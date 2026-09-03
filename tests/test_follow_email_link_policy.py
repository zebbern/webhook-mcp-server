"""Policy tests for follow_email_link: operator allowlist, proxies, blocked redirects, TLS."""

from __future__ import annotations

import ipaddress
import socket
from pathlib import Path

import httpcore
import httpx
import pytest
import respx

from services import request_service
from services.request_service import RequestService
from utils import safe_url
from utils.http_client import WEBHOOK_SITE_API, WebhookHttpClient
from utils.safe_url import (
    HostAllowList,
    PublicOnlyBackend,
    PublicOnlyTransport,
    default_ssl_context,
    ensure_public_http_url,
    proxy_for_url,
)
from utils.validation import ValidationError

TOKEN = "550e8400-e29b-41d4-a716-446655440000"
REQUESTS_URL = f"{WEBHOOK_SITE_API}/token/{TOKEN}/requests"
VERIFY = "https://example.com/verify?token=abc"
LOCAL_VERIFY = "http://localhost:3000/verify?token=abc"
PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")


def _email(uuid: str, text: str) -> dict:
    return {
        "uuid": uuid,
        "type": "email",
        "content": "",
        "text_content": text,
        "html_content": "",
        "headers": {"from": ["noreply@example.com"], "subject": [uuid]},
        "created_at": "2026-01-01 00:00:00",
    }


def _inbox(*emails: dict) -> None:
    respx.get(REQUESTS_URL).mock(return_value=httpx.Response(200, json={"data": list(emails)}))


async def _follow(allow: str | None = None, **kwargs) -> request_service.ToolResult:
    async with WebhookHttpClient() as client:
        service = RequestService(client, follow_allowlist=HostAllowList.from_env(allow))
        return await service.follow_email_link(TOKEN, **kwargs)


class _FakeStream:
    pass


class _FakeBackend:
    def __init__(self) -> None:
        self.hosts: list[str] = []

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        self.hosts.append(host)
        return _FakeStream()

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise AssertionError("unexpected unix socket connect")

    async def sleep(self, seconds: float) -> None:
        return None


def _resolver(*addresses: str):
    async def resolve(host: str, port: int) -> list[str]:
        return list(addresses)

    return resolve


@pytest.fixture
def no_proxy_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in PROXY_VARS:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    return monkeypatch


# --- allowlist ------------------------------------------------------------


def test_allowlist_parses_hosts_wildcards_and_networks() -> None:
    allow = HostAllowList.from_env("localhost, 127.0.0.1 ,*.corp.example,10.0.0.0/8\n::1")
    assert allow
    assert allow.allows_host("localhost") and allow.allows_host("LOCALHOST.")
    assert allow.allows_host("app.corp.example") and not allow.allows_host("corp.example")
    assert allow.allows_address(ipaddress.ip_address("127.0.0.1"))
    assert allow.allows_address(ipaddress.ip_address("10.2.3.4"))
    assert allow.allows_address(ipaddress.ip_address("::1"))
    assert not allow.allows_address(ipaddress.ip_address("192.168.0.1"))
    assert not HostAllowList.from_env("") and not HostAllowList.from_env(None)


@pytest.mark.parametrize("value", ["10.0.0.0/99", "http://localhost", "bad!host", "*.", "*"])
def test_allowlist_rejects_invalid_entries(value: str) -> None:
    with pytest.raises(ValueError, match="FOLLOW_EMAIL_LINK_ALLOW_HOSTS"):
        HostAllowList.from_env(value)


def test_ensure_public_http_url_honors_allowlist() -> None:
    allow = HostAllowList.from_env("localhost,10.0.0.0/8")
    ensure_public_http_url("http://localhost:3000/verify", allow)
    ensure_public_http_url("http://10.1.2.3/verify", allow)
    with pytest.raises(ValidationError, match="FOLLOW_EMAIL_LINK_ALLOW_HOSTS"):
        ensure_public_http_url("http://192.168.1.5/verify", allow)
    with pytest.raises(ValidationError, match="FOLLOW_EMAIL_LINK_ALLOW_HOSTS"):
        ensure_public_http_url("http://localhost:3000/verify")


@pytest.mark.asyncio
async def test_backend_allowlist_permits_private_resolution_for_listed_hosts() -> None:
    inner = _FakeBackend()
    allow = HostAllowList.from_env("*.corp.example")
    backend = PublicOnlyBackend(inner, resolver=_resolver("10.0.0.5"), allowlist=allow)
    await backend.connect_tcp("app.corp.example", 443)
    assert inner.hosts == ["10.0.0.5"]
    with pytest.raises(ValidationError, match="private"):
        await backend.connect_tcp("other.example", 443)
    assert inner.hosts == ["10.0.0.5"]


@pytest.mark.asyncio
async def test_backend_allowlist_permits_listed_networks() -> None:
    inner = _FakeBackend()
    allow = HostAllowList.from_env("10.0.0.0/8")
    backend = PublicOnlyBackend(inner, resolver=_resolver("10.0.0.5"), allowlist=allow)
    await backend.connect_tcp("intranet.example", 80)
    await backend.connect_tcp("10.9.9.9", 80)
    assert inner.hosts == ["10.0.0.5", "10.9.9.9"]
    with pytest.raises(ValidationError):
        await backend.connect_tcp("192.168.1.1", 80)


@pytest.mark.asyncio
@respx.mock
async def test_follow_email_link_opens_local_link_when_allowed() -> None:
    _inbox(_email("m", f"Click {LOCAL_VERIFY}"))
    route = respx.get(LOCAL_VERIFY).mock(return_value=httpx.Response(200, text="ok"))
    result = await _follow(allow="localhost")
    assert route.called
    assert result.success is True
    assert result.data["opened_url"] == LOCAL_VERIFY


@pytest.mark.asyncio
@respx.mock
async def test_follow_email_link_refuses_local_link_by_default_with_hint() -> None:
    _inbox(_email("m", f"Click {LOCAL_VERIFY}"))
    with pytest.raises(ValidationError, match="FOLLOW_EMAIL_LINK_ALLOW_HOSTS"):
        await _follow()


# --- blocked redirect after a successful public hop -----------------------


@pytest.mark.asyncio
@respx.mock
async def test_follow_email_link_reports_blocked_redirect_as_success() -> None:
    _inbox(_email("m", f"Click {VERIFY}"))
    respx.get(VERIFY).mock(
        return_value=httpx.Response(302, headers={"location": "http://localhost:3000/welcome"})
    )
    result = await _follow()
    assert result.success is True
    assert result.data["status_code"] == 302
    assert result.data["final_url"] == VERIFY
    assert result.data["redirects"] == []
    assert result.data["blocked_redirect"]["url"] == "http://localhost:3000/welcome"
    assert "did not follow the redirect to http://localhost:3000/welcome" in result.message


@pytest.mark.asyncio
@respx.mock
async def test_follow_email_link_reports_blocked_redirect_after_chain() -> None:
    _inbox(_email("m", f"Click {VERIFY}"))
    respx.get(VERIFY).mock(return_value=httpx.Response(302, headers={"location": "/step2"}))
    respx.get("https://example.com/step2").mock(
        return_value=httpx.Response(303, headers={"location": "http://10.0.0.5/app"})
    )
    result = await _follow()
    assert result.success is True
    assert result.data["status_code"] == 303
    assert result.data["final_url"] == "https://example.com/step2"
    assert result.data["redirects"] == [{"url": VERIFY, "status_code": 302}]
    assert result.data["blocked_redirect"]["url"] == "http://10.0.0.5/app"


@pytest.mark.asyncio
@respx.mock
async def test_follow_email_link_allowed_redirect_target_is_followed() -> None:
    _inbox(_email("m", f"Click {VERIFY}"))
    respx.get(VERIFY).mock(
        return_value=httpx.Response(302, headers={"location": "http://localhost:3000/welcome"})
    )
    respx.get("http://localhost:3000/welcome").mock(
        return_value=httpx.Response(200, text="<title>Welcome</title>")
    )
    result = await _follow(allow="localhost")
    assert result.data["status_code"] == 200
    assert result.data["title"] == "Welcome"
    assert "blocked_redirect" not in result.data


@pytest.mark.asyncio
@respx.mock
async def test_follow_email_link_blocked_first_hop_still_fails() -> None:
    _inbox(_email("m", "Click http://10.0.0.5/verify?token=abc"))
    with pytest.raises(ValidationError, match="private"):
        await _follow()


# --- proxies --------------------------------------------------------------


def test_proxy_for_url_ignores_missing_env(no_proxy_env: pytest.MonkeyPatch) -> None:
    assert proxy_for_url("https://example.com/x") is None


def test_proxy_for_url_reads_env(no_proxy_env: pytest.MonkeyPatch) -> None:
    env = no_proxy_env
    env.setenv("HTTPS_PROXY", "http://proxy.corp:8080")
    env.setenv("http_proxy", "http://proxy2.corp:8080")
    env.setenv("NO_PROXY", "localhost, .internal.example, example.org:443")
    assert proxy_for_url("https://example.com/x") == "http://proxy.corp:8080"
    assert proxy_for_url("http://example.com/x") == "http://proxy2.corp:8080"
    assert proxy_for_url("https://app.internal.example/x") is None
    assert proxy_for_url("https://example.org/x") is None
    assert proxy_for_url("http://localhost:3000/x") is None
    env.delenv("HTTPS_PROXY")
    env.setenv("ALL_PROXY", "socks5://proxy.corp:1080")
    assert proxy_for_url("https://example.com/x") == "socks5://proxy.corp:1080"
    env.setenv("NO_PROXY", "*")
    assert proxy_for_url("https://example.com/x") is None


@pytest.mark.asyncio
async def test_fetch_captured_link_vets_target_before_using_proxy(no_proxy_env: pytest.MonkeyPatch) -> None:
    no_proxy_env.setenv("HTTPS_PROXY", "http://proxy.corp:8080")
    no_proxy_env.setattr(safe_url, "resolve_addresses", _resolver("10.0.0.5"))
    no_proxy_env.setattr(request_service, "_proxy_transport", lambda proxy: pytest.fail("must vet first"))
    service = RequestService(client=None)  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="private"):
        await service._fetch_captured_link("https://intranet.example/verify")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_captured_link_uses_proxy_transport(no_proxy_env: pytest.MonkeyPatch) -> None:
    no_proxy_env.setenv("HTTPS_PROXY", "http://proxy.corp:8080")
    no_proxy_env.setattr(safe_url, "resolve_addresses", _resolver("93.184.216.34"))
    proxies: list[str] = []

    def record(proxy: str) -> httpx.AsyncHTTPTransport:
        proxies.append(proxy)
        return httpx.AsyncHTTPTransport(proxy=proxy, trust_env=False)

    no_proxy_env.setattr(request_service, "_proxy_transport", record)
    no_proxy_env.setattr(
        request_service, "PublicOnlyTransport", lambda **kw: pytest.fail("direct transport used")
    )
    respx.get(VERIFY).mock(return_value=httpx.Response(200, text="<title>Via proxy</title>"))
    service = RequestService(client=None)  # type: ignore[arg-type]
    page = await service._fetch_captured_link(VERIFY)
    assert page["title"] == "Via proxy"
    assert proxies == ["http://proxy.corp:8080"]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_captured_link_bypasses_proxy_for_no_proxy_hosts(
    no_proxy_env: pytest.MonkeyPatch,
) -> None:
    no_proxy_env.setenv("HTTPS_PROXY", "http://proxy.corp:8080")
    no_proxy_env.setenv("NO_PROXY", "example.com")
    no_proxy_env.setattr(request_service, "_proxy_transport", lambda proxy: pytest.fail("proxy used"))
    respx.get(VERIFY).mock(return_value=httpx.Response(200, text="direct"))
    service = RequestService(client=None)  # type: ignore[arg-type]
    page = await service._fetch_captured_link(VERIFY)
    assert page["preview"] == "direct"


def test_public_only_transport_refuses_proxy() -> None:
    with pytest.raises(ValueError):
        PublicOnlyTransport(proxy="http://proxy.corp:8080")


# --- TLS ------------------------------------------------------------------


def test_default_ssl_context_honors_ssl_cert_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import certifi

    bundle = Path(certifi.where()).read_text(encoding="utf-8")
    start = bundle.index("-----BEGIN CERTIFICATE-----")
    end = bundle.index("-----END CERTIFICATE-----", start) + len("-----END CERTIFICATE-----")
    pem = tmp_path / "corp-ca.pem"
    pem.write_text(bundle[start:end] + "\n", encoding="utf-8")
    monkeypatch.setenv("SSL_CERT_FILE", str(pem))
    monkeypatch.setattr(safe_url, "_ssl_context", None)
    context = default_ssl_context()
    assert len(context.get_ca_certs()) == 1
    assert context.check_hostname is True
    assert PublicOnlyTransport()._pool._ssl_context is context


@pytest.mark.live
@pytest.mark.asyncio
async def test_pinned_connection_still_validates_certificate_hostname() -> None:
    other_site = socket.getaddrinfo("github.com", 443, type=socket.SOCK_STREAM)[0][4][0]

    async def lie(host: str, port: int) -> list[str]:
        return [other_site]

    async with httpx.AsyncClient(transport=PublicOnlyTransport(resolver=lie), timeout=15) as client:
        with pytest.raises(httpx.ConnectError, match="certificate"):
            await client.get("https://example.com/")


@pytest.mark.asyncio
async def test_transport_wiring_survives_httpcore_pool() -> None:
    # The wiring relies on httpx's _pool and httpcore's _network_backend; if a
    # release renames them the constructor must fail closed, not connect unpinned.
    inner = httpcore.AsyncMockBackend([b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"])
    transport = PublicOnlyTransport(resolver=_resolver("93.184.216.34"), network_backend=inner)
    assert transport._pool._network_backend is transport.network_backend
