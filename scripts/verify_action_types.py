"""Run every documented action type through webhook.site's test-action endpoint for real.

Usage:
    WEBHOOK_SITE_API_KEY=... python scripts/verify_action_types.py

For each type in utils/action_types.json a minimal payload is built from the
documented required parameters and sent to POST /token/{id}/test-action against
a throwaway token. The outcome is written back into the JSON as ``verified``:

    ok                the API accepted the parameters and the action ran
    runtime_error     parameters accepted, execution failed (external host, provider)
    validation_error  the API rejected the payload: the docs are missing something
    unknown_type      the API does not know this type name

The raw exchanges are stored in tests/recordings/action_types_live.json.
Also probes a few names the product docs mention but the API list does not.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.account_service import AccountService  # noqa: E402
from services.webhook_service import WebhookService  # noqa: E402
from utils.http_client import WebhookApiError, WebhookHttpClient  # noqa: E402
from utils.recorder import sanitize  # noqa: E402

DATA = ROOT / "utils" / "action_types.json"
RECORDING = ROOT / "tests" / "recordings" / "action_types_live.json"
EXTRA_NAMES = ["mock", "openapi", "validate_json", "extract_json", "json_validate", "http_request", "not_a_real_type"]

# Never point an outbound action (http, send_request, slack_send_message...) at a
# webhook.site URL: the platform flags it as a recursive request, disables the
# action and emails the account owner.
BY_NAME: dict[str, Any] = {
    "url": "https://example.com/",
    "recipient": "{self_email}",
    "subject": "probe",
    "content": "probe",
    "text": "probe",
    "message": "probe",
    "topic": "mcp-probe",
    "jsonpath": "$",
    "regex": "(.*)",
    "xpath": "/",
    "variable_name": "probe_var",
    "name": "mcp_probe_var",
    "value": "1",
    "statement": "select 1",
    "query": "select 1",
    "host": "example.invalid",
    "username": "user",
    "password": "pass",
    "path": "/probe",
    "delimiter": ",",
    "source": "$request.content$",
    "input": "$request.method$",
    "operator": "eq",
    "action": "noop",
    "period": 60,
    "count": 100,
    "delay": "1",
    "template_id": 1,
    "token_id": "{self_token}",
    "provider_id": "1",
    "bucket_name": "bucket",
    "object_key": "key",
    "region": "us-east-1",
    "distribution_id": "dist",
    "paths": "/*",
    "spreadsheet_id": "sheet",
    "range": "A1",
    "values": "a",
    "worksheet": "Sheet1",
    "width": "10",
    "aspect_ratio": True,
    "webhook_url": "https://example.com/",
    "app_key": "k",
    "app_secret": "s",
    "target_type": "app",
    "target": "t",
    "tweet": "probe",
    "queue": "probe",
    "mode": "all",
    "default": "",
    "mappings": [{"from": "a", "to": "b"}],
    "replacements": [{"from": "a", "to": "b"}],
    "conditions": [{"input": "a", "operator": "eq", "value": "a"}],
    "properties": [{"name": "email", "value": "probe@example.com"}],
    "attachments": [],
    "params": [],
    "script": "echo('ok')",
    "schema": '{"type": "object"}',
}
BY_TYPE_SCRIPT = {"javascript": "console.log('ok')", "script": "echo('ok')"}
OPENAPI_SPEC = json.dumps(
    {
        "openapi": "3.0.0",
        "info": {"title": "probe", "version": "1"},
        "paths": {"/": {"get": {"responses": {"200": {"description": "ok", "content": {"application/json": {"schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}}}}}}}}},
    }
)
BY_TYPE_PARAM = {
    ("mock", "source"): OPENAPI_SPEC,
    ("validate_json", "source"): '{"a": 1}',
    ("condition", "value"): "POST",
    ("text_map", "default"): "none",
    ("webhook_get_requests", "variable_name"): "req",
    ("microsoft_drive_download", "variable_name"): "file",
}
MISSING = re.compile(r"Missing parameter:\s*([A-Za-z0-9_.]+)")


def placeholder(type_name: str, param: str, spec: dict[str, Any], ctx: dict[str, str]) -> Any:
    if (type_name, param) in BY_TYPE_PARAM:
        return BY_TYPE_PARAM[(type_name, param)]
    if param == "script":
        return BY_TYPE_SCRIPT.get(type_name, "echo('ok')")
    if param in BY_NAME:
        value = BY_NAME[param]
        return value.format(**ctx) if isinstance(value, str) else value
    if spec.get("in"):
        return spec["in"][0]
    kind = spec.get("type")
    if kind in ("int", "number"):
        return spec.get("min", 1)
    if kind == "bool":
        return True
    if kind == "array":
        return []
    if kind == "url":
        return "https://example.com/"
    return "probe"


def build_payload(type_name: str, entry: dict[str, Any], ctx: dict[str, str]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for name, spec in entry["params"].items():
        if "." in name or "*" in name:
            continue  # nested rule descriptions (retry.enabled, random.*.length)
        if spec.get("required") or spec.get("required_live") or (type_name, name) in BY_TYPE_PARAM:
            params[name] = placeholder(type_name, name, spec, ctx)
    # Types whose only interesting params are optional still need something sensible.
    if type_name == "modify_response":
        params.setdefault("content", "probe")
    if type_name == "set_variable":
        params.setdefault("value", "1")
    if type_name == "auto_json":
        params.setdefault("source", "$request.content$")
    if type_name == "extract_jsonpath":
        params.setdefault("source", '{"a": 1}')
    return {"type": type_name, "order": 1, "parameters": params}


def classify(status: int, body: Any, payload: dict[str, Any]) -> tuple[str, str]:
    text = json.dumps(body)[:300] if not isinstance(body, str) else body[:300]
    lowered = text.lower()
    if status == 422:
        if "invalid action type" in lowered:
            return "unknown_type", text
        return "validation_error", text
    if status == 404 and "entity not found" in lowered and "provider_id" in payload.get("parameters", {}):
        return "needs_provider", text
    if status >= 500:
        return "server_error", text
    if status >= 400:
        return "http_error", text
    if isinstance(body, dict):
        result = body.get("result") or {}
        output = result.get("output") or {}
        lines = [line for lines in output.values() for line in (lines if isinstance(lines, list) else [lines])]
        text = " | ".join(str(line) for line in lines)[:300]
        if body.get("success") is False or any("error" in str(line).lower() or "failed" in str(line).lower() for line in lines):
            return "runtime_error", text
        return "ok", text
    return "ok", ""


async def main() -> int:
    key = os.environ.get("WEBHOOK_SITE_API_KEY", "").strip()
    if not key:
        print("Set WEBHOOK_SITE_API_KEY", file=sys.stderr)
        return 2
    data = json.loads(DATA.read_text(encoding="utf-8"))
    types = data["types"]
    exchanges: list[dict[str, Any]] = []
    checked_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

    async with WebhookHttpClient(api_key=key) as client:
        webhooks = WebhookService(client)
        token = (await webhooks.create()).data["token"]
        ctx = {
            "self_url": f"https://webhook.site/{token}",
            "self_email": f"{token}@email.webhook.site",
            "self_token": token,
        }
        try:
            # A captured request to test against (test-action uses default variables otherwise).
            await client.request_raw("POST", ctx["self_url"], json={"a": 1, "probe": True})
            await asyncio.sleep(1.5)
            listing = await client.get(f"/token/{token}/requests", params={"sorting": "newest"})
            request_id = listing["data"][0]["uuid"] if listing.get("data") else None

            async def attempt(payload: dict[str, Any]) -> tuple[int, Any]:
                try:
                    response = await client.post(
                        f"/token/{token}/test-action",
                        json_data=payload,
                        params={"request_id": request_id} if request_id else None,
                    )
                    return response.status_code, response.json()
                except WebhookApiError as exc:
                    try:
                        return exc.status_code or 0, json.loads(exc.response_body or "")
                    except ValueError:
                        return exc.status_code or 0, exc.response_body

            names = list(types) + [n for n in EXTRA_NAMES if n not in types]
            for name in names:
                entry = types.get(name, {"params": {}})
                payload = build_payload(name, entry, ctx)
                learned: list[str] = []
                for _ in range(4):
                    status, body = await attempt(payload)
                    verdict, message = classify(status, body, payload)
                    missing = MISSING.search(message) if verdict == "validation_error" else None
                    if not missing or missing.group(1) in payload["parameters"]:
                        break
                    # The live API wants a parameter the docs call optional: add it and retry.
                    param = missing.group(1)
                    learned.append(param)
                    spec = entry["params"].get(param, {})
                    payload["parameters"][param] = placeholder(name, param, spec, ctx)
                    await asyncio.sleep(0.3)
                exchanges.append({"type": name, "payload": payload, "status": status, "body": body, "verdict": verdict, "learned_required": learned})
                flag = f" (live-required: {', '.join(learned)})" if learned else ""
                print(f"{verdict:17} {name:28} {message[:80]}{flag}")
                if name in types:
                    types[name]["verified"] = {"status": verdict, "message": message, "checked_at": checked_at}
                    for param in learned:
                        types[name]["params"].setdefault(param, {"required": False, "type": None})["required_live"] = True
                    if verdict in ("ok", "runtime_error"):
                        types[name]["example"] = payload["parameters"]
                await asyncio.sleep(0.4)
        finally:
            # store_global_variable may have created a variable; remove it.
            account = AccountService(client)
            found = await account.list_variables(search="mcp_probe_var")
            for item in found.data.get("variables", []):
                await account.delete_variable(item["id"])
            await webhooks.delete(token)

    data["verified_at"] = checked_at
    DATA.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    RECORDING.parent.mkdir(parents=True, exist_ok=True)
    RECORDING.write_text(
        json.dumps({"checked_at": checked_at, "exchanges": sanitize(exchanges)}, indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    counts: dict[str, int] = {}
    for item in exchanges:
        counts[item["verdict"]] = counts.get(item["verdict"], 0) + 1
    print("\nsummary:", counts)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
