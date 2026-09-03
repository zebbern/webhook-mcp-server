"""Offline tests for socket-first waiting with polling as a backstop."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
import respx

from services.request_service import RequestService
from utils.http_client import WEBHOOK_SITE_API, WebhookHttpClient
from utils.realtime import CREATED_EVENT, SocketWaiter

TOKEN = "550e8400-e29b-41d4-a716-446655440000"
BASE = f"{WEBHOOK_SITE_API}/token/{TOKEN}"


class FakeSocket:
    """Minimal python-socketio AsyncClient stand-in."""

    instances: list["FakeSocket"] = []

    def __init__(self, fail_connect: bool = False) -> None:
        self.handlers: dict[str, Any] = {}
        self.emitted: list[tuple[str, Any]] = []
        self.connected = False
        self.disconnected = False
        self.fail_connect = fail_connect
        FakeSocket.instances.append(self)

    def on(self, event: str, handler: Any) -> None:
        self.handlers[event] = handler

    async def connect(self, url: str, transports: list[str] | None = None) -> None:
        if self.fail_connect:
            raise ConnectionError("no socket")
        self.connected = True
        await self.handlers["connect"]()

    async def emit(self, event: str, data: Any) -> None:
        self.emitted.append((event, data))

    async def disconnect(self) -> None:
        self.disconnected = True

    def push(self, payload: dict[str, Any]) -> None:
        self.handlers[CREATED_EVENT](f"private-token.{TOKEN}", payload)


def _factory(**kwargs):
    return lambda: FakeSocket(**kwargs)


def _web(uuid: str) -> dict[str, Any]:
    return {"uuid": uuid, "type": "web", "method": "POST", "content": "{}"}


@pytest.fixture(autouse=True)
def _reset_fakes() -> None:
    FakeSocket.instances.clear()


@pytest.mark.asyncio
async def test_socket_waiter_subscribes_with_api_key_only_when_set() -> None:
    with_key = SocketWaiter(TOKEN, "secret", factory=_factory())
    assert await with_key.start(timeout=1) is True
    assert FakeSocket.instances[-1].emitted == [
        ("subscribe", {"channel": f"private-token.{TOKEN}", "auth": {"headers": {"Api-Key": "secret"}}})
    ]
    await with_key.close()
    assert FakeSocket.instances[-1].disconnected is True

    without = SocketWaiter(TOKEN, None, factory=_factory())
    assert await without.start(timeout=1) is True
    assert FakeSocket.instances[-1].emitted[0][1]["auth"] == {"headers": {}}
    await without.close()


@pytest.mark.asyncio
async def test_socket_waiter_reports_unavailable_without_raising() -> None:
    assert await SocketWaiter(TOKEN, None, factory=_factory(fail_connect=True)).start(timeout=1) is False

    def broken_factory():
        raise ImportError("python-socketio missing")

    assert await SocketWaiter(TOKEN, None, factory=broken_factory).start(timeout=1) is False


@pytest.mark.asyncio
@respx.mock
async def test_wait_for_request_returns_on_socket_event_without_polling() -> None:
    listing = respx.get(f"{BASE}/requests").mock(return_value=httpx.Response(200, json={"data": [_web("old")]}))
    fetch = respx.get(f"{BASE}/request/new").mock(return_value=httpx.Response(200, json=_web("new")))

    async def deliver() -> None:
        await asyncio.sleep(0.05)
        FakeSocket.instances[-1].push({"uuid": "new", "type": "web"})

    async with WebhookHttpClient(api_key="k") as client:
        service = RequestService(client, socket_factory=_factory())
        task = asyncio.create_task(deliver())
        result = await service.wait_for_request(TOKEN, timeout_seconds=5)
        await task
    assert result.success is True
    assert result.data["source"] == "socket"
    assert result.data["request"]["uuid"] == "new"
    assert listing.call_count == 1 and fetch.called
    assert FakeSocket.instances[-1].disconnected is True


@pytest.mark.asyncio
@respx.mock
async def test_wait_for_email_ignores_events_for_seen_or_other_types() -> None:
    respx.get(f"{BASE}/requests").mock(return_value=httpx.Response(200, json={"data": [_web("old")]}))
    respx.get(f"{BASE}/request/web2").mock(return_value=httpx.Response(200, json=_web("web2")))
    mail = {"uuid": "m1", "type": "email", "headers": {"subject": ["Hi"], "from": ["a@b"]}, "text_content": "code 123456"}
    respx.get(f"{BASE}/request/m1").mock(return_value=httpx.Response(200, json=mail))

    async def deliver() -> None:
        await asyncio.sleep(0.05)
        sock = FakeSocket.instances[-1]
        sock.push({"uuid": "old"})
        sock.push({"uuid": "web2"})
        sock.push({"uuid": "m1"})

    async with WebhookHttpClient() as client:
        service = RequestService(client, socket_factory=_factory())
        task = asyncio.create_task(deliver())
        result = await service.wait_for_email(TOKEN, timeout_seconds=5)
        await task
    assert result.data["source"] == "socket"
    assert result.data["email"]["subject"] == "Hi"
    assert result.data["email"]["verification_codes"] == ["123456"]


@pytest.mark.asyncio
@respx.mock
async def test_wait_for_request_falls_back_to_polling_when_socket_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    from services import request_service

    monkeypatch.setattr(request_service, "POLL_INTERVAL_SECONDS", 0.05)
    listing = respx.get(f"{BASE}/requests").mock(
        side_effect=[
            httpx.Response(200, json={"data": [_web("old")]}),
            httpx.Response(200, json={"data": [_web("old")]}),
            httpx.Response(200, json={"data": [_web("fresh"), _web("old")]}),
        ]
    )
    async with WebhookHttpClient() as client:
        service = RequestService(client, socket_factory=_factory(fail_connect=True))
        result = await service.wait_for_request(TOKEN, timeout_seconds=5)
    assert result.data["source"] == "poll"
    assert result.data["request"]["uuid"] == "fresh"
    assert listing.call_count == 3


@pytest.mark.asyncio
@respx.mock
async def test_wait_for_request_times_out_and_return_existing_short_circuits() -> None:
    respx.get(f"{BASE}/requests").mock(return_value=httpx.Response(200, json={"data": [_web("old")]}))
    async with WebhookHttpClient() as client:
        service = RequestService(client, socket_factory=_factory())
        existing = await service.wait_for_request(TOKEN, timeout_seconds=1, return_existing=True)
        timed_out = await service.wait_for_request(TOKEN, timeout_seconds=1)
    assert existing.data["source"] == "existing" and existing.data["waited"] is False
    assert timed_out.success is False and timed_out.data["timeout"] is True
