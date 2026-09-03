"""Model-in-the-loop evaluation: does Claude pick the right tool and arguments from a natural prompt?

Each prompt in evals/prompts/*.jsonl is given to headless Claude Code with only
this MCP server attached. The tool calls it makes are scored against the
prompt's expectations. Nothing is mocked: the server talks to webhook.site,
so this needs WEBHOOK_SITE_API_KEY and a signed-in `claude` CLI.

Usage:
    WEBHOOK_SITE_API_KEY=... python evals/run_evals.py [--only id,id] [--group name] [--model m]

Writes evals/results/<timestamp>.json and a markdown summary next to it, and
deletes every webhook the model created (tokens are parsed from tool results).

Expectation keys:
    tools    ordered list of tool names that must all be called (in that order)
    any_of   list of alternatives, one of which must be called
    forbid   tool names (or "tool:action") that must not be called
    args     {tool: {needle: regex}}: for every call of `tool`, at least one
             call's JSON-serialised input must contain a match for each regex,
             after "needle" (the key name, or any text)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "evals" / "prompts"
RESULTS = ROOT / "evals" / "results"
MCP_CONFIG = ROOT / "evals" / "mcp.json"
TOOL_PREFIX = "mcp__webhook__"
SYSTEM_NOTE = (
    "You are being evaluated on an MCP server for webhook.site. Use its tools to do exactly what the user asks, "
    "then answer briefly. Do not ask clarifying questions; make reasonable choices. Never invite or delete users."
)


def load_prompts(only: set[str] | None, group: str | None) -> list[dict[str, Any]]:
    prompts: list[dict[str, Any]] = []
    for path in sorted(PROMPTS.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if only and item["id"] not in only:
                continue
            if group and item.get("group") != group:
                continue
            prompts.append(item)
    return prompts


def run_claude(prompt: str, model: str | None, budget: float) -> tuple[list[dict[str, Any]], str, str]:
    """Run one headless session; return (tool calls, final text, raw stream)."""
    cmd = [
        "claude", "-p", prompt,
        "--mcp-config", str(MCP_CONFIG),
        "--strict-mcp-config",
        "--allowedTools", f"{TOOL_PREFIX}*",
        "--output-format", "stream-json",
        "--verbose",
        "--append-system-prompt", SYSTEM_NOTE,
        "--max-budget-usd", str(budget),
    ]
    if model:
        cmd += ["--model", model]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600, shell=os.name == "nt")
    calls: list[dict[str, Any]] = []
    results_by_id: dict[str, Any] = {}
    final = ""
    for line in proc.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        message = event.get("message") or {}
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use" and str(block.get("name", "")).startswith(TOOL_PREFIX):
                calls.append({"id": block.get("id"), "tool": block["name"][len(TOOL_PREFIX):], "input": block.get("input") or {}})
            if isinstance(block, dict) and block.get("type") == "tool_result":
                results_by_id[block.get("tool_use_id")] = block.get("content")
        if event.get("type") == "result":
            final = event.get("result") or ""
    for call in calls:
        call["result"] = results_by_id.get(call["id"])
    return calls, final, proc.stdout + "\n--- stderr ---\n" + proc.stderr


def tokens_created(calls: list[dict[str, Any]]) -> set[str]:
    found: set[str] = set()
    for call in calls:
        if call["tool"] in ("create_webhook", "configure_webhook") and "webhook_token" not in call["input"]:
            result = call.get("result")
            # Tool results arrive as JSON text (often inside a content list), so quotes may be escaped.
            text = (result if isinstance(result, str) else json.dumps(result)).replace('\\"', '"')
            for match in re.finditer(r'"token":\s*"([0-9a-f-]{36})"', text):
                found.add(match.group(1))
    return found


def score(item: dict[str, Any], calls: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    expect = item.get("expect", {})
    called = [c["tool"] for c in calls]
    problems: list[str] = []

    position = 0
    for tool in expect.get("tools", []):
        try:
            position = called.index(tool, position) + 1
        except ValueError:
            problems.append(f"expected {tool} to be called" + (" after the previous expected tools" if position else ""))

    alternatives = expect.get("any_of")
    if alternatives and not any(all(t in called for t in alt) for alt in alternatives):
        problems.append(f"expected one of {alternatives}")

    for forbidden in expect.get("forbid", []):
        tool, _, action = forbidden.partition(":")
        for call in calls:
            if call["tool"] == tool and (not action or call["input"].get("action") == action):
                problems.append(f"{forbidden} must not be called")
                break

    for tool, needles in expect.get("args", {}).items():
        inputs = [json.dumps(c["input"], ensure_ascii=False) for c in calls if c["tool"] == tool]
        if not inputs:
            continue  # missing tool already reported
        for needle, pattern in needles.items():
            if not any(re.search(pattern, text[text.find(needle):] if needle in text else "", re.IGNORECASE) for text in inputs):
                problems.append(f"{tool}: expected {needle!r} matching /{pattern}/ in some call")
    return not problems, problems


def main() -> int:
    global MCP_CONFIG
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="comma-separated prompt ids")
    parser.add_argument("--group")
    parser.add_argument("--model")
    # The first turn alone costs ~0.7 USD on large models (catalog + system prompt cache creation).
    parser.add_argument("--budget", type=float, default=5.0, help="max USD per prompt (default 5)")
    parser.add_argument("--mcp-config", default=str(MCP_CONFIG),
                        help="MCP config to attach (default evals/mcp.json runs the checkout; evals/mcp.published.json runs the PyPI release via uvx)")
    args = parser.parse_args()
    MCP_CONFIG = Path(args.mcp_config)
    if not os.environ.get("WEBHOOK_SITE_API_KEY"):
        print("Set WEBHOOK_SITE_API_KEY", file=sys.stderr)
        return 2

    prompts = load_prompts(set(args.only.split(",")) if args.only else None, args.group)
    RESULTS.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    report: list[dict[str, Any]] = []
    created: set[str] = set()
    for item in prompts:
        calls, final, raw = run_claude(item["prompt"], args.model, args.budget)
        ok, problems = score(item, calls)
        created |= tokens_created(calls)
        report.append({"id": item["id"], "group": item.get("group"), "ok": ok, "problems": problems, "calls": [{"tool": c["tool"], "input": c["input"]} for c in calls], "answer": final[:1000]})
        (RESULTS / f"{stamp}-{item['id']}.stream.txt").write_text(raw, encoding="utf-8")
        print(f"{'PASS' if ok else 'FAIL'} {item['id']:14} {' -> '.join(c['tool'] + ('(' + str(c['input'].get('action')) + ')' if c['input'].get('action') else '') for c in calls) or '(no tool calls)'}")
        for problem in problems:
            print(f"       {problem}")

    cleanup(created)
    passed = sum(1 for r in report if r["ok"])
    (RESULTS / f"{stamp}.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    lines = [f"# Eval run {stamp}", "", f"{passed}/{len(report)} prompts passed", ""]
    for r in report:
        lines.append(f"- {'PASS' if r['ok'] else 'FAIL'} `{r['id']}`: " + (", ".join(r["problems"]) or " ".join(c["tool"] for c in r["calls"])))
    (RESULTS / f"{stamp}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n{passed}/{len(report)} passed; report in {RESULTS / (stamp + '.md')}")
    return 0 if passed == len(report) else 1


def cleanup(tokens: set[str]) -> None:
    if not tokens:
        return
    import asyncio

    sys.path.insert(0, str(ROOT))
    from services.webhook_service import WebhookService
    from utils.http_client import WebhookHttpClient

    async def run() -> None:
        async with WebhookHttpClient(api_key=os.environ["WEBHOOK_SITE_API_KEY"]) as client:
            service = WebhookService(client)
            for token in sorted(tokens):
                try:
                    await service.delete(token)
                except Exception as exc:  # already deleted by the model, or expired
                    print(f"cleanup: {token}: {exc}")
        print(f"cleanup: deleted {len(tokens)} webhooks created during the run")

    asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
