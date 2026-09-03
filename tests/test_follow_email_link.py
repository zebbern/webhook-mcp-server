"""Offline regression tests for follow_email_link, link extraction and OTP parsing."""

from __future__ import annotations

import ipaddress
import socket
import time

import httpcore
import httpx
import pytest
import respx

from services import request_service
from services.request_service import RequestService
from utils.email_extract import (
    auth_link_score,
    combined_request_text,
    extract_auth_links,
    extract_urls,
    extract_verification_codes,
    normalize_url,
)
from utils.http_client import WEBHOOK_SITE_API, WebhookHttpClient
from utils.safe_url import (
    PublicOnlyBackend,
    PublicOnlyTransport,
    ensure_public_http_url,
    is_public_address,
)
from utils.validation import ValidationError

TOKEN = "550e8400-e29b-41d4-a716-446655440000"
REQUESTS_URL = f"{WEBHOOK_SITE_API}/token/{TOKEN}/requests"
VERIFY = "https://example.com/verify?token=abc"
VERIFY_NEW = "https://example.com/verify?token=def"
LOGIN = "https://app.example.com/login"
OK_RESPONSE = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"


def _email(uuid: str, text: str = "", html: str = "", content: str = "") -> dict:
    return {
        "uuid": uuid,
        "type": "email",
        "method": "POST",
        "content": content,
        "text_content": text,
        "html_content": html,
        "headers": {"from": ["noreply@example.com"], "subject": [uuid]},
        "query": {},
        "url": "",
        "ip": "1.2.3.4",
        "created_at": "2026-01-01 00:00:00",
    }


def _inbox(*emails: dict) -> None:
    respx.get(REQUESTS_URL).mock(return_value=httpx.Response(200, json={"data": list(emails)}))


async def _follow(**kwargs) -> request_service.ToolResult:
    async with WebhookHttpClient() as client:
        return await RequestService(client).follow_email_link(TOKEN, **kwargs)


# --- extraction -----------------------------------------------------------


def test_combined_text_ignores_raw_eml_when_decoded_parts_exist() -> None:
    raw_eml = (
        "Content-Transfer-Encoding: quoted-printable\r\n\r\n"
        "Click https://example.com/verify?token=3Dabc&u=3D1 now\r\n"
    )
    req = _email("m", text="Click https://example.com/verify?token=abc&u=1", content=raw_eml)
    assert extract_urls(combined_request_text(req)) == ["https://example.com/verify?token=abc&u=1"]


def test_combined_text_falls_back_to_content_for_http_requests() -> None:
    req = {"content": '{"callback": "https://example.com/hook?token=zz"}'}
    assert extract_urls(combined_request_text(req)) == ["https://example.com/hook?token=zz"]


def test_extract_urls_unescapes_html_entities() -> None:
    html = '<a href="https://example.com/verify?u=1&amp;t=abc">Verify</a>'
    text = "https://example.com/verify?u=1&t=abc"
    assert extract_urls(f"{text} {html}") == ["https://example.com/verify?u=1&t=abc"]


def test_extract_urls_stops_at_escaped_quote() -> None:
    assert extract_urls("href=&quot;https://example.com/x?a=1&quot;") == ["https://example.com/x?a=1"]


def test_extract_urls_keeps_legacy_entity_lookalikes() -> None:
    url = "https://example.com/verify?token=abc&region=eu&copy=1&not=2&lt=3&times=4"
    assert extract_urls(f"Open {url} now") == [url]
    assert normalize_url(url) == url


def test_extract_urls_handles_ipv6_literal_without_raising() -> None:
    url = "http://[2001:db8::1]/verify?token=abc"
    assert extract_urls(f"Go {url}") == [url]
    assert auth_link_score(url) >= 3
    assert extract_auth_links([url]) == [url]


def test_extract_urls_drops_zero_width_characters() -> None:
    assert extract_urls("https://example.com/x&#8203; and https://example.com/y​.") == [
        "https://example.com/x",
        "https://example.com/y",
    ]


def test_extract_auth_links_ranks_verify_first_and_drops_unsubscribe() -> None:
    urls = [
        "https://app.example.com/login",
        "https://app.example.com/verify?code=abc",
        "https://m.example.com/unsubscribe?token=zz",
        "https://example.com/static/logo.png",
    ]
    assert extract_auth_links(urls) == [
        "https://app.example.com/verify?code=abc",
        "https://app.example.com/login",
    ]


def test_extract_auth_links_uses_anchor_text_for_tracker_links() -> None:
    tracker = "https://ct.sendgrid.net/ls/click?upn=abc123"
    html = f'<a href="{tracker}"><span>Verify your email</span></a> <a href="{LOGIN}">Log in</a>'
    assert extract_auth_links(extract_urls(html), html) == [tracker, LOGIN]


def test_extract_auth_links_requires_word_boundaries() -> None:
    assert extract_auth_links(
        [
            "https://blog.example.com/authors/jane",
            "https://example.com/lessons/1",
            "https://example.com/hotpicks",
        ]
    ) == []


def test_extract_auth_links_keeps_mailchimp_confirm_and_asset_query_params() -> None:
    confirm = "https://example.us1.list-manage.com/subscribe/confirm?u=1&id=2&e=3"
    with_asset_param = "https://example.com/verify?img=logo.png"
    assert extract_auth_links([confirm, with_asset_param]) == [confirm, with_asset_param]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("<style>.a{color:#333333;background:#000000}</style><p>Your code is 847291</p>", ["847291"]),
        ("Your verification code is 512930. Order #778812", ["512930"]),
        ("code: 123 456", ["123456"]),
        ("847291 is your verification code", ["847291"]),
        ("Enter 442211 to continue", ["442211"]),
        ("Use 1234 to sign in. Ref #55667788", []),
        ("Your one-time password: 9081", ["9081"]),
        ("<p>Your&nbsp;code:&nbsp;<b>55 44 33</b></p>", ["554433"]),
        ("Your code is 847291 10 minutes from now it expires", ["847291"]),
        ("code 1234 expires in 10 minutes", ["1234"]),
        ("G-847291 is your Google verification code", ["847291"]),
        ("promo code 2024. Your login code is 556677", ["556677"]),
        ("Order number is 123456", []),
        ("zip code 90210. Enter 442211 to continue", ["442211"]),
        ("Your sort code is 12-34-56", []),
        ("<h1>847 291</h1>", ["847291"]),
    ],
)
def test_extract_verification_codes(text: str, expected: list[str]) -> None:
    assert extract_verification_codes(text) == expected


def test_markup_stripping_is_linear_on_unclosed_tags() -> None:
    start = time.perf_counter()
    assert extract_verification_codes("<script>" * 20000 + "Your code is 847291") == []
    assert extract_verification_codes("<style>" * 20000 + "</style>Your code is 847291") == ["847291"]
    assert extract_verification_codes("<a href=" * 20000 + "Your code is 847291") == ["847291"]
    assert time.perf_counter() - start < 3.0


# --- follow_email_link selection ------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_follow_email_link_prefers_email_containing_url() -> None:
    _inbox(_email("welcome", text=f"Log in at {LOGIN}"), _email("verify", text=f"Click {VERIFY}"))
    respx.get(VERIFY).mock(return_value=httpx.Response(200, text="<title>Verified</title>"))
    result = await _follow(url=VERIFY)
    assert result.success is True
    assert result.data["request_id"] == "verify"
    assert result.data["opened_url"] == VERIFY


@pytest.mark.asyncio
@respx.mock
async def test_follow_email_link_default_prefers_strong_link_over_newer_login() -> None:
    _inbox(_email("welcome", text=f"Log in at {LOGIN}"), _email("verify", text=f"Click {VERIFY}"))
    route = respx.get(VERIFY).mock(return_value=httpx.Response(200, text="ok"))
    result = await _follow()
    assert route.called
    assert result.data["request_id"] == "verify"
    assert result.data["auth_links"][0] == VERIFY


@pytest.mark.asyncio
@respx.mock
async def test_follow_email_link_default_prefers_newest_strong_link() -> None:
    _inbox(_email("verify-new", text=f"Click {VERIFY_NEW}"), _email("verify-old", text=f"Click {VERIFY}"))
    route = respx.get(VERIFY_NEW).mock(return_value=httpx.Response(200, text="ok"))
    result = await _follow()
    assert route.called
    assert result.data["request_id"] == "verify-new"


@pytest.mark.asyncio
@respx.mock
async def test_follow_email_link_honors_request_id() -> None:
    respx.get(f"{WEBHOOK_SITE_API}/token/{TOKEN}/request/verify").mock(
        return_value=httpx.Response(200, json=_email("verify", text=f"Click {VERIFY}"))
    )
    respx.get(VERIFY).mock(return_value=httpx.Response(200, text="ok"))
    result = await _follow(request_id="verify")
    assert result.success is True
    assert result.data["request_id"] == "verify"


@pytest.mark.asyncio
@respx.mock
async def test_follow_email_link_skips_unsubscribe_and_returns_candidates() -> None:
    html = (
        '<a href="https://m.example.com/unsubscribe?token=zz">unsub</a>'
        f'<a href="{LOGIN}">login</a>'
        '<a href="https://app.example.com/verify?u=1&amp;code=abc">verify</a>'
    )
    _inbox(_email("m", html=html))
    route = respx.get("https://app.example.com/verify?u=1&code=abc").mock(
        return_value=httpx.Response(200, text="ok")
    )
    result = await _follow()
    assert route.called
    assert result.data["auth_links"] == ["https://app.example.com/verify?u=1&code=abc", LOGIN]


@pytest.mark.asyncio
@respx.mock
async def test_follow_email_link_accepts_html_escaped_url_argument() -> None:
    html = '<a href="https://app.example.com/verify?u=1&amp;code=abc">verify</a>'
    _inbox(_email("m", html=html))
    route = respx.get("https://app.example.com/verify?u=1&code=abc").mock(
        return_value=httpx.Response(200, text="ok")
    )
    result = await _follow(url="https://app.example.com/verify?u=1&amp;code=abc")
    assert route.called
    assert result.data["opened_url"] == "https://app.example.com/verify?u=1&code=abc"


@pytest.mark.asyncio
@respx.mock
async def test_follow_email_link_accepts_url_exactly_as_reported() -> None:
    url = "https://example.com/verify?token=abc&region=eu&copy=1"
    _inbox(_email("m", text=f"Open {url}"))
    route = respx.get(url).mock(return_value=httpx.Response(200, text="ok"))
    result = await _follow(url=url)
    assert route.called
    assert result.data["opened_url"] == url


@pytest.mark.asyncio
@respx.mock
async def test_follow_email_link_rejects_url_missing_from_every_email() -> None:
    _inbox(_email("m", text=VERIFY))
    with pytest.raises(ValidationError, match="not found"):
        await _follow(url="https://evil.example/phish")


# --- redirects ------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_follow_email_link_3xx_without_location_is_final() -> None:
    _inbox(_email("m", text=VERIFY))
    respx.get(VERIFY).mock(return_value=httpx.Response(302, text="moved"))
    result = await _follow()
    assert result.data["status_code"] == 302
    assert result.data["redirects"] == []
    assert result.data["final_url"] == VERIFY


@pytest.mark.asyncio
@respx.mock
async def test_follow_email_link_follows_redirect_and_reports_history() -> None:
    _inbox(_email("m", text=VERIFY))
    respx.get(VERIFY).mock(return_value=httpx.Response(302, headers={"location": "/done"}))
    respx.get("https://example.com/done").mock(
        return_value=httpx.Response(200, text="<title>Done</title>")
    )
    result = await _follow()
    assert result.success is True
    assert result.data["status_code"] == 200
    assert result.data["final_url"] == "https://example.com/done"
    assert result.data["redirects"] == [{"url": VERIFY, "status_code": 302}]
    assert result.data["title"] == "Done"


@pytest.mark.asyncio
@respx.mock
async def test_follow_email_link_does_not_follow_redirect_to_private_address() -> None:
    _inbox(_email("m", text=VERIFY))
    respx.get(VERIFY).mock(
        return_value=httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})
    )
    result = await _follow()
    assert result.success is True
    assert result.data["status_code"] == 302
    assert result.data["blocked_redirect"]["url"] == "http://169.254.169.254/latest"
    assert "private" in result.data["blocked_redirect"]["reason"]


@pytest.mark.asyncio
@respx.mock
async def test_follow_email_link_rejects_javascript_redirect() -> None:
    # httpx raises while preparing the next request, before handing back the 302,
    # so there is no successful hop to report.
    _inbox(_email("m", text=VERIFY))
    respx.get(VERIFY).mock(return_value=httpx.Response(302, headers={"location": "javascript:alert(1)"}))
    with pytest.raises(ValidationError, match="not a valid http"):
        await _follow()


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("location", ["ftp://example.com/x", "http://exa mple.com/"])
async def test_follow_email_link_stops_at_non_http_redirects(location: str) -> None:
    _inbox(_email("m", text=VERIFY))
    respx.get(VERIFY).mock(return_value=httpx.Response(302, headers={"location": location}))
    result = await _follow()
    assert result.success is True
    assert result.data["blocked_redirect"]["url"].startswith(location.split(" ")[0])


@pytest.mark.asyncio
@respx.mock
async def test_follow_email_link_reports_too_many_redirects() -> None:
    _inbox(_email("m", text=VERIFY))
    respx.get(VERIFY).mock(return_value=httpx.Response(302, headers={"location": VERIFY}))
    with pytest.raises(ValidationError, match="Too many redirects"):
        await _follow()


# --- SSRF pinning ---------------------------------------------------------


class _FakeStream:
    pass


class _FakeBackend:
    def __init__(self) -> None:
        self.hosts: list[str] = []
        self.timeouts: list[float | None] = []

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        self.hosts.append(host)
        self.timeouts.append(timeout)
        return _FakeStream()

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise AssertionError("unexpected unix socket connect")

    async def sleep(self, seconds: float) -> None:
        return None


class _RecordingMockBackend(httpcore.AsyncMockBackend):
    def __init__(self, buffer: list[bytes]) -> None:
        super().__init__(buffer)
        self.hosts: list[str] = []

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        self.hosts.append(host)
        return await super().connect_tcp(
            host, port, timeout=timeout, local_address=local_address, socket_options=socket_options
        )


def _resolver(*addresses: str):
    async def resolve(host: str, port: int) -> list[str]:
        return list(addresses)

    return resolve


@pytest.mark.asyncio
async def test_public_only_backend_connects_to_the_vetted_ip() -> None:
    inner = _FakeBackend()
    backend = PublicOnlyBackend(inner, resolver=_resolver("93.184.216.34"))
    await backend.connect_tcp("example.com", 443)
    assert inner.hosts == ["93.184.216.34"]


@pytest.mark.asyncio
@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "::1", "fd00::1"])
async def test_public_only_backend_rejects_private_resolution(address: str) -> None:
    inner = _FakeBackend()
    backend = PublicOnlyBackend(inner, resolver=_resolver("93.184.216.34", address))
    with pytest.raises(ValidationError, match="private"):
        await backend.connect_tcp("example.com", 443)
    assert inner.hosts == []


@pytest.mark.asyncio
async def test_public_only_backend_rejects_private_literal_without_resolving() -> None:
    inner = _FakeBackend()

    async def boom(host: str, port: int) -> list[str]:
        raise AssertionError("literal addresses must not be resolved")

    backend = PublicOnlyBackend(inner, resolver=boom)
    with pytest.raises(ValidationError):
        await backend.connect_tcp("169.254.169.254", 80)
    assert inner.hosts == []


@pytest.mark.asyncio
async def test_public_only_backend_refuses_unix_sockets() -> None:
    backend = PublicOnlyBackend(_FakeBackend(), resolver=_resolver("93.184.216.34"))
    with pytest.raises(ValidationError):
        await backend.connect_unix_socket("/var/run/docker.sock")


@pytest.mark.asyncio
async def test_public_only_backend_shares_one_timeout_across_addresses() -> None:
    class Flaky(_FakeBackend):
        async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
            await super().connect_tcp(host, port, timeout, local_address, socket_options)
            if len(self.hosts) < 3:
                raise httpcore.ConnectError("refused")
            return _FakeStream()

    inner = Flaky()
    backend = PublicOnlyBackend(
        inner, resolver=_resolver("93.184.216.34", "93.184.216.35", "93.184.216.36")
    )
    await backend.connect_tcp("example.com", 443, timeout=5.0)
    assert inner.hosts == ["93.184.216.34", "93.184.216.35", "93.184.216.36"]
    assert all(t is not None and t <= 5.0 for t in inner.timeouts)
    assert inner.timeouts == sorted(inner.timeouts, reverse=True)


@pytest.mark.asyncio
async def test_public_only_backend_bounds_dns_by_the_connect_timeout() -> None:
    async def slow(host: str, port: int) -> list[str]:
        import anyio

        await anyio.sleep(5)
        return ["93.184.216.34"]

    backend = PublicOnlyBackend(_FakeBackend(), resolver=slow)
    start = time.perf_counter()
    with pytest.raises(httpcore.ConnectTimeout):
        await backend.connect_tcp("example.com", 443, timeout=0.2)
    assert time.perf_counter() - start < 2.0


@pytest.mark.parametrize(
    "address",
    [
        "168.63.129.16",
        "100.64.1.1",
        "192.0.0.192",
        "224.0.0.1",
        "255.255.255.255",
        "::ffff:127.0.0.1",
        "::ffff:10.0.0.1",
        "64:ff9b::7f00:1",
        "::7f00:1",
        "2002:7f00:1::1",
        "ff02::1",
        "2001:db8::1",
    ],
)
def test_is_public_address_rejects_embedded_and_cloud_ranges(address: str) -> None:
    assert not is_public_address(ipaddress.ip_address(address))


@pytest.mark.parametrize(
    "address",
    ["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946", "64:ff9b::5db8:d822"],
)
def test_is_public_address_accepts_public(address: str) -> None:
    assert is_public_address(ipaddress.ip_address(address))


def test_public_only_transport_pins_every_connection() -> None:
    transport = PublicOnlyTransport()
    assert isinstance(transport.network_backend, PublicOnlyBackend)


@pytest.mark.asyncio
async def test_transport_pins_through_the_real_pool() -> None:
    inner = _RecordingMockBackend([OK_RESPONSE])
    transport = PublicOnlyTransport(resolver=_resolver("93.184.216.34"), network_backend=inner)
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("http://example.com/")
    assert response.status_code == 200
    assert inner.hosts == ["93.184.216.34"]


@pytest.mark.asyncio
async def test_transport_blocks_private_resolution_through_the_real_pool() -> None:
    inner = _RecordingMockBackend([OK_RESPONSE])
    transport = PublicOnlyTransport(resolver=_resolver("10.0.0.5"), network_backend=inner)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ValidationError, match="private"):
            await client.get("http://intranet.example/")
    assert inner.hosts == []


@pytest.mark.asyncio
async def test_fetch_captured_link_vets_redirect_hosts_by_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inner = _RecordingMockBackend(
        [b"HTTP/1.1 302 Found\r\nLocation: http://intranet.example/admin\r\nContent-Length: 0\r\n\r\n"]
    )

    async def resolve(host: str, port: int) -> list[str]:
        return ["93.184.216.34"] if host == "example.com" else ["10.0.0.5"]

    monkeypatch.setattr(
        request_service,
        "PublicOnlyTransport",
        lambda **kw: PublicOnlyTransport(resolver=resolve, network_backend=inner, **kw),
    )
    service = RequestService(client=None)  # type: ignore[arg-type]
    page = await service._fetch_captured_link("http://example.com/verify")
    assert inner.hosts == ["93.184.216.34"]
    assert page["status_code"] == 302
    assert page["final_url"] == "http://example.com/verify"
    assert page["blocked_redirect"]["url"] == "http://intranet.example/admin"
    assert "private" in page["blocked_redirect"]["reason"]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_captured_link_uses_pinned_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[PublicOnlyTransport] = []

    class Recording(PublicOnlyTransport):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            created.append(self)

    monkeypatch.setattr(request_service, "PublicOnlyTransport", Recording)
    _inbox(_email("m", text=VERIFY))
    respx.get(VERIFY).mock(return_value=httpx.Response(200, text="ok"))
    await _follow()
    assert len(created) == 1


def test_ensure_public_http_url_does_not_block_on_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args, **kwargs):
        raise AssertionError("sync DNS lookup on the event loop")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    ensure_public_http_url("https://example.com/verify")
    for bad in (
        "http://[::1]/verify",
        "http://10.1.2.3/verify",
        "http://168.63.129.16/",
        "http://[::ffff:127.0.0.1]/",
        "http://app.localhost/",
    ):
        with pytest.raises(ValidationError):
            ensure_public_http_url(bad)
