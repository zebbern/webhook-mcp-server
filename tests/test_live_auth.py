"""Authenticated live tests: run with WEBHOOK_SITE_API_KEY set (``pytest -m live_auth``).

Every token these tests create is deleted in a finally block. That matters for
the sign-up flow: a send_email Custom Action also fires on incoming emails, so
an undeleted token could keep mailing itself.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from services.account_service import AccountService
from services.actions_service import ActionsService
from services.request_service import RequestService
from services.webhook_service import WebhookService
from utils.http_client import WebhookHttpClient

pytestmark = [pytest.mark.live_auth, pytest.mark.asyncio]


@pytest.fixture
async def client(api_key: str) -> AsyncIterator[WebhookHttpClient]:
    async with WebhookHttpClient(api_key=api_key) as http:
        yield http


@pytest.fixture
async def token(client: WebhookHttpClient) -> AsyncIterator[str]:
    webhooks = WebhookService(client)
    created = await webhooks.create()
    assert created.success, created.message
    try:
        yield created.data["token"]
    finally:
        await webhooks.delete(created.data["token"])


async def test_created_token_is_permanent_and_listed(client: WebhookHttpClient, token: str) -> None:
    info = await WebhookService(client).get_info(token)
    assert info.data["premium"] is True
    assert info.data["expires_at"] is None
    listed = await AccountService(client).list_tokens(per_page=100, max_items=500)
    assert listed.success is True
    assert token in {hook["token"] for hook in listed.data["webhooks"]}


async def test_configure_alias_and_request_limit(client: WebhookHttpClient, token: str) -> None:
    from models.schemas import WebhookConfig

    alias = f"mcp-ci-{token[:8]}"
    updated = await WebhookService(client).configure(
        WebhookConfig(alias=alias, request_limit=50, default_status=202), webhook_token=token
    )
    assert updated.success is True
    info = await WebhookService(client).get_info(token)
    assert info.data["alias"] == alias
    assert info.data["default_status"] == 202


async def test_signup_flow_end_to_end(client: WebhookHttpClient, token: str) -> None:
    """create -> guarded send_email action -> trigger -> wait_for_email -> follow_email_link."""
    actions = ActionsService(client)
    requests = RequestService(client)
    inbox = f"{token}@email.webhook.site"

    # Stop the chain for anything that is not a web request, so the email the
    # send_email action delivers to this same inbox cannot re-trigger it.
    guard = await actions.create(
        token,
        type="condition",
        order=1,
        parameters={"input": "$request.type$", "operator": "neq", "value": "web", "action": "stop"},
    )
    assert guard.success, guard.message
    guard_id = guard.data["action"]["uuid"]
    mail = await actions.create(
        token,
        type="send_email",
        order=2,
        parameters={
            "recipient": inbox,
            "subject": "Verify your account",
            "is_html": True,
            "content": (
                "<p>Your verification code is 847291.</p>"
                '<p><a href="https://example.com/verify?token=abc&amp;u=1">Verify your email</a></p>'
            ),
        },
    )
    assert mail.success, mail.message
    listed = await actions.list(token)
    assert {action["uuid"] for action in listed.data["actions"]} >= {guard_id, mail.data["action"]["uuid"]}

    async def trigger() -> None:
        await asyncio.sleep(1)
        await requests.send_multiple(token, payloads=[{"trigger": "verification"}])

    task = asyncio.create_task(trigger())
    received = await requests.wait_for_email(token, timeout_seconds=90)
    await task
    assert received.success, received.message
    email = received.data["email"]
    assert email["verification_codes"] == ["847291"]
    assert email["auth_links"][0] == "https://example.com/verify?token=abc&u=1"
    assert email["checks"]["dkim"] is True

    opened = await requests.follow_email_link(token, request_id=email["uuid"])
    assert opened.data["opened_url"] == "https://example.com/verify?token=abc&u=1"
    assert opened.data["status_code"] in (200, 404)
    assert opened.data["title"] == "Example Domain"

    # Guard held: only one email, not a loop.
    await asyncio.sleep(5)
    inbox_state = await requests.get_all(token, limit=50, request_type="email")
    assert inbox_state.data["total_requests"] == 1


async def test_wait_for_request_arrives_over_socket(client: WebhookHttpClient, token: str) -> None:
    requests = RequestService(client)

    async def fire() -> None:
        await asyncio.sleep(1)
        await requests.send_multiple(token, payloads=[{"ping": 1}])

    task = asyncio.create_task(fire())
    result = await requests.wait_for_request(token, timeout_seconds=30, request_type="web")
    await task
    assert result.success is True
    assert result.data["source"] == "socket"


async def test_global_variable_round_trip(client: WebhookHttpClient) -> None:
    account = AccountService(client)
    created = await account.create_variable("mcp_ci_probe", "1")
    variable_id = created.data["variable"]["id"]
    try:
        listed = await account.list_variables(search="mcp_ci_probe")
        assert any(item["id"] == variable_id for item in listed.data["variables"])
    finally:
        assert (await account.delete_variable(variable_id)).success is True


async def test_csv_export_and_raw_body(client: WebhookHttpClient, token: str) -> None:
    requests = RequestService(client)
    await requests.send_multiple(token, payloads=[{"hello": "csv"}])
    await asyncio.sleep(2)
    latest = await requests.get_request(token, raw=True)
    assert latest.data["request"]["uuid"]
    assert "csv" in latest.data["raw_body"]
    exported = await requests.export_requests(token, format="csv")
    assert exported.data["csv"].startswith("uuid,")
