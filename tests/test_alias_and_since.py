"""Aliases (and pasted URLs / addresses) resolve to the token; `since` is a sorting cursor.

Live facts behind these tests (2026-09-03):
- GET /token/{alias} answers 200 with the token object although the docs say aliases are not
  accepted in API URLs; GET /token/{alias}/requests really does 404.
- query `sorting:>N` returned exactly the requests created after the one with sorting N.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from models.app_context import AppContext
from models.schemas import SearchFilters, with_since
from services.account_service import AccountService
from services.actions_service import ActionsService
from services.bugbounty_service import BugBountyService
from services.database_service import DatabaseService
from services.request_service import RequestService
from services.schedule_service import ScheduleService
from services.webhook_service import WebhookService
from utils.http_client import WEBHOOK_SITE_API, WebhookHttpClient
from utils.validation import extract_token_reference, looks_like_alias, looks_like_uuid

TOKEN = "550e8400-e29b-41d4-a716-446655440000"
ALIAS = "my-alias_1"
TOKEN_OBJECT = {"uuid": TOKEN, "alias": ALIAS, "premium": True, "default_status": 200, "request_limit": 100}


@pytest.mark.parametrize(
    "value,expected",
    [
        (TOKEN, TOKEN),
        (ALIAS, ALIAS),
        (f"  {ALIAS} ", ALIAS),
        (f"https://webhook.site/{TOKEN}", TOKEN),
        (f"https://webhook.site/{ALIAS}/api/v1/hook?x=1", ALIAS),
        (f"http://webhook.site:443/{TOKEN}#frag", TOKEN),
        (f"https://{TOKEN}.webhook.site/anything", TOKEN),
        (f"{TOKEN}@emailhook.site", TOKEN),
        (f"{ALIAS}@email.webhook.site", ALIAS),
        (f"Signup <{TOKEN}@emailhook.site>", TOKEN),
        (f"{TOKEN}.dnshook.site", TOKEN),
        (f"sub.{TOKEN}.dnshook.site", TOKEN),
        (f"https://exfil.{TOKEN}.dnshook.site", TOKEN),
        ("https://example.com/not-a-token", "https://example.com/not-a-token"),
        ("someone@example.com", "someone@example.com"),
    ],
)
def test_extract_token_reference(value: str, expected: str) -> None:
    assert extract_token_reference(value) == expected


def test_alias_and_uuid_detection() -> None:
    assert looks_like_uuid(TOKEN) and not looks_like_alias(TOKEN)
    assert looks_like_alias(ALIAS) and looks_like_alias("abc") and looks_like_alias("a" * 32)
    assert not looks_like_alias("ab") and not looks_like_alias("a" * 33) and not looks_like_alias("has space")


def _ctx(client: WebhookHttpClient) -> object:
    app = AppContext(
        client=client,
        webhooks=WebhookService(client),
        requests=RequestService(client),
        bounty=BugBountyService(client),
        account=AccountService(client),
        actions=ActionsService(client),
        schedules=ScheduleService(client),
        databases=DatabaseService(client),
    )
    return type("Ctx", (), {"request_context": type("RC", (), {"lifespan_context": app})()})()


async def _run(tool: str, args: dict) -> dict:
    import server

    registered = server.mcp._tool_manager.get_tool(tool)  # type: ignore[attr-defined]
    async with WebhookHttpClient(api_key="k") as client:
        return await registered.run(args, context=_ctx(client))


@pytest.mark.asyncio
@respx.mock
async def test_alias_is_resolved_with_one_get_then_the_uuid_is_used() -> None:
    by_alias = respx.get(f"{WEBHOOK_SITE_API}/token/{ALIAS}").mock(return_value=httpx.Response(200, json=TOKEN_OBJECT))
    by_uuid = respx.get(f"{WEBHOOK_SITE_API}/token/{TOKEN}").mock(return_value=httpx.Response(200, json=TOKEN_OBJECT))
    result = await _run("get_webhook_info", {"webhook_token": ALIAS})
    assert result["success"] is True and result["token"] == TOKEN
    assert by_alias.call_count == 1 and by_uuid.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_pasted_url_and_email_forms_work_and_a_uuid_costs_no_lookup() -> None:
    respx.get(f"{WEBHOOK_SITE_API}/token/{TOKEN}").mock(return_value=httpx.Response(200, json=TOKEN_OBJECT))
    listing = respx.get(f"{WEBHOOK_SITE_API}/token/{TOKEN}/requests").mock(return_value=httpx.Response(200, json={"data": []}))
    for value in (f"https://webhook.site/{TOKEN}", f"{TOKEN}@emailhook.site", TOKEN):
        result = await _run("get_webhook_requests", {"webhook_token": value})
        assert result["success"] is True, result
    assert listing.call_count == 3
    assert not any(str(call.request.url).endswith(f"/token/{TOKEN}") for call in listing.calls)


@pytest.mark.asyncio
@respx.mock
async def test_unknown_alias_and_garbage_are_validation_errors() -> None:
    respx.get(f"{WEBHOOK_SITE_API}/token/nope-alias").mock(
        return_value=httpx.Response(404, json={"success": False, "error": {"message": "Token not found"}})
    )
    missing = await _run("get_webhook_info", {"webhook_token": "nope-alias"})
    assert missing["success"] is False and "No webhook with alias 'nope-alias'" in missing["message"]
    garbage = await _run("get_webhook_info", {"webhook_token": "https://example.com/x y"})
    assert garbage["success"] is False and "Invalid webhook token" in garbage["message"]


@pytest.mark.asyncio
@respx.mock
async def test_optional_token_tools_still_work_without_one() -> None:
    result = await _run("manage_custom_actions", {"action": "types", "type": "log"})
    assert result["success"] is True and result["type"] == "log"


@pytest.mark.asyncio
@respx.mock
async def test_update_on_an_aliased_token_reports_the_alias_cache() -> None:
    respx.get(f"{WEBHOOK_SITE_API}/token/{ALIAS}").mock(return_value=httpx.Response(200, json=TOKEN_OBJECT))
    respx.get(f"{WEBHOOK_SITE_API}/token/{TOKEN}").mock(return_value=httpx.Response(200, json=TOKEN_OBJECT))
    respx.put(f"{WEBHOOK_SITE_API}/token/{TOKEN}").mock(return_value=httpx.Response(200, json={**TOKEN_OBJECT, "default_status": 203}))
    result = await _run("configure_webhook", {"webhook_token": ALIAS, "default_status": 203})
    assert result["success"] is True and "2 minutes" in result["alias_cache_note"]
    respx.put(f"{WEBHOOK_SITE_API}/token/{TOKEN}").mock(return_value=httpx.Response(200, json={**TOKEN_OBJECT, "alias": None}))
    plain = await _run("configure_webhook", {"webhook_token": TOKEN, "alias": ""})
    assert plain["success"] is True and "alias_cache_note" not in plain


# --- since cursor -----------------------------------------------------------


def test_with_since_wraps_an_existing_query() -> None:
    assert with_since(None, 5) == "sorting:>5"
    assert with_since("method:POST OR method:PUT", 5) == "(method:POST OR method:PUT) AND sorting:>5"
    assert SearchFilters(request_type="email", query="content:x", since=9).to_params()["query"] == "(type:email content:x) AND sorting:>9"


@pytest.mark.asyncio
@respx.mock
async def test_get_all_passes_the_cursor_and_returns_the_next_one() -> None:
    route = respx.get(f"{WEBHOOK_SITE_API}/token/{TOKEN}/requests").mock(
        return_value=httpx.Response(200, json={"data": [
            {"uuid": "a", "sorting": 1788472548588803, "method": "POST"},
            {"uuid": "b", "sorting": 1788472548944304, "method": "POST"},
        ], "is_last_page": True})
    )
    async with WebhookHttpClient() as client:
        result = await RequestService(client).get_all(TOKEN, 10, None, page=1, since=1788472548220448)
    assert route.calls[0].request.url.params["query"] == "sorting:>1788472548220448"
    assert result.data["next_since"] == 1788472548944304
    assert result.data["requests"][0]["sorting"] == 1788472548588803


@pytest.mark.asyncio
@respx.mock
async def test_empty_page_keeps_the_cursor() -> None:
    respx.get(f"{WEBHOOK_SITE_API}/token/{TOKEN}/requests").mock(return_value=httpx.Response(200, json={"data": [], "is_last_page": True}))
    async with WebhookHttpClient() as client:
        result = await RequestService(client).get_all(TOKEN, 10, None, since=42)
        untouched = await RequestService(client).get_all(TOKEN, 10, None)
    assert result.data["next_since"] == 42
    assert untouched.data["next_since"] is None
