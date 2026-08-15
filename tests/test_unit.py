"""Offline unit tests — no webhook.site network access."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from models.schemas import ToolResult
from services.bugbounty_service import BugBountyService
from services.request_service import RequestService
from services.webhook_service import WebhookService
from utils.http_client import WEBHOOK_SITE_API, WebhookHttpClient
from utils.validation import ValidationError, validate_webhook_token

TOKEN = "550e8400-e29b-41d4-a716-446655440000"


def test_tool_result_none_data_serializes() -> None:
    result = ToolResult(success=False, message="Token not found", data=None)  # type: ignore[arg-type]
    payload = json.loads(result.to_json())
    assert payload["success"] is False
    assert payload["message"] == "Token not found"


def test_invalid_webhook_token_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_webhook_token("not-a-uuid")
    with pytest.raises(ValidationError):
        validate_webhook_token("")
    validate_webhook_token(TOKEN)


def test_ssrf_payloads_are_split() -> None:
    service = BugBountyService(client=None)  # type: ignore[arg-type]
    result = service.generate_ssrf_payload(TOKEN, include_dns=True, include_ip=True)
    assert result.success is True
    callbacks = result.data["callback_payloads"]
    local = result.data["local_bypass_examples"]
    assert "https_url" in callbacks
    assert "dns_payload" in callbacks
    assert "decimal_ip" in local
    assert "localhost_bypass" in local
    assert "decimal_ip" not in callbacks


@pytest.mark.asyncio
async def test_import_server_and_list_tools() -> None:
    import server

    tools = await server.mcp.list_tools()
    names = [tool.name for tool in tools]
    assert "create_webhook" in names
    assert "get_latest_request" in names
    assert "get_webhook_dns" in names
    assert "get_webhook_email" in names
    assert "wait_for_email" in names
    assert len(names) == 23


@pytest.mark.asyncio
async def test_tool_descriptions_cover_signup_and_email() -> None:
    import server

    tools = {tool.name: (tool.description or "").lower() for tool in await server.mcp.list_tools()}

    create = tools["create_webhook"]
    assert "sign up" in create
    assert "email" in create
    assert "wait_for_email" in create

    inbox = tools["get_webhook_email"]
    assert "sign up" in inbox
    assert "magic" in inbox
    assert "password" in inbox
    assert "wait_for_email" in inbox

    wait = tools["wait_for_email"]
    assert "sign-up" in wait or "sign up" in wait
    assert "magic" in wait
    assert "password-reset" in wait or "password" in wait
    assert "create_webhook" in wait

    links = tools["extract_links_from_request"]
    assert "magic" in links or "reset" in links
    assert "verify" in links or "confirm" in links


@pytest.mark.asyncio
async def test_get_webhook_dns_rejects_invalid_token() -> None:
    from handlers.tools import _execute
    from utils.validation import validate_webhook_token as validate

    def _op():
        validate("not-a-uuid")
        raise AssertionError("should not reach service")

    payload = await _execute(_op)
    assert payload["success"] is False
    assert "Validation Error" in payload["message"]


def _request_json(uuid: str, request_type: str = "web") -> dict:
    return {
        "uuid": uuid,
        "type": request_type,
        "method": "POST",
        "content": "{}",
        "headers": {},
        "query": {},
        "url": f"{WEBHOOK_SITE_API}/{TOKEN}",
        "ip": "1.2.3.4",
        "created_at": "2026-01-01 00:00:00",
    }


@pytest.mark.asyncio
@respx.mock
async def test_wait_for_request_ignores_existing_by_default() -> None:
    existing = _request_json("old-request")
    respx.get(f"{WEBHOOK_SITE_API}/token/{TOKEN}/requests").mock(
        return_value=httpx.Response(200, json={"data": [existing]})
    )
    async with WebhookHttpClient() as client:
        service = RequestService(client)
        result = await service.wait_for_request(TOKEN, timeout_seconds=1)
    assert result.success is False
    assert result.data.get("timeout") is True


@pytest.mark.asyncio
@respx.mock
async def test_wait_for_request_return_existing() -> None:
    existing = _request_json("old-request")
    respx.get(f"{WEBHOOK_SITE_API}/token/{TOKEN}/requests").mock(
        return_value=httpx.Response(200, json={"data": [existing]})
    )
    async with WebhookHttpClient() as client:
        service = RequestService(client)
        result = await service.wait_for_request(TOKEN, timeout_seconds=1, return_existing=True)
    assert result.success is True
    assert result.data["waited"] is False
    assert result.data["request"]["uuid"] == "old-request"


@pytest.mark.asyncio
@respx.mock
async def test_get_url_validate_missing_token_serializes() -> None:
    respx.get(f"{WEBHOOK_SITE_API}/token/{TOKEN}").mock(
        return_value=httpx.Response(404, text="not found")
    )
    async with WebhookHttpClient() as client:
        service = WebhookService(client)
        result = await service.get_url(TOKEN, validate=True)
    payload = json.loads(result.to_json())
    assert payload["success"] is False
    assert "not found" in payload["message"].lower()
