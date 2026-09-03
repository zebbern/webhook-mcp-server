"""The action-type reference is real data: generated from the docs and annotated by a live run."""

from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock

import pytest

from utils import action_types
from utils.validation import ValidationError

TOKEN = "550e8400-e29b-41d4-a716-446655440000"


def test_reference_covers_every_type_with_a_live_verdict() -> None:
    data = action_types.load()
    types = data["types"]
    assert len(types) >= 63
    assert dt.date.fromisoformat(data["verified_at"]) <= dt.date.today()
    for name, entry in types.items():
        assert entry["verified"]["status"] in action_types.STATUS_TEXT, name
        assert entry["verified"]["checked_at"] == data["verified_at"], name
    assert "mock" in types and "validate_json" in types  # exist live, absent from the API list
    assert sum(1 for e in types.values() if e["verified"]["status"] == "ok") >= 30


def test_live_required_params_are_marked() -> None:
    condition = action_types.describe("condition")
    assert condition["params"]["value"]["required"] is True
    assert "500" in condition["params"]["value"]["live_note"]
    assert condition["params"]["input"]["required"] is True
    assert action_types.required_params(action_types.all_types()["text_map"]) == ["source", "operator", "variable_name", "default", "mappings"]


def test_describe_and_summarise_shapes() -> None:
    http = action_types.describe("http")
    assert http["params"]["url"]["required"] is True
    assert http["params"]["mode"]["in"] == ["text", "json", "multipart", "urlencoded", "forward"]
    assert http["verified"]["status"] == "ok"
    assert http["example_parameters"]["url"].startswith("https://example.com")
    provider = action_types.describe("aws_s3_put_object")
    assert provider["verified"]["status"] == "needs_provider" and "provider" in provider["note"].lower()
    summary = action_types.summarise("send_email", action_types.all_types()["send_email"])
    assert summary["required"] == ["recipient", "subject"] and "sender" in summary["optional"]


def test_validate_action_rejects_unknown_and_incomplete() -> None:
    with pytest.raises(ValidationError, match="Did you mean: http"):
        action_types.validate_action("http_request", {"url": "https://example.com"})
    with pytest.raises(ValidationError, match="needs parameters: url"):
        action_types.validate_action("http", {})
    with pytest.raises(ValidationError, match="input, value"):
        action_types.validate_action("condition", {"operator": "eq", "action": "stop"})
    action_types.validate_action("condition", {"input": "$request.type$", "operator": "eq", "value": "web", "action": "stop"})
    action_types.validate_action("http", {"mode": "json"}, partial=True)


def test_variables_reference_lists_verified_base_variables() -> None:
    ref = action_types.variables_reference()
    names = {item["name"] for item in ref["base_variables"]}
    assert {"request.method", "request.query.<name>", "request.form.<name>", "request.checks.<name>"} <= names
    assert ".json_format" in ref["modifiers"]["available"]


@pytest.mark.asyncio
async def test_manage_custom_actions_serves_reference_without_a_token() -> None:
    import server
    from models.app_context import AppContext

    from unittest.mock import AsyncMock

    fields = ("client", "webhooks", "requests", "bounty", "account", "actions", "schedules", "databases")
    app = AppContext(**{name: MagicMock(name=name) for name in fields})
    app.account.live_variables = AsyncMock(return_value=["request.method", "request.uuid"])
    ctx = type("Ctx", (), {"request_context": type("RC", (), {"lifespan_context": app})()})()
    fn = server.mcp._tool_manager.get_tool("manage_custom_actions").fn  # type: ignore[attr-defined]

    listing = await fn(action="types", ctx=ctx)
    assert listing["success"] is True and len(listing["types"]) >= 63
    one = await fn(action="types", ctx=ctx, type="modify_response")
    assert one["params"]["content"]["required"] is False and one["verified"]["status"] == "ok"
    variables = await fn(action="variables", ctx=ctx)
    assert any(v["name"] == "request.method" for v in variables["base_variables"])
    assert variables["live_base_variable_names"] == ["request.method", "request.uuid"]

    bad = await fn(action="create", ctx=ctx, webhook_token=TOKEN, type="http", parameters={})
    assert bad["success"] is False and "needs parameters: url" in bad["message"]
    unknown = await fn(action="create", ctx=ctx, webhook_token=TOKEN, type="htp", parameters={"url": "x"})
    assert unknown["success"] is False and "Did you mean" in unknown["message"]
    no_token = await fn(action="list", ctx=ctx)
    assert no_token["success"] is False and "webhook_token is required" in no_token["message"]
    assert not app.actions.method_calls
