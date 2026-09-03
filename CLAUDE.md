# webhook-mcp-server — working rules

MCP server for webhook.site. 28 tools in `handlers/tools.py`, services in `services/`, HTTP client and helpers in `utils/`.

## Truth comes from the live API, not from docs or mocks

- webhook.site's docs were wrong in several places (paths, required fields, response shapes). Before relying on any endpoint, call it for real with `WEBHOOK_SITE_API_KEY` and look at the actual response. Record what you saw in the code comment or the CHANGELOG.
- A test is only valid if its expectation was checked against real behaviour. Never write a mock whose response shape you invented. Use recorded real responses (`tests/recordings/`) or a live test. A green test that encodes a guess is worse than no test.
- After any change to a service or tool, run the real check: `WEBHOOK_SITE_API_KEY=... python scripts/live_tool_check.py --record tests/recordings/live` (drives `server.py` over stdio, calls every tool, cleans up, refreshes the recordings). Then `pytest -m "not live and not live_auth"` (includes the replay of those recordings), `pytest -m live`, `pytest -m live_auth`.
- Custom Action knowledge lives in `utils/action_types.json`. Regenerate from the docs with `scripts/gen_action_types.py ../docs/api/action-types.md`, then re-verify live with `scripts/verify_action_types.py`; never hand-edit the `verified` blocks.
- Verify both sides: that the call succeeds, and that the effect happened (the alias answers, the note is stored, the email arrived). A 200 alone proves nothing.

## Account safety while testing

- The key lives in `../docs/.env.local` (line `## API Key: <uuid>`), outside the repo. Read it into `WEBHOOK_SITE_API_KEY` for a run; never print it, never commit it, never read that file from tests.
- Tokens created with the key are permanent. Every test or probe must delete what it creates in a `finally`, then confirm with `list_webhooks`.
- Custom actions run on incoming emails too. Any `send_email` action to a token's own inbox must be guarded by a `condition` action on `$request.type$` or it loops (37 emails in a minute, seen).
- Do not invite or delete users, and do not send email to real addresses.
- Never point an outbound action (`http`, `send_request`, `slack_send_message`, schedules) at a webhook.site URL, including the token's own. The platform detects the recursion, disables the action and emails the account owner. Use `https://example.com/` as the harmless target in probes.

## Product stance

- Users with a key pay for their plan; do not remove capability for security. Use MCP tool annotations, not gates. The one hard line is `follow_email_link`, which only opens public hosts unless `FOLLOW_EMAIL_LINK_ALLOW_HOSTS` allows more.
- Free-text tool fields that may carry JSON must be typed `JsonText` (the MCP SDK pre-parses JSON-looking strings).
- The API replaces records on PUT. Every update merges into the saved record first.
- `POST /token` ignores `listen`; only PUT sets it. Set Response (`PUT /request/{id}/response`) returns `{"status": 3}` when it reached a waiting caller and `2` when nothing was waiting; a request is only held while `listen > 0` and a socket listener is subscribed (see `respond_to_next_request` and the open-source `whcli`).
- Custom action `name` is real but a PUT without it clears it: merge it like every other field. `test-action?action_id=` does not change the saved action.
- `conditions` (plural) accepts regex/nex/null/nnull; the singular `condition` answers "Unknown operator" for them. set_variable has modes math and random_number. `database` accepts type whdb + db_id. These came from the frontend bundle (`e.actionConditionOperators`, the action default map) and were confirmed with test-action; keep such findings in `LIVE_ADDITIONS` in `scripts/gen_action_types.py` so a regen does not lose them.
- The current mail domain is `{token}@emailhook.site` (verified delivering); `email.webhook.site` still works. `POST /{token}/{status}` forces that status. `alias: null` on PUT removes an alias. Notes are capped at 10000 characters. request_limit above 10000 is accepted where the plan allows it (20000 on Pro).
- Alias lookups are cached by webhook.site for about 120 s: after any read by alias (API or capture URL), a PUT changes the UUID URL at once but the alias URL keeps the old settings until the cache expires (measured 2026-09-04). Also, idle keep-alive connections get dropped after a few seconds; the client expires them at 4 s and retries idempotent calls once.
- `GET /token/{alias}` resolves an alias to its token (docs say aliases are not accepted in API URLs; only the sub-resource paths 404). Every tool accepts a UUID, alias, webhook.site URL or inbox address and resolves it once in `_execute`. `query=sorting:>N` is a reliable "newer than" cursor (`since` / `next_since`).
- WebhookScript names: `utils/webhookscript.json` is generated from `../docs/webhookscript` and every name is called live by `scripts/verify_webhookscript.py`; the docs' `base64_urlencode` and `number_length` do not exist, `base64url_encode`, `get`, `get_variable`, `length` do.
- Keep the catalog under the token budget in `tests/test_unit.py` and keep every description honest about what the tool actually does (see `update_request`'s Set Response note).

## Docs

- `docs/TOOLS.md` is generated: after changing any tool signature or description run `python scripts/gen_tool_docs.py`; `tests/test_docs_current.py` fails otherwise, and also fails if README's Tools Reference misses a tool or the badge count is wrong.

## Model evals

- `evals/prompts/*.jsonl` + `evals/run_evals.py` drive headless `claude -p` with only this server attached and score tool choice and arguments. They cost real money and create real resources; run them only when the owner asks (release testing), never as part of routine verification.

## Release

- Commit at each verified step; do not push or tag until the whole plan is done and `scripts/live_tool_check.py` is 100% green.
- Versions to bump together: `pyproject.toml`, `server.json` (two fields), README install pins, CHANGELOG.
