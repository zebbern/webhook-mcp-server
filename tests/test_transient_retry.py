"""A dropped connection before any response is retried once for idempotent calls, never for POST.

Seen live on 2026-09-03: one GET /token/{id}/requests in a 108-call run failed with
"Server disconnected without sending a response"; the next call worked.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from utils.http_client import WEBHOOK_SITE_API, WebhookApiError, WebhookHttpClient

TOKEN = "550e8400-e29b-41d4-a716-446655440000"


@pytest.mark.asyncio
@respx.mock
async def test_get_retries_once_after_a_dropped_connection() -> None:
    route = respx.get(f"{WEBHOOK_SITE_API}/token/{TOKEN}")
    route.side_effect = [httpx.RemoteProtocolError("Server disconnected without sending a response."),
                         httpx.Response(200, json={"uuid": TOKEN})]
    async with WebhookHttpClient() as client:
        data = await client.get(f"/token/{TOKEN}")
    assert data["uuid"] == TOKEN
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_get_gives_up_after_the_second_drop() -> None:
    route = respx.get(f"{WEBHOOK_SITE_API}/token/{TOKEN}")
    route.side_effect = [httpx.RemoteProtocolError("dropped"), httpx.RemoteProtocolError("dropped again")]
    async with WebhookHttpClient() as client:
        with pytest.raises(WebhookApiError):
            await client.get(f"/token/{TOKEN}")
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_post_is_never_replayed() -> None:
    route = respx.post(f"{WEBHOOK_SITE_API}/token")
    route.side_effect = [httpx.RemoteProtocolError("dropped"), httpx.Response(201, json={"uuid": TOKEN})]
    async with WebhookHttpClient() as client:
        with pytest.raises(WebhookApiError):
            await client.post("/token", json_data={})
    assert route.call_count == 1
