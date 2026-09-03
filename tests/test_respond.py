"""respond_to_next_request: the whcli forward mechanism, verified live on 2026-09-03.

Facts encoded here: POST /token ignores `listen` (only PUT sets it); a held
request is answered with PUT /request/{id}/response, which returns
{"status": 3} when delivered and {"status": 2} when nothing was waiting.
"""

from __future__ import annotations

import asyncio
import base64
import json

import httpx
import pytest
import respx

from models.schemas import WebhookConfig
from services.request_service import RequestService
from services.webhook_service import WebhookService
from tests.test_realtime import FakeSocket, _factory, _web
from utils.http_client import WEBHOOK_SITE_API, WebhookHttpClient

TOKEN = "550e8400-e29b-41d4-a716-446655440000"
BASE = f"{WEBHOOK_SITE_API}/token/{TOKEN}"
TOKEN_OBJECT = {"uuid": TOKEN, "default_status": 203, "default_content": "keep", "timeout": 0, "listen": 0, "cors": False, "actions": False}


@pytest.mark.asyncio
@respx.mock
async def test_answers_the_held_request_and_restores_listen() -> None:
    respx.get(BASE).mock(return_value=httpx.Response(200, json=TOKEN_OBJECT))
    token_put = respx.put(BASE).mock(return_value=httpx.Response(200, json={**TOKEN_OBJECT, "listen": 10}))
    respx.get(f"{BASE}/requests").mock(return_value=httpx.Response(200, json={"data": [_web("old")]}))
    answer = respx.put(f"{BASE}/request/new/response").mock(return_value=httpx.Response(200, json={"status": 3}))
    respx.get(f"{BASE}/request/new").mock(return_value=httpx.Response(200, json=_web("new")))

    async def deliver() -> None:
        await asyncio.sleep(0.05)
        FakeSocket.instances[-1].push({"request": {"uuid": "new"}, "variables": {}})

    async with WebhookHttpClient(api_key="k") as client:
        service = RequestService(client, socket_factory=_factory())
        task = asyncio.create_task(deliver())
        result = await service.respond_to_next_request(
            TOKEN, status=299, content='{"ok":true}', headers={"X-Test": "1"}, timeout_seconds=5
        )
        await task
    assert result.success is True and result.data["answered"] is True
    assert result.data["request"]["uuid"] == "new" and result.data["listened_via"] == "socket"
    sent = json.loads(answer.calls[0].request.content)
    assert base64.b64decode(sent["content"]) == b'{"ok":true}' and sent["status"] == 299 and sent["headers"] == {"X-Test": "1"}
    # listen raised to 10 with the other settings preserved, then restored to 0
    bodies = [json.loads(c.request.content) for c in token_put.calls]
    assert bodies[0]["listen"] == 10 and bodies[0]["default_status"] == 203 and bodies[0]["default_content"] == "keep"
    assert bodies[-1]["listen"] == 0
    assert FakeSocket.instances[-1].disconnected is True


@pytest.mark.asyncio
@respx.mock
async def test_reports_when_the_request_was_no_longer_waiting() -> None:
    respx.get(BASE).mock(return_value=httpx.Response(200, json={**TOKEN_OBJECT, "listen": 10}))
    respx.put(BASE).mock(return_value=httpx.Response(200, json=TOKEN_OBJECT))
    respx.get(f"{BASE}/requests").mock(return_value=httpx.Response(200, json={"data": []}))
    respx.put(f"{BASE}/request/late/response").mock(return_value=httpx.Response(200, json={"status": 2}))
    respx.get(f"{BASE}/request/late").mock(return_value=httpx.Response(200, json=_web("late")))

    async def deliver() -> None:
        await asyncio.sleep(0.05)
        FakeSocket.instances[-1].push({"request": {"uuid": "late"}})

    async with WebhookHttpClient(api_key="k") as client:
        service = RequestService(client, socket_factory=_factory())
        task = asyncio.create_task(deliver())
        result = await service.respond_to_next_request(TOKEN, timeout_seconds=5)
        await task
    assert result.success is False and result.data["set_response_status"] == 2
    assert "no longer waiting" in result.message


@pytest.mark.asyncio
@respx.mock
async def test_falls_back_to_fast_polling_without_a_socket() -> None:
    respx.get(BASE).mock(return_value=httpx.Response(200, json=TOKEN_OBJECT))
    respx.put(BASE).mock(return_value=httpx.Response(200, json=TOKEN_OBJECT))
    respx.get(f"{BASE}/requests").mock(
        side_effect=[httpx.Response(200, json={"data": []}), httpx.Response(200, json={"data": [_web("polled")]})]
    )
    respx.put(f"{BASE}/request/polled/response").mock(return_value=httpx.Response(200, json={"status": 3}))
    respx.get(f"{BASE}/request/polled").mock(return_value=httpx.Response(200, json=_web("polled")))
    async with WebhookHttpClient() as client:
        result = await RequestService(client, socket_factory=_factory(fail_connect=True)).respond_to_next_request(
            TOKEN, timeout_seconds=5
        )
    assert result.success is True and result.data["listened_via"] == "poll"


@pytest.mark.asyncio
@respx.mock
async def test_configure_create_sets_listen_with_a_follow_up_put() -> None:
    respx.post(f"{WEBHOOK_SITE_API}/token").mock(return_value=httpx.Response(201, json={"uuid": TOKEN, "listen": 0}))
    put = respx.put(BASE).mock(return_value=httpx.Response(200, json={"uuid": TOKEN, "listen": 5}))
    async with WebhookHttpClient(api_key="k") as client:
        result = await WebhookService(client).configure(WebhookConfig(listen=5, default_status=201))
    assert put.called and json.loads(put.calls[0].request.content) == {"default_status": 201, "listen": 5}
    assert result.data["listen"] == 5
