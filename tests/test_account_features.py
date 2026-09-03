"""Offline tests for the 3.0 account features: pagination, raw downloads, new services and tools."""

from __future__ import annotations

import base64
import json

import httpx
import pytest
import respx

from models.schemas import WebhookConfig
from services.account_service import AccountService
from services.actions_service import ActionsService
from services.bugbounty_service import BugBountyService
from services.database_service import DatabaseService
from services.request_service import RequestService
from services.schedule_service import ScheduleService
from services.webhook_service import WebhookService
from utils.http_client import WEBHOOK_SITE_API, WebhookApiError, WebhookHttpClient
from utils.validation import ValidationError, resolve_default_expiry

TOKEN = "550e8400-e29b-41d4-a716-446655440000"
BASE = f"{WEBHOOK_SITE_API}/token/{TOKEN}"


def _page(items: list, page: int, last_page: int, **extra) -> dict:
    return {
        "data": items,
        "current_page": page,
        "last_page": last_page,
        "next_page_url": None if page >= last_page else f"{WEBHOOK_SITE_API}/x?page={page + 1}",
        "per_page": len(items),
        **extra,
    }


# --- http client ----------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_paginate_walks_pages_until_last_page() -> None:
    route = respx.get(f"{WEBHOOK_SITE_API}/groups")
    route.side_effect = [
        httpx.Response(200, json=_page([{"id": 1}], 1, 3, total=3)),
        httpx.Response(200, json=_page([{"id": 2}], 2, 3, total=3)),
        httpx.Response(200, json=_page([{"id": 3}], 3, 3, total=3)),
    ]
    async with WebhookHttpClient() as client:
        items, pagination = await client.paginate("/groups", delay=0)
    assert [item["id"] for item in items] == [1, 2, 3]
    assert pagination["pages_fetched"] == 3
    assert pagination["is_last_page"] is True
    assert pagination["truncated"] is False
    assert route.calls[1].request.url.params["page"] == "2"


@pytest.mark.asyncio
@respx.mock
async def test_paginate_stops_on_is_last_page_and_caps_items() -> None:
    respx.get(f"{BASE}/requests").mock(
        side_effect=[
            httpx.Response(200, json={"data": [{"uuid": "a"}, {"uuid": "b"}], "is_last_page": False, "total": 5}),
            httpx.Response(200, json={"data": [{"uuid": "c"}, {"uuid": "d"}], "is_last_page": False, "total": 5}),
            httpx.Response(200, json={"data": [{"uuid": "e"}], "is_last_page": True, "total": 5}),
        ]
    )
    async with WebhookHttpClient() as client:
        items, pagination = await client.paginate(f"/token/{TOKEN}/requests", max_items=3, delay=0)
    assert [item["uuid"] for item in items] == ["a", "b", "c"]
    assert pagination["truncated"] is True
    assert pagination["total"] == 5


@pytest.mark.asyncio
@respx.mock
async def test_get_raw_caps_body_and_reports_content_type() -> None:
    respx.get(f"{BASE}/requests/export").mock(
        return_value=httpx.Response(200, content=b"a,b\n" * 100, headers={"content-type": "text/csv"})
    )
    async with WebhookHttpClient() as client:
        body = await client.get_raw(f"/token/{TOKEN}/requests/export", accept="text/csv", max_bytes=40)
    assert len(body.content) == 40
    assert body.truncated is True
    assert body.content_type == "text/csv"


@pytest.mark.asyncio
@respx.mock
async def test_delete_raises_on_http_error() -> None:
    respx.delete(f"{BASE}").mock(return_value=httpx.Response(404, text="gone"))
    async with WebhookHttpClient() as client:
        with pytest.raises(WebhookApiError) as info:
            await client.delete(f"/token/{TOKEN}")
    assert info.value.status_code == 404


# --- webhook service --------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_configure_creates_with_default_expiry_when_unset() -> None:
    route = respx.post(f"{WEBHOOK_SITE_API}/token").mock(
        return_value=httpx.Response(201, json={"uuid": TOKEN, "premium": True, "expires_at": None})
    )
    async with WebhookHttpClient() as client:
        service = WebhookService(client, default_expiry=600)
        created = await service.configure(WebhookConfig(default_status=201, request_limit=0))
        explicit = await service.configure(WebhookConfig(expiry=60))
        plain = await service.create()
    assert created.data["applied_settings"] == {"default_status": 201, "request_limit": 0, "expiry": 600}
    assert json.loads(route.calls[1].request.content)["expiry"] == 60
    assert json.loads(route.calls[2].request.content) == {"expiry": 600}
    assert plain.data["premium"] is True and plain.data["email"].endswith("@emailhook.site")


@pytest.mark.asyncio
@respx.mock
async def test_configure_updates_existing_token_without_resetting_the_rest() -> None:
    # Seen live 2026-09-03: PUT with only {"alias"} reset status/content/timeout/cors.
    respx.get(BASE).mock(
        return_value=httpx.Response(
            200,
            json={
                "uuid": TOKEN, "default_status": 203, "default_content": "keep-me", "default_content_type": "text/html",
                "timeout": 2, "listen": 0, "cors": True, "alias": None, "request_limit": 50, "actions": False,
                "group_id": None, "description": None, "expiry": None, "expires_at": None,
            },
        )
    )
    route = respx.put(BASE).mock(return_value=httpx.Response(200, json={"uuid": TOKEN, "alias": "my-hook"}))
    async with WebhookHttpClient() as client:
        result = await WebhookService(client).configure(
            WebhookConfig(alias="my-hook", listen=5, actions=False), webhook_token=TOKEN
        )
    assert json.loads(route.calls[0].request.content) == {
        "default_status": 203, "default_content": "keep-me", "default_content_type": "text/html",
        "timeout": 2, "listen": 5, "cors": True, "alias": "my-hook", "request_limit": 50, "actions": False,
    }
    assert result.data["url"] == f"{WEBHOOK_SITE_API}/my-hook"
    assert result.data["updated_settings"] == {"listen": 5, "alias": "my-hook", "actions": False}


@pytest.mark.asyncio
@respx.mock
async def test_get_info_includes_every_address() -> None:
    respx.get(BASE).mock(return_value=httpx.Response(200, json={"uuid": TOKEN, "alias": None, "requests": 3}))
    async with WebhookHttpClient() as client:
        result = await WebhookService(client).get_info(TOKEN)
    assert result.data["dns"] == f"{TOKEN}.dnshook.site"
    assert result.data["subdomain_url"] == f"https://{TOKEN}.webhook.site"
    assert result.data["requests_count"] == 3


def test_resolve_default_expiry() -> None:
    assert resolve_default_expiry(None) is None
    assert resolve_default_expiry(" ") is None
    assert resolve_default_expiry("0") is None
    assert resolve_default_expiry("3600") == 3600
    with pytest.raises(ValueError):
        resolve_default_expiry("later")
    with pytest.raises(ValueError):
        resolve_default_expiry("999999999")


# --- request service --------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_get_request_latest_retries_after_404_then_raw() -> None:
    latest = respx.get(f"{BASE}/request/latest").mock(
        side_effect=[
            httpx.Response(404, json={}),
            httpx.Response(200, json={"uuid": "r1", "type": "web", "method": "POST", "content": "{}"}),
        ]
    )
    respx.get(f"{BASE}/request/latest/raw").mock(
        return_value=httpx.Response(200, content=b'{"hello":1}', headers={"content-type": "application/json"})
    )
    async with WebhookHttpClient() as client:
        result = await RequestService(client).get_request(TOKEN, raw=True)
    assert latest.call_count == 2
    assert result.data["request"]["uuid"] == "r1"
    assert result.data["raw_body"] == '{"hello":1}'


@pytest.mark.asyncio
@respx.mock
async def test_get_request_empty_token_returns_none() -> None:
    respx.get(f"{BASE}/request/latest").mock(return_value=httpx.Response(404, json={}))
    async with WebhookHttpClient() as client:
        result = await RequestService(client).get_request(TOKEN)
    assert result.success is True and result.data["request"] is None


@pytest.mark.asyncio
@respx.mock
async def test_update_request_uses_singular_paths_with_documented_fallback() -> None:
    singular = respx.put(f"{BASE}/request/r1").mock(return_value=httpx.Response(404, json={}))
    plural = respx.put(f"{BASE}/requests/r1").mock(return_value=httpx.Response(200, json={"note": "hi"}))
    response = respx.put(f"{BASE}/request/r1/response").mock(return_value=httpx.Response(200, json={"status": 2}))
    async with WebhookHttpClient() as client:
        result = await RequestService(client).update_request(
            TOKEN, "r1", note="hi", response_content="ok", response_status=201, response_headers={"X": "1"}
        )
    assert singular.called and plural.called
    assert result.success is True
    assert result.data["note_path"].endswith("/requests/r1")
    assert result.data["response_api_status"] == 2
    sent = json.loads(response.calls[0].request.content)
    assert base64.b64decode(sent["content"]) == b"ok"
    assert sent["status"] == 201 and sent["headers"] == {"X": "1"}


@pytest.mark.asyncio
@respx.mock
async def test_download_file_follows_redirect_and_base64_encodes() -> None:
    respx.get(f"{BASE}/request/r1/download/f1").mock(
        return_value=httpx.Response(302, headers={"location": "https://files.example/blob"})
    )
    respx.get("https://files.example/blob").mock(
        return_value=httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png"})
    )
    async with WebhookHttpClient() as client:
        result = await RequestService(client).download_file(TOKEN, "r1", "f1")
    assert result.data["content_type"] == "image/png"
    assert base64.b64decode(result.data["content_base64"]) == b"\x89PNG"


@pytest.mark.asyncio
@respx.mock
async def test_export_json_pages_and_csv_uses_export_endpoint() -> None:
    respx.get(f"{BASE}/requests").mock(
        side_effect=[
            httpx.Response(200, json={"data": [{"uuid": "a", "html_content": "<b>x</b>"}], "is_last_page": False}),
            httpx.Response(200, json={"data": [{"uuid": "b"}], "is_last_page": True}),
        ]
    )
    respx.get(f"{BASE}/requests/export").mock(
        return_value=httpx.Response(200, content=b"uuid,type\na,web\nb,web\n", headers={"content-type": "text/csv"})
    )
    async with WebhookHttpClient() as client:
        service = RequestService(client)
        as_json = await service.export_requests(TOKEN, limit=200)
        as_csv = await service.export_requests(TOKEN, format="csv", query="type:web")
    assert [row["uuid"] for row in as_json.data["requests"]] == ["a", "b"]
    assert as_json.data["requests"][0]["html_content"] == "<b>x</b>"
    assert as_json.data["pagination"]["pages_fetched"] == 2
    assert as_csv.data["request_count"] == 2 and as_csv.data["csv"].startswith("uuid,type")


@pytest.mark.asyncio
@respx.mock
async def test_list_requests_exposes_pagination_and_attachments() -> None:
    respx.get(f"{BASE}/requests").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "uuid": "m1",
                        "type": "email",
                        "sender": "bounce@example.com",
                        "checks": {"spam": False, "dkim": True},
                        "email_truncated": True,
                        "files": {"attachment": {"id": "f1", "filename": "invoice.pdf", "size": 10, "content_type": "application/pdf"}},
                        "headers": {"from": ["a@b"], "subject": ["Hi"]},
                    }
                ],
                "is_last_page": True,
                "total": 1,
                "current_page": 2,
            },
        )
    )
    async with WebhookHttpClient() as client:
        service = RequestService(client)
        listed = await service.get_all(TOKEN, limit=5, page=2)
        email = service._format_email(listed.data["requests"][0] | {"headers": {"from": ["a@b"], "subject": ["Hi"]}, "sender": "bounce@example.com", "checks": {"spam": False}, "email_truncated": True, "files": {"attachment": {"id": "f1", "filename": "invoice.pdf"}}}, extract_links=True)
    assert listed.data["pagination"] == {
        "total": 1, "per_page": None, "current_page": 2, "last_page": None,
        "is_last_page": True, "pages_fetched": 1, "returned": 1, "truncated": False,
    }
    assert listed.data["requests"][0]["attachments"][0]["file_id"] == "f1"
    assert email["sender"] == "bounce@example.com" and email["email_truncated"] is True
    assert email["attachments"][0]["filename"] == "invoice.pdf"


@pytest.mark.asyncio
@respx.mock
async def test_send_multiple_uses_method_and_headers() -> None:
    route = respx.put(f"{WEBHOOK_SITE_API}/{TOKEN}").mock(return_value=httpx.Response(202))
    async with WebhookHttpClient() as client:
        result = await RequestService(client).send_multiple(
            TOKEN, payloads=[{"a": 1}, {"b": 2}], method="put", headers={"X-Test": "yes"}
        )
    assert result.data["success_count"] == 2
    assert route.calls[0].request.headers["X-Test"] == "yes"


# --- account, actions, schedules, databases ----------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_account_list_tokens_formats_and_paginates() -> None:
    respx.get(f"{WEBHOOK_SITE_API}/token").mock(
        return_value=httpx.Response(200, json=_page([{"uuid": TOKEN, "alias": "hook", "requests": 2, "premium": True}], 1, 1))
    )
    async with WebhookHttpClient(api_key="k") as client:
        result = await AccountService(client).list_tokens()
    hook = result.data["webhooks"][0]
    assert hook["url"] == f"{WEBHOOK_SITE_API}/hook" and hook["requests_count"] == 2
    assert result.data["pagination"]["is_last_page"] is True


@pytest.mark.asyncio
@respx.mock
async def test_account_crud_paths() -> None:
    create = respx.post(f"{WEBHOOK_SITE_API}/global-variables").mock(return_value=httpx.Response(200, json={"id": 7}))
    respx.get(f"{WEBHOOK_SITE_API}/global-variables").mock(
        return_value=httpx.Response(200, json=_page([{"id": 7, "name": "v", "value": "1"}], 1, 1))
    )
    update = respx.put(f"{WEBHOOK_SITE_API}/global-variables/7").mock(return_value=httpx.Response(200, json={"id": 7, "value": "2"}))
    delete = respx.delete(f"{WEBHOOK_SITE_API}/global-variables/7").mock(return_value=httpx.Response(204))
    invite = respx.post(f"{WEBHOOK_SITE_API}/users/invite").mock(return_value=httpx.Response(200, json={"id": 9}))
    templates = respx.post(f"{WEBHOOK_SITE_API}/templates").mock(return_value=httpx.Response(200, json={"id": 3}))
    async with WebhookHttpClient(api_key="k") as client:
        svc = AccountService(client)
        assert (await svc.create_variable("v", "1")).data["variable"]["id"] == 7
        assert (await svc.update_variable(7, value="2")).data["variable"]["value"] == "2"
        assert (await svc.delete_variable(7)).success is True
        assert (await svc.invite_user("Jo", "jo@example.com", 300)).data["user"]["id"] == 9
        assert (await svc.create_template("T", actions=[{"type": "log"}])).data["template"]["id"] == 3
    assert json.loads(create.calls[0].request.content) == {"name": "v", "value": "1"}
    # a value-only PUT would wipe the name on webhook.site, so the saved name is resent
    assert json.loads(update.calls[0].request.content) == {"name": "v", "value": "2"}
    assert delete.called
    assert json.loads(invite.calls[0].request.content)["user_type_id"] == 300
    assert json.loads(templates.calls[0].request.content)["actions"] == [{"type": "log"}]


@pytest.mark.asyncio
@respx.mock
async def test_actions_service_endpoints() -> None:
    listed = respx.get(f"{BASE}/actions").mock(return_value=httpx.Response(200, json={"data": [{"uuid": "a1"}]}))
    created = respx.post(f"{BASE}/actions").mock(return_value=httpx.Response(201, json={"uuid": "a2", "type": "log"}))
    tested = respx.post(f"{BASE}/test-action").mock(return_value=httpx.Response(200, json={"success": True, "result": {"output": {}}}))
    executed = respx.post(f"{BASE}/request/r1/execute").mock(return_value=httpx.Response(200, json={"success": True, "result": {}}))
    deleted = respx.delete(f"{BASE}/actions/a2").mock(return_value=httpx.Response(204))
    async with WebhookHttpClient(api_key="k") as client:
        svc = ActionsService(client)
        assert (await svc.list(TOKEN)).data["actions"] == [{"uuid": "a1"}]
        create = await svc.create(TOKEN, type="log", parameters={"text": "hi"}, order=1, queue=True, delay=5)
        test = await svc.test(TOKEN, type="script", parameters={"script": "echo('x')"}, request_id="r1")
        run = await svc.execute(TOKEN, "r1", error_notifications=True)
        gone = await svc.delete(TOKEN, "a2")
    assert listed.called and create.data["action"]["uuid"] == "a2"
    assert json.loads(created.calls[0].request.content) == {
        "type": "log", "order": 1, "parameters": {"text": "hi"}, "queue": True, "delay": 5,
    }
    assert tested.calls[0].request.url.params["request_id"] == "r1" and test.success is True
    assert executed.calls[0].request.url.params["error_notifications"] == "true" and run.success is True
    assert gone.success is True


@pytest.mark.asyncio
@respx.mock
async def test_schedule_service_endpoints() -> None:
    respx.get(f"{WEBHOOK_SITE_API}/schedules").mock(return_value=httpx.Response(200, json=_page([{"id": 1}], 1, 1)))
    created = respx.post(f"{WEBHOOK_SITE_API}/schedules").mock(return_value=httpx.Response(200, json={"id": 2, "name": "ping"}))
    respx.post(f"{WEBHOOK_SITE_API}/schedules/2/run-now").mock(return_value=httpx.Response(200, json={"ok": True}))
    logs = respx.get(f"{WEBHOOK_SITE_API}/schedules/2/logs").mock(return_value=httpx.Response(200, json={"data": [{"id": 5}], "total": 1}))
    respx.delete(f"{WEBHOOK_SITE_API}/schedules/2").mock(return_value=httpx.Response(204))
    async with WebhookHttpClient(api_key="k") as client:
        svc = ScheduleService(client)
        assert (await svc.list()).data["schedules"] == [{"id": 1}]
        made = await svc.create(name="ping", interval="5-minute", request_url="https://example.com", request_method="GET", ignored=None)
        assert (await svc.run_now(2)).data["status_code"] == 200
        assert (await svc.logs(2)).data["logs"] == [{"id": 5}]
        assert (await svc.delete(2)).success is True
    assert made.data["schedule"]["id"] == 2
    assert json.loads(created.calls[0].request.content) == {
        "name": "ping", "interval": "5-minute", "request_url": "https://example.com", "request_method": "GET",
    }
    assert logs.calls[0].request.headers["accept"] == "application/json"


@pytest.mark.asyncio
@respx.mock
async def test_database_service_query_reports_errors() -> None:
    respx.post(f"{WEBHOOK_SITE_API}/databases/9/query").mock(
        side_effect=[
            httpx.Response(200, json={"result": [{"id": 1}], "error": None, "time": 3}),
            httpx.Response(200, json={"result": None, "error": "relation missing", "time": 1}),
        ]
    )
    async with WebhookHttpClient(api_key="k") as client:
        svc = DatabaseService(client)
        ok = await svc.query("9", "select 1", params=[1])
        bad = await svc.query("9", "select * from nope")
    assert ok.success is True and ok.data["result"] == [{"id": 1}]
    assert bad.success is False and "relation missing" in bad.message


@pytest.mark.asyncio
@respx.mock
async def test_updates_merge_into_the_saved_record() -> None:
    respx.get(f"{BASE}/actions").mock(
        return_value=httpx.Response(200, json={"data": [{"uuid": "a1", "type": "log", "order": 3, "parameters": {"text": "old"}, "queue": True}]})
    )
    action_put = respx.put(f"{BASE}/actions/a1").mock(return_value=httpx.Response(201, json={"uuid": "a1"}))
    respx.get(f"{WEBHOOK_SITE_API}/schedules/5").mock(
        return_value=httpx.Response(200, json={"id": 5, "name": "old", "interval": "daily", "request_url": "https://example.com", "request_method": "GET", "timeout": 10})
    )
    schedule_put = respx.put(f"{WEBHOOK_SITE_API}/schedules/5").mock(return_value=httpx.Response(200, json={"id": 5}))
    run = respx.post(f"{WEBHOOK_SITE_API}/schedules/5/run-now").mock(
        return_value=httpx.Response(302, headers={"location": f"{WEBHOOK_SITE_API}/control-panel/schedules/5/logs"})
    )
    respx.get(f"{WEBHOOK_SITE_API}/users").mock(
        return_value=httpx.Response(200, json=_page([{"id": 9, "name": "Jo", "email": "jo@example.com", "user_type_id": 100}], 1, 1))
    )
    user_put = respx.put(f"{WEBHOOK_SITE_API}/users/9").mock(return_value=httpx.Response(200, json={"id": 9}))
    respx.get(f"{WEBHOOK_SITE_API}/databases").mock(
        return_value=httpx.Response(200, json=_page([{"id": "77", "name": "db", "plan": "db-m", "group_id": None}], 1, 1))
    )
    db_put = respx.put(f"{WEBHOOK_SITE_API}/databases/77").mock(return_value=httpx.Response(200, json={"id": "77"}))
    async with WebhookHttpClient(api_key="k") as client:
        await ActionsService(client).update(TOKEN, "a1", parameters={"text": "new"})
        await ScheduleService(client).update(5, name="renamed")
        ran = await ScheduleService(client).run_now(5)
        await AccountService(client).update_user(9, name="Joanna")
        await DatabaseService(client).update("77", name="db2")
    assert json.loads(action_put.calls[0].request.content) == {"type": "log", "order": 3, "parameters": {"text": "new"}, "queue": True}
    assert json.loads(schedule_put.calls[0].request.content) == {
        "name": "renamed", "interval": "daily", "request_url": "https://example.com", "request_method": "GET", "timeout": 10,
    }
    assert run.called and ran.success is True and ran.data["logs_url"].endswith("/logs")
    assert json.loads(user_put.calls[0].request.content) == {"name": "Joanna", "email": "jo@example.com", "user_type_id": 100}
    assert json.loads(db_put.calls[0].request.content) == {"name": "db2", "plan": "db-m"}


@pytest.mark.asyncio
@respx.mock
async def test_api_errors_carry_the_servers_validation_message() -> None:
    respx.put(f"{WEBHOOK_SITE_API}/schedules/5").mock(
        return_value=httpx.Response(
            422, json={"success": False, "error": {"message": "Validation error", "validation": {"interval": ["The interval field is required."]}}}
        )
    )
    respx.post(f"{BASE}/test-action").mock(return_value=httpx.Response(422, json={"order": ["The order field is required."]}))
    async with WebhookHttpClient(api_key="k") as client:
        with pytest.raises(WebhookApiError, match="interval: The interval field is required"):
            await client.put("/schedules/5", json_data={"name": "x"})
        with pytest.raises(WebhookApiError, match="order: The order field is required"):
            await client.post(f"/token/{TOKEN}/test-action", json_data={})


@pytest.mark.asyncio
@respx.mock
async def test_check_for_callbacks_matches_identifier_anywhere_in_the_request() -> None:
    respx.get(f"{BASE}/requests").mock(
        return_value=httpx.Response(
            200,
            json={"data": [
                {"uuid": "1", "type": "web", "method": "GET", "url": f"{WEBHOOK_SITE_API}/{TOKEN}?id=probe-7", "headers": {}, "content": ""},
                {"uuid": "2", "type": "dns", "hostname": f"other.{TOKEN}.dnshook.site", "headers": {}},
            ]},
        )
    )
    async with WebhookHttpClient() as client:
        hit = await BugBountyService(client).check_for_callbacks(TOKEN, since_minutes=5, identifier="probe-7")
        miss = await BugBountyService(client).check_for_callbacks(TOKEN, since_minutes=5, identifier="nope")
    assert hit.data["detected"] is True and hit.data["total_callbacks"] == 1
    assert miss.data["detected"] is False


@pytest.mark.asyncio
@respx.mock
async def test_queue_profiles_and_description_verified_live() -> None:
    # Shapes seen live 2026-09-03: POST/PUT need every field; GET /queues/{id} 404s so updates read the list.
    created = respx.post(f"{WEBHOOK_SITE_API}/queues").mock(
        return_value=httpx.Response(200, json={"name": "q", "delay": 0, "amount": 10, "duration": 60, "expiry": 3600, "group_id": None, "id": 7})
    )
    respx.get(f"{WEBHOOK_SITE_API}/queues").mock(
        return_value=httpx.Response(200, json=_page([{"id": 7, "name": "q", "amount": 10, "duration": 60, "expiry": 3600, "delay": 0, "group_id": None}], 1, 1))
    )
    updated = respx.put(f"{WEBHOOK_SITE_API}/queues/7").mock(return_value=httpx.Response(200, json={"id": 7, "amount": 5}))
    respx.delete(f"{WEBHOOK_SITE_API}/queues/7").mock(return_value=httpx.Response(204))
    respx.get(f"{WEBHOOK_SITE_API}/variables").mock(return_value=httpx.Response(200, json={"request.uuid": "x", "request.method": "POST"}))
    action = respx.post(f"{BASE}/actions").mock(return_value=httpx.Response(201, json={"uuid": "a1", "queue": True, "queue_id": 7}))
    async with WebhookHttpClient(api_key="k") as client:
        svc = AccountService(client)
        assert (await svc.create_queue("q", 10, 60, 3600)).data["queue"]["id"] == 7
        assert (await svc.update_queue(7, amount=5)).success is True
        assert (await svc.list_queues()).data["queues"][0]["name"] == "q"
        assert (await svc.delete_queue(7)).success is True
        assert await svc.live_variables() == ["request.method", "request.uuid"]
        await ActionsService(client).create(TOKEN, type="log", parameters={"text": "x"}, order=1, queue=True, queue_id=7)
    assert json.loads(created.calls[0].request.content) == {"name": "q", "amount": 10, "duration": 60, "expiry": 3600, "delay": 0}
    assert json.loads(updated.calls[0].request.content) == {"name": "q", "amount": 5, "duration": 60, "expiry": 3600, "delay": 0}
    assert json.loads(action.calls[0].request.content)["queue_id"] == 7
    assert WebhookConfig(description="label").to_payload() == {"description": "label"}


def test_generate_oob_payloads_dispatches() -> None:
    svc = BugBountyService(client=None)  # type: ignore[arg-type]
    assert "callback_payloads" in svc.generate_oob_payloads(TOKEN, "ssrf").data
    assert svc.generate_oob_payloads(TOKEN, "xss").success is True
    canary = svc.generate_oob_payloads(TOKEN, "canary", canary_type="dns")
    assert canary.success is True
    assert svc.generate_oob_payloads(TOKEN, "bogus").success is False


# --- tools ----------------------------------------------------------------------


class _Ctx:
    def __init__(self, app) -> None:
        self.request_context = type("RC", (), {"lifespan_context": app})()


async def _call(tool_name: str, **kwargs):
    import server

    tools = {tool.name: tool for tool in await server.mcp.list_tools()}
    assert tool_name in tools
    fn = server.mcp._tool_manager.get_tool(tool_name).fn  # type: ignore[attr-defined]
    return await fn(**kwargs)


@pytest.mark.asyncio
async def test_manage_tools_validate_required_arguments() -> None:
    from unittest.mock import MagicMock

    from models.app_context import AppContext

    fields = ("client", "webhooks", "requests", "bounty", "account", "actions", "schedules", "databases")
    app = AppContext(**{name: MagicMock(name=name) for name in fields})  # never reached when validation fails
    ctx = _Ctx(app)
    missing_type = await _call("manage_custom_actions", webhook_token=TOKEN, action="create", ctx=ctx)
    assert missing_type["success"] is False and "type is required" in missing_type["message"]
    bad_id = await _call("manage_groups", action="delete", ctx=ctx, group_id=0)
    assert bad_id["success"] is False and "group_id" in bad_id["message"]
    no_body = await _call("send_requests", webhook_token=TOKEN, ctx=ctx)
    assert no_body["success"] is False and "payloads" in no_body["message"]
    nothing = await _call("update_request", webhook_token=TOKEN, request_id="r1", ctx=ctx)
    assert nothing["success"] is False and "note" in nothing["message"]
    for service in (app.actions, app.account, app.requests):
        assert not service.method_calls
