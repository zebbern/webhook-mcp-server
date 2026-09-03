"""Rate limits, socket drops and the diagnostics tool. Shapes come from live probes on 2026-09-03."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from services.request_service import RequestService
from services.status_service import StatusService
from utils.http_client import WEBHOOK_SITE_API, WebhookApiError, WebhookHttpClient

TOKEN = "550e8400-e29b-41d4-a716-446655440000"
BASE = f"{WEBHOOK_SITE_API}/token/{TOKEN}"

# Exactly what the export endpoint returned once its 3/min quota was used.
RATE_LIMITED = dict(
    status_code=429,
    json={
        "success": False,
        "error": {
            "message": "This request has been rate limited, try again in 58 seconds. Please contact Webhook.site Support to inquire about raising the rate limit.",
            "id": "",
        },
    },
    headers={"retry-after": "58", "x-ratelimit-limit": "3", "x-ratelimit-remaining": "0", "x-ratelimit-reset": "1788466643"},
)


@pytest.mark.asyncio
@respx.mock
async def test_short_rate_limit_is_waited_out_and_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    short = dict(RATE_LIMITED, headers={**RATE_LIMITED["headers"], "retry-after": "1"})
    route = respx.get(f"{BASE}/requests").mock(side_effect=[httpx.Response(**short), httpx.Response(200, json={"data": []})])
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    async with WebhookHttpClient() as client:
        result = await client.get(f"/token/{TOKEN}/requests")
    assert result == {"data": []}
    assert route.call_count == 2
    assert sleeps == [1.5]


@pytest.mark.asyncio
@respx.mock
async def test_long_rate_limit_surfaces_the_wait_instead_of_hanging() -> None:
    respx.get(f"{BASE}/requests/export").mock(return_value=httpx.Response(**RATE_LIMITED))
    async with WebhookHttpClient() as client:
        with pytest.raises(WebhookApiError) as info:
            await client.get_raw(f"/token/{TOKEN}/requests/export", accept="text/csv")
    assert info.value.status_code == 429
    assert info.value.retry_after == 58.0
    assert "Rate limited: retry after 58 seconds" in str(info.value)
    assert "try again in 58 seconds" in str(info.value)


@pytest.mark.asyncio
@respx.mock
async def test_socket_drop_mid_wait_falls_back_to_fast_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    from services import request_service
    from tests.test_realtime import FakeSocket, _factory, _web

    monkeypatch.setattr(request_service, "POLL_INTERVAL_SECONDS", 0.05)
    monkeypatch.setattr(request_service, "SOCKET_POLL_INTERVAL_SECONDS", 30.0)
    listing = respx.get(f"{BASE}/requests").mock(
        side_effect=[
            httpx.Response(200, json={"data": [_web("old")]}),
            httpx.Response(200, json={"data": [_web("old")]}),
            httpx.Response(200, json={"data": [_web("fresh"), _web("old")]}),
        ]
    )

    async def drop() -> None:
        # A dropped socket delivers nothing more; the wait must notice and poll fast.
        await asyncio.sleep(0.05)
        FakeSocket.instances[-1].handlers["disconnect"]()

    async with WebhookHttpClient() as client:
        service = RequestService(client, socket_factory=_factory())
        task = asyncio.create_task(drop())
        result = await service.wait_for_request(TOKEN, timeout_seconds=5)
        await task
    assert result.success is True
    assert result.data["source"] == "poll"
    assert listing.call_count == 3


@pytest.mark.asyncio
@respx.mock
async def test_server_status_with_key_reports_plan_and_socket() -> None:
    from tests.test_realtime import _factory

    respx.get(f"{WEBHOOK_SITE_API}/token").mock(return_value=httpx.Response(200, json={"data": [{"uuid": TOKEN, "premium": True}]}))
    async with WebhookHttpClient(api_key="k") as client:
        report = await StatusService(client, socket_factory=_factory()).report()
    assert report.success is True
    assert report.data["account"] == {"reachable": True, "authenticated": True, "tokens_seen": 1, "premium_urls": True}
    assert report.data["realtime_socket"] == "connected"
    assert report.data["problems"] == []


@pytest.mark.asyncio
@respx.mock
async def test_server_status_without_key_and_with_bad_key() -> None:
    from tests.test_realtime import _factory

    respx.get(url__regex=rf"{WEBHOOK_SITE_API}/token/[0-9a-f-]+$").mock(
        return_value=httpx.Response(404, json={"success": False, "error": {"message": "Token not found"}})
    )
    respx.get(f"{WEBHOOK_SITE_API}/token").mock(return_value=httpx.Response(401, json={"success": False, "error": {"message": "Unauthenticated"}}))
    async with WebhookHttpClient() as client:
        anonymous = await StatusService(client, socket_factory=_factory(fail_connect=True)).report()
    async with WebhookHttpClient(api_key="bad") as client:
        rejected = await StatusService(client, socket_factory=_factory()).report(check_socket=False)
    assert anonymous.success is False and "No WEBHOOK_SITE_API_KEY" in anonymous.message
    assert anonymous.data["account"] == {"reachable": True, "authenticated": False}
    assert anonymous.data["realtime_socket"].startswith("unavailable")
    assert rejected.success is False and "rejected" in rejected.message
    assert "realtime_socket" not in rejected.data
