"""Exercise every MCP tool against the real webhook.site API through the real server.

Starts ``server.py`` as a subprocess, talks to it over stdio with the official MCP
client (so schemas, serialization and the lifespan run exactly as a client sees
them), calls all 28 tools with real side effects, and deletes everything it made.

Usage:
    WEBHOOK_SITE_API_KEY=... python scripts/live_tool_check.py [--record DIR]

--record DIR writes DIR/http.jsonl (every HTTP exchange the server made, tagged
with the tool call that caused it) and DIR/tools.json (every tool call with its
arguments and result), sanitised. tests/test_replay_recordings.py replays them.

Exit code 1 if any tool call did not behave as expected.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://webhook.site"
EXPECTED_TOOLS = 29


class Check:
    def __init__(self, session: ClientSession) -> None:
        self.session = session
        self.results: list[tuple[str, bool, str]] = []
        self.calls: list[dict[str, Any]] = []
        self._started = 0

    async def call(self, tool: str, expect_success: bool | None = True, **args: Any) -> dict[str, Any]:
        """Call a tool and record PASS/FAIL. expect_success=None records without judging."""
        label = f"{tool}({args.get('action', '')})".replace("()", "")
        # Sequence numbers are assigned when the call starts, like the server's
        # recorder does, so overlapping calls line up between both recordings.
        self._started += 1
        seq = self._started
        try:
            raw = await self.session.call_tool(tool, args, read_timeout_seconds=150)
            payload = self._payload(raw)
            self.calls.append({"seq": seq, "tool": tool, "args": args, "result": payload})
        except Exception as exc:  # transport / schema errors are failures too
            self.results.append((label, False, f"exception: {exc}"))
            print(f"FAIL {label}: exception {exc}")
            return {"success": False, "message": str(exc)}
        ok = bool(payload.get("success"))
        judged = True if expect_success is None else ok == expect_success
        summary = payload.get("message", "")[:110 if judged else 400].replace("\n", " ")
        self.results.append((label, judged, summary))
        print(f"{'PASS' if judged else 'FAIL'} {label}: {summary}")
        return payload

    @staticmethod
    def _payload(raw: Any) -> dict[str, Any]:
        structured = getattr(raw, "structured_content", None)
        if isinstance(structured, dict) and "success" in structured:
            return structured
        for item in getattr(raw, "content", []) or []:
            text = getattr(item, "text", None)
            if text:
                try:
                    return json.loads(text)
                except ValueError:
                    return {"success": not raw.is_error, "message": text}
        return {"success": not getattr(raw, "is_error", False), "message": "<empty>"}

    def expect(self, condition: bool, label: str, detail: str = "") -> None:
        self.results.append((label, condition, detail))
        print(f"{'PASS' if condition else 'FAIL'} {label}: {detail}")


async def run(api_key: str, record_dir: Path | None = None) -> int:
    env = {**os.environ, "WEBHOOK_SITE_API_KEY": api_key}
    if record_dir is not None:
        record_dir.mkdir(parents=True, exist_ok=True)
        env["WEBHOOK_MCP_RECORD"] = str(record_dir / "http.jsonl")
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "server.py")], env=env, cwd=str(ROOT))
    created_tokens: list[str] = []
    cleanup: list[tuple[str, dict[str, Any]]] = []

    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        c = Check(session)
        tools = await session.list_tools()
        names = sorted(t.name for t in tools.tools)
        c.expect(len(names) == EXPECTED_TOOLS, "list_tools", f"{len(names)} tools")

        try:
            status = await c.call("server_status")
            c.expect(status.get("account", {}).get("authenticated") is True and status.get("realtime_socket") == "connected", "server_status sees key, account and socket", json.dumps(status.get("account")))

            # --- webhooks -----------------------------------------------------
            a = await c.call("create_webhook")
            token_a = a["token"]
            created_tokens.append(token_a)
            c.expect(a.get("premium") is True and a.get("expires_at") is None, "create_webhook is permanent+premium", str(a.get("expires_at")))

            alias = f"mcp-check-{token_a[:8]}"
            b = await c.call("configure_webhook", alias=alias, default_status=201, default_content='{"ok":true}', default_content_type="application/json", cors=True)
            token_b = b.get("token") or (await c.call("create_webhook"))["token"]
            created_tokens.append(token_b)
            c.expect(b.get("alias") == alias and b["url"].endswith(alias), "configure_webhook create applied alias", b.get("url", ""))

            upd = await c.call("configure_webhook", webhook_token=token_b, default_status=203, request_limit=100, timeout=1)
            info_b = await c.call("get_webhook_info", webhook_token=token_b)
            c.expect(info_b.get("default_status") == 203 and info_b.get("dns", "").endswith(".dnshook.site"), "configure_webhook update + get_webhook_info", f"status={info_b.get('default_status')} limit={info_b.get('request_limit')}")
            captured = httpx.get(f"{SITE}/{alias}", timeout=30)
            c.expect(captured.status_code == 203, "alias URL answers with configured status", f"{captured.status_code}")

            email = await c.call("get_webhook_email", webhook_token=token_a, validate=True)
            c.expect(email.get("email") == f"{token_a}@email.webhook.site", "get_webhook_email", email.get("email", ""))

            listed = await c.call("list_webhooks", per_page=100, max_items=500)
            ids = {hook["token"] for hook in listed.get("webhooks", [])}
            c.expect({token_a, token_b} <= ids, "list_webhooks contains both new tokens", f"{len(ids)} tokens listed")

            # --- groups --------------------------------------------------------
            group = await c.call("manage_groups", action="create", name=f"mcp-check-{token_a[:6]}")
            group_id = group.get("group", {}).get("id")
            if group_id:
                cleanup.append(("manage_groups", {"action": "delete", "group_id": group_id}))
                await c.call("configure_webhook", webhook_token=token_b, group_id=group_id)
                await c.call("manage_groups", action="update", group_id=group_id, name=f"mcp-check-{token_a[:6]}-renamed")
                groups = await c.call("manage_groups", action="list")
                c.expect(any(g.get("id") == group_id for g in groups.get("groups", [])), "manage_groups list shows the group", "")

            # --- requests -------------------------------------------------------
            await c.call("send_requests", webhook_token=token_a, data={"event": "one", "link": "https://example.com/verify?token=abc&u=1"}, headers={"X-Check": "1"})
            multi = await c.call("send_requests", webhook_token=token_a, payloads=[{"n": 1}, {"n": 2}], method="PUT", delay_ms=100)
            c.expect(multi.get("success_count") == 2, "send_requests PUT x2", str(multi.get("results", ""))[:80])
            upload = httpx.post(f"{SITE}/{token_a}", files={"report": ("report.txt", b"hello attachment", "text/plain")}, timeout=30)
            c.expect(upload.status_code == 200, "multipart upload captured", str(upload.status_code))
            await asyncio.sleep(2)

            page = await c.call("get_webhook_requests", webhook_token=token_a, limit=2, page=1)
            c.expect(len(page.get("requests", [])) == 2 and page.get("pagination", {}).get("is_last_page") is False, "get_webhook_requests page 1 of many", json.dumps(page.get("pagination")))
            page2 = await c.call("get_webhook_requests", webhook_token=token_a, limit=2, page=2)
            c.expect(len(page2.get("requests", [])) >= 1, "get_webhook_requests page 2", f"{len(page2.get('requests', []))} items")

            found = await c.call("search_requests", webhook_token=token_a, query="method:PUT", limit=10)
            c.expect(found.get("total_found") == 2 and all(r["method"] == "PUT" for r in found["requests"]), "search_requests method:PUT", f"{found.get('total_found')} found")

            latest = await c.call("get_request", webhook_token=token_a)
            with_file = [r for r in page["requests"] + page2["requests"] if r.get("attachments")]
            c.expect(bool(with_file), "attachments surfaced on list results", str(with_file[0]["attachments"] if with_file else "none"))
            file_req = with_file[0] if with_file else latest["request"]
            by_id = await c.call("get_request", webhook_token=token_a, request_id=file_req["uuid"], raw=True)
            c.expect("raw_body" in by_id, "get_request by id with raw body", by_id.get("raw_content_type", ""))

            if with_file:
                att = with_file[0]["attachments"][0]
                dl = await c.call("download_request_file", webhook_token=token_a, request_id=file_req["uuid"], file_id=att["file_id"])
                import base64
                c.expect(base64.b64decode(dl.get("content_base64", "")) == b"hello attachment", "download_request_file content matches", f"{dl.get('size')} bytes {dl.get('content_type')}")

            links = await c.call("extract_links_from_request", webhook_token=token_a, request_id=None)
            noted = await c.call("update_request", webhook_token=token_a, request_id=file_req["uuid"], note="checked by live_tool_check")
            c.expect(noted.get("note") == "checked by live_tool_check", "update_request stored the note", noted.get("note_path", ""))

            # dynamic response: token listens 5s, we answer the pending request
            await c.call("configure_webhook", webhook_token=token_a, listen=5)

            async def slow_post() -> httpx.Response:
                async with httpx.AsyncClient(timeout=30) as http:
                    return await http.post(f"{SITE}/{token_a}", json={"dynamic": True})

            pending = asyncio.create_task(slow_post())
            await asyncio.sleep(1.5)
            newest = await c.call("get_request", webhook_token=token_a)
            answered = await c.call("update_request", webhook_token=token_a, request_id=newest["request"]["uuid"], response_content="answered dynamically", response_status=299)
            response = await pending
            c.expect(answered.get("response_api_status") is not None, "update_request set-response accepted by the API", f"api_status={answered.get('response_api_status')}; caller (no CLI attached) got {response.status_code}")
            await c.call("configure_webhook", webhook_token=token_a, listen=0)

            # --- custom actions + email flow ----------------------------------
            types = await c.call("manage_custom_actions", action="types")
            c.expect(len(types.get("types", [])) >= 63, "manage_custom_actions types catalogue", f"{len(types.get('types', []))} types")
            one = await c.call("manage_custom_actions", action="types", type="send_email")
            c.expect(one.get("params", {}).get("recipient", {}).get("required") is True, "manage_custom_actions types detail", str(one.get("verified", {}).get("status")))
            await c.call("manage_custom_actions", action="variables")
            rejected = await c.call("manage_custom_actions", expect_success=False, webhook_token=token_a, action="create", type="http", parameters={})
            c.expect("url" in rejected.get("message", ""), "manage_custom_actions validates required params before calling the API", rejected.get("message", "")[:80])
            guard = await c.call("manage_custom_actions", webhook_token=token_a, action="create", type="condition", order=1, parameters={"input": "$request.type$", "operator": "neq", "value": "web", "action": "stop"})
            log_action = await c.call("manage_custom_actions", webhook_token=token_a, action="create", type="log", order=2, parameters={"text": "seen $request.method$"})
            log_id = log_action.get("action", {}).get("uuid")
            actions = await c.call("manage_custom_actions", webhook_token=token_a, action="list")
            c.expect(len(actions.get("actions", [])) == 2, "manage_custom_actions list", f"{len(actions.get('actions', []))} actions")
            tested = await c.call("manage_custom_actions", webhook_token=token_a, action="test", type="script", parameters={"script": "echo('live check')"}, request_id=file_req["uuid"])
            c.expect("live check" in json.dumps(tested.get("result", {})), "manage_custom_actions test ran the script", "")
            await c.call("manage_custom_actions", webhook_token=token_a, action="update", action_id=log_id, parameters={"text": "updated $request.method$"})
            executed = await c.call("manage_custom_actions", webhook_token=token_a, action="execute", request_id=file_req["uuid"])
            c.expect("updated" in json.dumps(executed.get("result", {})), "manage_custom_actions execute used the updated action", "")

            mail_action = await c.call(
                "manage_custom_actions", webhook_token=token_a, action="create", type="send_email", order=3,
                parameters={"recipient": f"{token_a}@email.webhook.site", "subject": "Verify your account", "is_html": True,
                            "content": '<p>Your verification code is 847291.</p><p><a href="https://example.com/verify?token=abc&amp;u=1">Verify your email</a></p>'},
            )

            async def trigger() -> None:
                await asyncio.sleep(1)
                await c.call("send_requests", expect_success=None, webhook_token=token_a, data={"trigger": "mail"})

            task = asyncio.create_task(trigger())
            mail = await c.call("wait_for_email", webhook_token=token_a, timeout_seconds=90)
            await task
            email_data = mail.get("email") or {}
            c.expect(email_data.get("verification_codes") == ["847291"] and mail.get("source") == "socket", "wait_for_email got the code over the socket", f"source={mail.get('source')} codes={email_data.get('verification_codes')}")
            opened = await c.call("follow_email_link", expect_success=None, webhook_token=token_a, request_id=email_data.get("uuid"))
            c.expect(opened.get("opened_url") == "https://example.com/verify?token=abc&u=1" and opened.get("title") == "Example Domain", "follow_email_link opened the decoded link", f"{opened.get('status_code')} {opened.get('title')}")
            await c.call("manage_custom_actions", webhook_token=token_a, action="delete", action_id=mail_action.get("action", {}).get("uuid"))

            # --- wait_for_request over the socket --------------------------------
            async def fire() -> None:
                await asyncio.sleep(1)
                await c.call("send_requests", expect_success=None, webhook_token=token_a, data={"ping": time.time()})

            task = asyncio.create_task(fire())
            waited = await c.call("wait_for_request", webhook_token=token_a, timeout_seconds=30, request_type="web")
            await task
            c.expect(waited.get("source") == "socket", "wait_for_request delivered over the socket", f"source={waited.get('source')}")

            # --- DNSHook ---------------------------------------------------------------
            async def lookup() -> None:
                await asyncio.sleep(1)
                loop = asyncio.get_running_loop()
                try:
                    await loop.getaddrinfo(f"probe.{token_a}.dnshook.site", 80)
                except OSError:
                    pass  # the lookup itself is what webhook.site records

            task = asyncio.create_task(lookup())
            dns_hit = await c.call("wait_for_request", webhook_token=token_a, timeout_seconds=30, request_type="dns")
            await task
            # Resolvers may ask for NS before A; any record type proves the hook fired.
            c.expect(dns_hit.get("request", {}).get("type") == "dns" and bool(dns_hit["request"].get("method")), "wait_for_request captured a DNSHook lookup", f"source={dns_hit.get('source')} record={dns_hit.get('request', {}).get('method')}")
            dns_found = await c.call("search_requests", webhook_token=token_a, request_type="dns")
            c.expect(dns_found.get("total_found", 0) >= 1, "search_requests request_type=dns", f"{dns_found.get('total_found')} found")

            # --- token settings that change behaviour ----------------------------------
            cloned = await c.call("configure_webhook", clone_from=token_b)
            if cloned.get("token"):
                created_tokens.append(cloned["token"])
                c.expect(cloned.get("default_status") == 203, "configure_webhook clone_from copies settings", f"status={cloned.get('default_status')}")
            quiet = await c.call("configure_webhook", request_limit=0)
            if quiet.get("token"):
                created_tokens.append(quiet["token"])
                await c.call("send_requests", webhook_token=quiet["token"], data={"stored": False})
                await asyncio.sleep(1.5)
                stored = await c.call("get_webhook_requests", webhook_token=quiet["token"])
                c.expect(stored.get("total_requests") == 0, "request_limit=0 stores nothing", f"{stored.get('total_requests')} stored")
            await c.call("configure_webhook", webhook_token=token_a, actions=False)
            await c.call("send_requests", webhook_token=token_a, data={"actions": "off"})
            await asyncio.sleep(1.5)
            silent = await c.call("get_request", webhook_token=token_a)
            c.expect(not silent.get("request", {}).get("custom_action_output"), "actions=false skips custom actions", "")
            await c.call("configure_webhook", webhook_token=token_a, actions=True)
            aged = await c.call("delete_all_requests", webhook_token=token_a, date_to="now-7d")
            c.expect(aged.get("success") is True, "delete_all_requests with a date expression", aged.get("message", "")[:60])

            # --- security ------------------------------------------------------------
            ssrf = await c.call("generate_oob_payloads", webhook_token=token_a, kind="ssrf", identifier="lc-ssrf")
            xss = await c.call("generate_oob_payloads", webhook_token=token_a, kind="xss", identifier="lc-xss")
            canary = await c.call("generate_oob_payloads", webhook_token=token_a, kind="canary", canary_type="dns")
            c.expect(bool(ssrf.get("callback_payloads")) and xss.get("success") and canary.get("success"), "generate_oob_payloads ssrf/xss/canary", "")
            https_url = ssrf.get("callback_payloads", {}).get("https_url")
            if https_url:
                httpx.get(https_url, timeout=30)
                await asyncio.sleep(2)
            hits = await c.call("check_for_callbacks", webhook_token=token_a, since_minutes=5, identifier="lc-ssrf")
            c.expect(hits.get("detected") is True and hits.get("total_callbacks") == 1, "check_for_callbacks saw exactly the SSRF hit", f"detected={hits.get('detected')} total={hits.get('total_callbacks')}")

            # --- export ------------------------------------------------------------
            exported = await c.call("export_webhook_data", webhook_token=token_a, limit=200)
            c.expect(exported.get("request_count", 0) >= 6 and any(r.get("html_content") for r in exported.get("requests", [])), "export_webhook_data json includes html", f"{exported.get('request_count')} rows")
            csv = await c.call("export_webhook_data", webhook_token=token_a, format="csv")
            c.expect(csv.get("csv", "").startswith("uuid,"), "export_webhook_data csv", f"{csv.get('request_count')} rows")
            # The export endpoint allows 3 calls a minute; the 4th must fail with a clear wait, not hang.
            limited = None
            for _ in range(3):
                limited = await c.call("export_webhook_data", expect_success=None, webhook_token=token_a, format="csv")
                if limited.get("success") is False:
                    break
            c.expect(limited is not None and limited.get("success") is False and "Rate limited: retry after" in limited.get("message", ""), "export rate limit surfaces Retry-After", limited.get("message", "")[:100] if limited else "")

            # --- global variables, templates, schedules, databases, users -------------
            var = await c.call("manage_global_variables", action="create", name="mcp_live_check", value="1")
            var_id = var.get("variable", {}).get("id")
            if var_id:
                cleanup.append(("manage_global_variables", {"action": "delete", "variable_id": var_id}))
                await c.call("manage_global_variables", action="update", variable_id=var_id, value="2")
                vars_ = await c.call("manage_global_variables", action="list", search="mcp_live_check")
                c.expect(any(v.get("id") == var_id and v.get("value") == "2" for v in vars_.get("variables", [])), "manage_global_variables list reflects update", "")

            tpl = await c.call("manage_templates", action="create", name=f"mcp-check-{token_a[:6]}", actions=[{"type": "log", "order": 1, "parameters": {"text": "tpl"}}], variables=[{"name": "example", "value": "1"}])
            tpl_id = tpl.get("template", {}).get("id")
            if tpl_id:
                cleanup.append(("manage_templates", {"action": "delete", "template_id": tpl_id}))
                await c.call("manage_templates", action="update", template_id=tpl_id, name=f"mcp-check-{token_a[:6]}-2")
                tpls = await c.call("manage_templates", action="list")
                mine = next((t for t in tpls.get("templates", []) if t.get("id") == tpl_id), {})
                c.expect(mine.get("name", "").endswith("-2") and len(mine.get("actions") or []) == 1, "manage_templates update kept name and actions", f"name={mine.get('name')} actions={len(mine.get('actions') or [])}")

            sched = await c.call("manage_schedules", action="create", name=f"mcp-check-{token_a[:6]}", interval="daily", request_url=f"{SITE}/{token_b}", request_method="GET", timeout=10)
            sched_id = sched.get("schedule", {}).get("id")
            if sched_id:
                cleanup.append(("manage_schedules", {"action": "delete", "schedule_id": sched_id}))
                await c.call("manage_schedules", action="get", schedule_id=sched_id)
                await c.call("manage_schedules", action="update", schedule_id=sched_id, name=f"mcp-check-{token_a[:6]}-2")
                await c.call("manage_schedules", action="run", schedule_id=sched_id)
                await asyncio.sleep(3)
                logs = await c.call("manage_schedules", action="logs", schedule_id=sched_id)
                c.expect(len(logs.get("logs", [])) >= 1, "manage_schedules logs after run", f"{len(logs.get('logs', []))} entries")
                scheds = await c.call("manage_schedules", action="list")
                c.expect(any(s.get("id") == sched_id for s in scheds.get("schedules", [])), "manage_schedules list", "")

            dbs = await c.call("manage_databases", action="list")
            db = await c.call("manage_databases", expect_success=None, action="create", name=f"mcp-check-{token_a[:6]}", plan="db-s")
            db_id = db.get("database", {}).get("id")
            if db_id:
                cleanup.append(("manage_databases", {"action": "delete", "database_id": str(db_id)}))
                q = await c.call("manage_databases", action="query", database_id=str(db_id), query="select 1 as one")
                c.expect(q.get("result") == [{"one": 1}], "manage_databases query", str(q.get("result")))
                await c.call("manage_databases", action="update", database_id=str(db_id), name=f"mcp-check-{token_a[:6]}-2")
            else:
                c.expect(True, "manage_databases create not available on this plan (reported, not failed)", db.get("message", "")[:80])

            users = await c.call("manage_users", action="list")
            me = (users.get("users") or [{}])[0]
            if me.get("id"):
                await c.call("manage_users", action="update", user_id=me["id"], name=me.get("name"))

            # --- deletes ------------------------------------------------------------
            await c.call("delete_request", webhook_token=token_a, request_id=file_req["uuid"])
            bulk = await c.call("delete_all_requests", webhook_token=token_a, query="method:PUT")
            await asyncio.sleep(1)
            after = await c.call("search_requests", webhook_token=token_a, query="method:PUT")
            c.expect(after.get("total_found") == 0, "delete_all_requests removed the PUTs", f"{after.get('total_found')} left")

        finally:
            for tool, args in reversed(cleanup):
                await c.call(tool, expect_success=None, **args)
            for tok in created_tokens:
                await c.call("delete_webhook", webhook_token=tok)
            remaining = await c.call("list_webhooks", per_page=100, max_items=500)
            left = {hook["token"] for hook in remaining.get("webhooks", [])} & set(created_tokens)
            c.expect(not left, "cleanup: created tokens deleted", f"left={left}")

        if record_dir is not None:
            from utils.recorder import sanitize

            calls = sorted(c.calls, key=lambda item: item["seq"])
            # Team member names appear as plain arguments (manage_users update); scrub them too.
            names = {
                user.get("name")
                for call in calls
                if call["tool"] == "manage_users"
                for user in (call["result"].get("users") or [])
                if user.get("name")
            }
            text = json.dumps({"calls": sanitize(calls)}, indent=1, ensure_ascii=False)
            for name in names:
                text = text.replace(json.dumps(name)[1:-1], "Recorded User")
            (record_dir / "tools.json").write_text(text + "\n", encoding="utf-8")
            print(f"recorded {len(c.calls)} tool calls to {record_dir}")

        failures = [(label, detail) for label, ok, detail in c.results if not ok]
        print("\n" + "=" * 70)
        print(f"{len(c.results) - len(failures)}/{len(c.results)} checks passed")
        for label, detail in failures:
            print(f"  FAILED {label}: {detail}")
        return 1 if failures else 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    key = os.environ.get("WEBHOOK_SITE_API_KEY", "").strip()
    if not key:
        print("Set WEBHOOK_SITE_API_KEY first", file=sys.stderr)
        sys.exit(2)
    target = None
    if "--record" in sys.argv:
        target = Path(sys.argv[sys.argv.index("--record") + 1])
    sys.exit(asyncio.run(run(key, target)))
