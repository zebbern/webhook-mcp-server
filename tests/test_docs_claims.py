"""Behaviour taken from the webhook.site docs sweep, each item checked live on 2026-09-03 before it was coded.

Live findings this file guards:
- emailhook.site is the current mail domain (an email sent there arrived; destinations showed emailhook.site)
- POST https://webhook.site/{token}/503 answers 503; the subdomain form captures too
- PUT /token/{id} with alias null removes the alias
- request_limit 20000 was accepted on a Pro token (the old client cap of 10000 was wrong)
- PUT /token/{id}/request/{rid} rejects notes over 10000 characters (422)
- a custom action PUT without `name` clears the name; test-action with action_id does NOT change the saved action
- schedules accept require_cert_expiry (days); null clears it
- set_variable has modes math and random_number; `conditions` accepts regex/nex/null/nnull, `condition` does not
- database actions accept type whdb with db_id
- every documented WebhookScript function name except base64_urlencode and number_length exists on the engine
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from models.schemas import WebhookConfig
from services.actions_service import ActionsService
from services.schedule_service import ScheduleService
from services.webhook_service import WebhookService, build_webhook_urls
from utils import action_types, webhookscript
from utils.http_client import WEBHOOK_SITE_API, WebhookHttpClient
from utils.validation import ValidationError, validate_note, validate_request_limit

TOKEN = "550e8400-e29b-41d4-a716-446655440000"
BASE = f"{WEBHOOK_SITE_API}/token/{TOKEN}"
TOKEN_OBJECT = {
    "uuid": TOKEN, "alias": "old-alias", "default_status": 200, "default_content": "", "default_content_type": "text/html",
    "timeout": 0, "cors": False, "listen": 0, "actions": True, "request_limit": 100, "premium": True, "description": None,
}


# --- URLs -------------------------------------------------------------------


def test_urls_use_the_current_mail_domain_and_expose_the_force_status_form() -> None:
    urls = build_webhook_urls(TOKEN, alias="my-alias")
    assert urls["email"] == f"{TOKEN}@emailhook.site"
    assert urls["force_status_url"] == f"{WEBHOOK_SITE_API}/my-alias/{{status}}"
    assert urls["subdomain_url"] == f"https://{TOKEN}.webhook.site"


# --- alias clearing ---------------------------------------------------------


def test_empty_alias_becomes_null_in_the_payload() -> None:
    assert WebhookConfig(alias="").to_payload() == {"alias": None}
    assert WebhookConfig(alias="keep").to_payload() == {"alias": "keep"}
    assert "alias" not in WebhookConfig().to_payload()


@pytest.mark.asyncio
@respx.mock
async def test_update_with_empty_alias_sends_null_and_keeps_other_settings() -> None:
    respx.get(BASE).mock(return_value=httpx.Response(200, json=TOKEN_OBJECT))
    put = respx.put(BASE).mock(return_value=httpx.Response(200, json={**TOKEN_OBJECT, "alias": None}))
    async with WebhookHttpClient(api_key="k") as client:
        result = await WebhookService(client).configure(WebhookConfig(alias=""), webhook_token=TOKEN)
    body = json.loads(put.calls[0].request.content)
    assert body["alias"] is None
    assert body["default_status"] == 200 and body["request_limit"] == 100
    assert result.data["alias"] is None


# --- limits -----------------------------------------------------------------


def test_request_limit_allows_plan_ceilings_above_10000() -> None:
    validate_request_limit(20000)
    validate_request_limit(100000)
    with pytest.raises(ValidationError):
        validate_request_limit(100001)


def test_note_length_matches_the_api_cap() -> None:
    validate_note("x" * 10000)
    with pytest.raises(ValidationError, match="10000"):
        validate_note("x" * 10001)


# --- custom action names ----------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_update_keeps_the_saved_action_name_and_can_rename() -> None:
    saved = {"uuid": "a1", "type": "log", "order": 1, "parameters": {"text": "a"}, "name": "keep me",
             "disabled": False, "queue": False, "delay": 0, "condition": None, "queue_id": None}
    respx.get(f"{BASE}/actions").mock(return_value=httpx.Response(200, json={"data": [saved]}))
    put = respx.put(f"{BASE}/actions/a1").mock(return_value=httpx.Response(200, json=saved))
    async with WebhookHttpClient(api_key="k") as client:
        svc = ActionsService(client)
        await svc.update(TOKEN, "a1", parameters={"text": "b"})
        await svc.update(TOKEN, "a1", name="renamed")
    first, second = (json.loads(call.request.content) for call in put.calls)
    assert first["name"] == "keep me" and first["parameters"] == {"text": "b"}
    assert second["name"] == "renamed"


@pytest.mark.asyncio
@respx.mock
async def test_create_sends_the_name() -> None:
    post = respx.post(f"{BASE}/actions").mock(return_value=httpx.Response(201, json={"uuid": "a2", "name": "n"}))
    async with WebhookHttpClient(api_key="k") as client:
        await ActionsService(client).create(TOKEN, type="log", parameters={"text": "x"}, name="n")
    assert json.loads(post.calls[0].request.content)["name"] == "n"


# --- schedules --------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_schedule_create_and_update_carry_require_cert_expiry() -> None:
    post = respx.post(f"{WEBHOOK_SITE_API}/schedules").mock(return_value=httpx.Response(201, json={"id": 7, "name": "s"}))
    respx.get(f"{WEBHOOK_SITE_API}/schedules/7").mock(return_value=httpx.Response(200, json={
        "id": 7, "name": "s", "interval": "daily", "request_url": "https://example.com", "request_method": "GET",
        "timeout": 5, "require_cert_expiry": 30}))
    put = respx.put(f"{WEBHOOK_SITE_API}/schedules/7").mock(return_value=httpx.Response(200, json={"id": 7}))
    async with WebhookHttpClient(api_key="k") as client:
        svc = ScheduleService(client)
        await svc.create(name="s", interval="daily", request_url="https://example.com", request_method="GET", timeout=5, require_cert_expiry=30)
        await svc.update(7, name="s2")
    assert json.loads(post.calls[0].request.content)["require_cert_expiry"] == 30
    merged = json.loads(put.calls[0].request.content)
    assert merged["require_cert_expiry"] == 30 and merged["name"] == "s2"


# --- action type reference --------------------------------------------------


def test_reference_carries_the_frontend_and_live_findings() -> None:
    set_variable = action_types.describe("set_variable")
    assert set_variable["params"]["mode"]["in"] == ["text", "random", "random_number", "date", "math"]
    assert "random_number.*.from" in set_variable["params"]
    conditions = action_types.describe("conditions")
    assert conditions["params"]["conditions.*.operator"]["in"][-4:] == ["nex", "null", "nnull", "regex"]
    condition = action_types.describe("condition")
    assert "regex" not in condition["params"]["operator"]["in"] and "Unknown operator" in condition["note"]
    assert action_types.describe("text_map")["params"]["operator"]["in"][:2] == ["eq", "neq"]
    database = action_types.describe("database")
    assert "whdb" in database["params"]["type"]["in"] and "db_id" in database["params"]
    assert "Legacy" in action_types.describe("send_request")["note"]
    assert "queue" in action_types.describe("modify_response")["note"]


# --- WebhookScript reference ------------------------------------------------


def test_webhookscript_reference_lists_verified_functions() -> None:
    full = webhookscript.reference()
    names = {f["name"] for f in full["functions"]}
    assert full["count"] >= 136 and {"var", "set", "store", "respond", "json_path", "http", "db", "get", "length"} <= names
    assert full["verified_at"] is not None
    missing = {f["name"] for f in full["functions"] if f.get("exists_live") is False}
    assert missing == {"base64_urlencode", "number_length"}
    string_replace = next(f for f in full["functions"] if f["name"] == "string_replace")
    assert " | " in string_replace["signature"] and string_replace["group"] == "string"
    assert any("var('request.content')" in note for note in full["language_notes"])


def test_webhookscript_reference_filters() -> None:
    only_dates = webhookscript.reference(group="date")
    assert {f["group"] for f in only_dates["functions"]} == {"date"}
    found = webhookscript.reference(search="jsonpath")
    assert {f["name"] for f in found["functions"]} >= {"json_path"}
    with pytest.raises(ValidationError, match="Groups"):
        webhookscript.reference(group="nope")


@pytest.mark.asyncio
async def test_script_reference_tool_action() -> None:
    import server

    tool = server.mcp._tool_manager.get_tool("manage_custom_actions")  # type: ignore[attr-defined]
    ctx = type("Ctx", (), {"request_context": type("RC", (), {"lifespan_context": None})()})()
    result = await tool.run({"action": "script_reference", "search": "base64"}, context=ctx)
    assert result["success"] is True
    names = {f["name"] for f in result["functions"]}
    assert {"base64_encode", "base64_decode", "base64url_encode"} <= names
    assert "verified live" in result["message"]
