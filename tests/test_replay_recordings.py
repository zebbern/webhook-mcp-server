"""Replay real recorded exchanges through the real code and expect the recorded tool results.

The recordings under tests/recordings/live are produced by
``scripts/live_tool_check.py --record tests/recordings/live`` against the live
API. Every HTTP response here was really returned by webhook.site; every
expected tool result was really produced from it. Replaying them offline turns
that live run into a regression test of the whole service layer.

Tools that leave webhook.site (follow_email_link) or depend on the socket
(wait_for_request, wait_for_email) are skipped; their live coverage stays in
the tool check and the live_auth tier.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from models.app_context import AppContext
from services.account_service import AccountService
from services.actions_service import ActionsService
from services.bugbounty_service import BugBountyService
from services.database_service import DatabaseService
from services.request_service import RequestService
from services.schedule_service import ScheduleService
from services.webhook_service import WebhookService
from utils.http_client import WebhookHttpClient

RECORDINGS = Path(__file__).parent / "recordings" / "live"
SKIP = {"wait_for_request", "wait_for_email", "follow_email_link"}
pytestmark = pytest.mark.skipif(not (RECORDINGS / "tools.json").exists(), reason="no live recordings yet")


def _load() -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    calls = json.loads((RECORDINGS / "tools.json").read_text(encoding="utf-8"))["calls"]
    by_seq: dict[int, list[dict[str, Any]]] = defaultdict(list)
    seq = 0
    for line in (RECORDINGS / "http.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry["kind"] == "tool":
            seq = entry["seq"]
        else:
            by_seq[seq].append(entry)
    return calls, by_seq


def _cases() -> list[tuple[str, dict[str, Any], dict[str, Any], list[dict[str, Any]]]]:
    if not (RECORDINGS / "tools.json").exists() or not (RECORDINGS / "http.jsonl").exists():
        return []
    calls, by_seq = _load()
    cases = []
    for call in calls:
        if call["tool"] in SKIP:
            continue
        cases.append((call["tool"], call["args"], call["result"], by_seq.get(call["seq"], [])))
    return cases


def _response(entry: dict[str, Any]) -> httpx.Response:
    headers = {}
    if entry.get("content_type"):
        headers["content-type"] = entry["content_type"]
    if entry.get("location"):
        headers["location"] = entry["location"]
    if entry["response_is_text"]:
        return httpx.Response(entry["status"], text=entry["response"], headers=headers)
    return httpx.Response(entry["status"], json=entry["response"], headers=headers)


class _Ctx:
    def __init__(self, app: AppContext) -> None:
        self.request_context = type("RC", (), {"lifespan_context": app})()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,args,expected,exchanges", _cases(), ids=lambda v: v if isinstance(v, str) else "")
async def test_replayed_tool_call_matches_live_result(tool, args, expected, exchanges) -> None:
    import server

    queues: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in exchanges:
        queues[(entry["method"], entry["url"])].append(entry)

    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        for (method, url), entries in queues.items():
            router.route(method=method, url=url).mock(side_effect=[_response(e) for e in entries])
        async with WebhookHttpClient(api_key="recorded") as client:
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
            # Go through the SDK's Tool.run so argument validation and JSON
            # pre-parsing happen exactly as they did for the live client.
            registered = server.mcp._tool_manager.get_tool(tool)  # type: ignore[attr-defined]
            result = await registered.run(args, context=_Ctx(app))
    assert result == expected
