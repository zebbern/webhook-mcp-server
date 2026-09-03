"""Real sockets, no mocks: follow_email_link against a local web server and a local HTTP proxy.

These run offline (loopback only) but exercise the actual network stack:
PublicOnlyTransport with an allowlist reaching 127.0.0.1, and the proxied path
with HTTP_PROXY pointing at a proxy that really forwards the request.
"""

from __future__ import annotations

import asyncio
import http.server
import socketserver
import threading
import urllib.request
from collections.abc import Iterator

import pytest

from services.request_service import RequestService
from utils.safe_url import HostAllowList
from utils.validation import ValidationError


class _Site(http.server.BaseHTTPRequestHandler):
    hits: list[str] = []
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        _Site.hits.append(self.path)
        if self.path.startswith("/verify"):
            self.send_response(302)
            self.send_header("Location", "/welcome")
            self.end_headers()
            return
        body = b"<html><title>Welcome home</title><body>verified</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # silence
        pass


class _Proxy(http.server.BaseHTTPRequestHandler):
    """Minimal forward proxy for absolute-URI GETs (what an HTTP_PROXY receives)."""

    forwarded: list[str] = []
    protocol_version = "HTTP/1.1"
    # urllib would honour the HTTP_PROXY the test sets and loop back into this proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def do_GET(self) -> None:  # noqa: N802
        _Proxy.forwarded.append(self.path)
        with self.opener.open(self.path, timeout=5) as upstream:  # noqa: S310 - loopback only
            body = upstream.read()
            self.send_response(upstream.status)
            self.send_header("Content-Type", upstream.headers.get("Content-Type", "text/html"))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Via-Proxy", "1")
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


@pytest.fixture
def site() -> Iterator[str]:
    _Site.hits.clear()
    server = _Server(("127.0.0.1", 0), _Site)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://localhost:{server.server_address[1]}"
    finally:
        server.shutdown()


@pytest.fixture
def proxy() -> Iterator[str]:
    _Proxy.forwarded.clear()
    server = _Server(("127.0.0.1", 0), _Proxy)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


@pytest.mark.asyncio
async def test_allowlisted_local_server_is_fetched_over_a_real_socket(site: str, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    service = RequestService(client=None, follow_allowlist=HostAllowList.from_env("localhost"))  # type: ignore[arg-type]
    page = await service._fetch_captured_link(f"{site}/verify?token=abc")
    assert page["status_code"] == 200
    assert page["title"] == "Welcome home"
    assert page["redirects"] == [{"url": f"{site}/verify?token=abc", "status_code": 302}]
    assert _Site.hits == ["/verify?token=abc", "/welcome"]


@pytest.mark.asyncio
async def test_local_server_is_refused_without_the_allowlist(site: str, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        monkeypatch.delenv(name, raising=False)
    service = RequestService(client=None)  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="FOLLOW_EMAIL_LINK_ALLOW_HOSTS"):
        await service._fetch_captured_link(f"{site}/verify?token=abc")
    assert _Site.hits == []


@pytest.mark.asyncio
async def test_http_proxy_env_really_routes_through_the_proxy(site: str, proxy: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", proxy)
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    service = RequestService(client=None, follow_allowlist=HostAllowList.from_env("localhost"))  # type: ignore[arg-type]
    page = await service._fetch_captured_link(f"{site}/welcome")
    assert page["status_code"] == 200 and page["title"] == "Welcome home"
    assert _Proxy.forwarded == [f"{site}/welcome"]  # the proxy saw the absolute URL
    assert _Site.hits == ["/welcome"]


@pytest.mark.asyncio
async def test_no_proxy_bypasses_the_proxy(site: str, proxy: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", proxy)
    monkeypatch.setenv("NO_PROXY", "localhost")
    service = RequestService(client=None, follow_allowlist=HostAllowList.from_env("localhost"))  # type: ignore[arg-type]
    page = await service._fetch_captured_link(f"{site}/welcome")
    assert page["status_code"] == 200
    assert _Proxy.forwarded == []
    assert _Site.hits == ["/welcome"]
