"""The API key must never reach a capture URL or a recording.

Background (2026-09-04): send_requests used the API client for the capture URL, so
webhook.site stored the Api-Key header with the captured request and the live
recordings copied it. Two guards now: capture-URL sends use a keyless client, and
the recorder redacts the active key wherever it appears.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from services.request_service import RequestService
from services.webhook_service import WebhookService
from utils import recorder
from utils.http_client import WEBHOOK_SITE_API, WebhookHttpClient

TOKEN = "550e8400-e29b-41d4-a716-446655440000"
KEY = "11111111-2222-4333-8444-555555555555"


@pytest.mark.asyncio
@respx.mock
async def test_capture_url_requests_carry_no_api_key_but_api_calls_do() -> None:
    capture = respx.route(url=f"{WEBHOOK_SITE_API}/{TOKEN}").mock(return_value=httpx.Response(404, text="configured 404"))
    api = respx.get(f"{WEBHOOK_SITE_API}/token/{TOKEN}").mock(return_value=httpx.Response(200, json={"uuid": TOKEN}))
    async with WebhookHttpClient(api_key=KEY) as client:
        sent = await WebhookService(client).send_data(TOKEN, {"a": 1}, headers={"X-Test": "1"})
        multi = await RequestService(client).send_multiple(TOKEN, [{"b": 2}], method="PUT")
        await client.get(f"/token/{TOKEN}")
    for call in capture.calls:
        assert "api-key" not in {k.lower() for k in call.request.headers}
    assert capture.calls[0].request.headers["X-Test"] == "1"
    assert api.calls[0].request.headers["Api-Key"] == KEY
    assert sent.success is True and sent.data["status_code"] == 404
    assert multi.success is True


def test_recorder_redacts_the_active_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBHOOK_SITE_API_KEY", KEY)
    payload = {"headers": {"api-key": [KEY]}, "text": f"Api-Key: {KEY} and more", "nested": [KEY]}
    clean = recorder.sanitize(payload)
    assert KEY not in str(clean)
    assert clean["headers"]["api-key"] == [recorder.REDACTED_API_KEY]
    assert clean["text"].startswith("Api-Key: 00000000-0000-4000-8000-0000000000ee")


def test_recorder_leaves_values_alone_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEBHOOK_SITE_API_KEY", raising=False)
    assert recorder.sanitize({"k": KEY}) == {"k": KEY}
