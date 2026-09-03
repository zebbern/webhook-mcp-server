"""Offline unit tests — no webhook.site network access."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from models.schemas import ToolResult
from services.bugbounty_service import BugBountyService
from services.request_service import (
    BODY_PREVIEW_CHARS,
    RequestService,
    preview_body,
)
from services.webhook_service import WebhookService
from utils.email_extract import extract_verification_codes
from utils.http_client import WEBHOOK_SITE_API, WebhookHttpClient
from utils.safe_url import ensure_public_http_url
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
    expected = {
        "server_status",
        "create_webhook",
        "configure_webhook",
        "get_webhook_info",
        "get_webhook_email",
        "list_webhooks",
        "delete_webhook",
        "get_webhook_requests",
        "search_requests",
        "get_request",
        "update_request",
        "download_request_file",
        "delete_request",
        "delete_all_requests",
        "export_webhook_data",
        "wait_for_request",
        "wait_for_email",
        "follow_email_link",
        "manage_custom_actions",
        "manage_schedules",
        "manage_global_variables",
        "manage_groups",
        "manage_templates",
        "manage_databases",
        "manage_users",
        "generate_oob_payloads",
        "check_for_callbacks",
        "extract_links_from_request",
        "send_requests",
    }
    assert set(names) == expected
    assert len(names) == 29
    for removed in ("get_webhook_url", "get_webhook_dns", "get_latest_request", "generate_ssrf_payload"):
        assert removed not in names
    annotated = {tool.name: tool.annotations for tool in tools}
    assert annotated["delete_webhook"].destructive_hint is True
    assert annotated["get_webhook_info"].read_only_hint is True
    assert annotated["manage_schedules"].destructive_hint is True
    assert all(annotation is not None for annotation in annotated.values())


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
    assert "verification_codes" in wait or "otp" in wait
    assert "follow_email_link" in wait

    follow = tools["follow_email_link"]
    assert "verify" in follow or "magic" in follow
    assert "wait_for_email" in follow

    links = tools["extract_links_from_request"]
    assert "magic" in links or "reset" in links
    assert "verify" in links or "confirm" in links

    configure = tools["configure_webhook"]
    assert "alias" in configure and "expiry" in configure and "request_limit" in configure

    oob = tools["generate_oob_payloads"]
    assert "ssrf" in oob and "xss" in oob and "canary" in oob

    actions = tools["manage_custom_actions"]
    assert "$request.type$" in actions


CATALOG_TOKEN_BUDGET = 9000


@pytest.mark.asyncio
async def test_tool_catalog_stays_under_token_budget() -> None:
    import server
    import tiktoken

    catalog = []
    for tool in await server.mcp.list_tools():
        payload = tool.model_dump()
        catalog.append(
            {
                "name": payload.get("name"),
                "description": payload.get("description") or "",
                "inputSchema": payload.get("inputSchema") or payload.get("input_schema") or {},
            }
        )
    blob = json.dumps(catalog, ensure_ascii=False)
    tokens = len(tiktoken.get_encoding("cl100k_base").encode(blob))
    assert tokens <= CATALOG_TOKEN_BUDGET, (
        f"tool catalog is {tokens} tokens (budget {CATALOG_TOKEN_BUDGET})"
    )


def test_preview_body_truncates() -> None:
    assert preview_body(None) is None
    assert preview_body("short") == "short"
    long_body = "x" * (BODY_PREVIEW_CHARS + 50)
    preview = preview_body(long_body)
    assert preview is not None
    assert preview.startswith("x" * BODY_PREVIEW_CHARS)
    assert "export_webhook_data" in preview
    assert len(preview) < len(long_body) + 80


def test_format_request_omits_html_and_truncates() -> None:
    service = RequestService(client=None)  # type: ignore[arg-type]
    formatted = service._format_request(
        {
            "uuid": "req-1",
            "type": "email",
            "method": "POST",
            "content": "y" * (BODY_PREVIEW_CHARS + 10),
            "text_content": "plain",
            "html_content": "<html>huge</html>",
            "headers": {"from": ["a@b.test"]},
            "query": {},
            "url": "https://webhook.site/x",
            "ip": "1.2.3.4",
            "created_at": "2026-01-01 00:00:00",
        }
    )
    assert "html_content" not in formatted
    assert formatted["html_omitted"] is True
    assert formatted["text_content"] == "plain"
    assert "export_webhook_data" in formatted["content"]


def test_format_email_keeps_links_without_html() -> None:
    service = RequestService(client=None)  # type: ignore[arg-type]
    email = service._format_email(
        {
            "uuid": "mail-1",
            "text_content": "Click https://example.com/verify?token=abc",
            "html_content": '<a href="https://example.com/magic?x=1">login</a>',
            "headers": {"from": ["noreply@example.com"], "subject": ["Verify"]},
            "created_at": "2026-01-01 00:00:00",
        },
        extract_links=True,
    )
    assert "html_content" not in email
    assert email["html_omitted"] is True
    assert "https://example.com/verify?token=abc" in email["all_links"]
    assert "https://example.com/magic?x=1" in email["all_links"]
    assert email["auth_links"]
    assert email["verification_codes"] == []


def test_extract_verification_codes_ignores_url_digits() -> None:
    text = (
        "Your code is 847291. Ignore https://example.com/reset?token=111222 "
        "and year 2026."
    )
    assert extract_verification_codes(text) == ["847291"]


def test_format_email_includes_otp() -> None:
    service = RequestService(client=None)  # type: ignore[arg-type]
    email = service._format_email(
        {
            "uuid": "mail-2",
            "text_content": "OTP: 442211 https://example.com/login?token=zz",
            "headers": {"from": ["noreply@example.com"], "subject": ["Code"]},
            "created_at": "2026-01-01 00:00:00",
        },
        extract_links=True,
    )
    assert email["verification_codes"] == ["442211"]
    assert email["auth_links"]


def test_ensure_public_http_url_blocks_localhost() -> None:
    with pytest.raises(ValidationError):
        ensure_public_http_url("http://localhost/verify")
    with pytest.raises(ValidationError):
        ensure_public_http_url("http://127.0.0.1/verify")
    with pytest.raises(ValidationError):
        ensure_public_http_url("ftp://example.com/verify")


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
async def test_get_email_validate_missing_token_serializes() -> None:
    respx.get(f"{WEBHOOK_SITE_API}/token/{TOKEN}").mock(
        return_value=httpx.Response(404, text="not found")
    )
    async with WebhookHttpClient() as client:
        service = WebhookService(client)
        result = await service.get_email(TOKEN, validate=True)
    payload = json.loads(result.to_json())
    assert payload["success"] is False
    assert "not found" in payload["message"].lower()


@pytest.mark.asyncio
@respx.mock
async def test_export_keeps_full_html_and_body() -> None:
    huge_html = "<html>" + ("z" * (BODY_PREVIEW_CHARS + 20)) + "</html>"
    respx.get(f"{WEBHOOK_SITE_API}/token/{TOKEN}/requests").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        **_request_json("full-1"),
                        "content": "y" * (BODY_PREVIEW_CHARS + 10),
                        "html_content": huge_html,
                    }
                ]
            },
        )
    )
    async with WebhookHttpClient() as client:
        service = RequestService(client)
        result = await service.export_requests(TOKEN, limit=1)
    assert result.success is True
    exported = result.data["requests"][0]
    assert exported["html_content"] == huge_html
    assert exported["content"] == "y" * (BODY_PREVIEW_CHARS + 10)
    assert "truncated" not in exported["content"]


def _email_json(uuid: str, text: str, html: str = "") -> dict:
    return {
        "uuid": uuid,
        "type": "email",
        "method": "POST",
        "content": "",
        "text_content": text,
        "html_content": html,
        "headers": {"from": ["noreply@example.com"], "subject": ["Verify"]},
        "query": {},
        "url": "",
        "ip": "1.2.3.4",
        "created_at": "2026-01-01 00:00:00",
    }


@pytest.mark.asyncio
@respx.mock
async def test_follow_email_link_opens_captured_auth_url() -> None:
    verify = "https://example.com/verify?token=abc"
    respx.get(f"{WEBHOOK_SITE_API}/token/{TOKEN}/requests").mock(
        return_value=httpx.Response(
            200,
            json={"data": [_email_json("mail-1", f"Click {verify}")]},
        )
    )
    respx.get(verify).mock(
        return_value=httpx.Response(200, text="<html><title>Verified</title><body>ok</body></html>")
    )
    async with WebhookHttpClient() as client:
        service = RequestService(client)
        result = await service.follow_email_link(TOKEN)
    assert result.success is True
    assert result.data["opened_url"] == verify
    assert result.data["status_code"] == 200
    assert result.data["title"] == "Verified"


@pytest.mark.asyncio
@respx.mock
async def test_follow_email_link_rejects_url_not_in_email() -> None:
    respx.get(f"{WEBHOOK_SITE_API}/token/{TOKEN}/requests").mock(
        return_value=httpx.Response(
            200,
            json={"data": [_email_json("mail-1", "Click https://example.com/verify?token=abc")]},
        )
    )
    async with WebhookHttpClient() as client:
        service = RequestService(client)
        with pytest.raises(ValidationError, match="not found"):
            await service.follow_email_link(TOKEN, url="https://evil.example/phish")
