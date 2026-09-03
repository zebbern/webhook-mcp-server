# webhook-mcp-server — working rules

MCP server for webhook.site: 31 tools in `handlers/tools.py`, services in `services/`, HTTP client and helpers in `utils/`. What the platform actually does is written down in `docs/webhook-site-notes.md`; the test layers in `docs/testing.md`; the release steps in `docs/releasing.md`. Keep those pages current instead of repeating them here.

## Truth comes from the live API, not from docs or mocks

- webhook.site's docs are wrong in places (paths, required fields, response shapes, alias support). Before relying on an endpoint, call it for real with the key and look at the response. Record the finding in `docs/webhook-site-notes.md` and in the code comment next to the workaround.
- A test is only valid if its expectation was checked against real behaviour. Never invent a mock's response shape: use the recordings under `tests/recordings/` or a live test.
- After any change to a service or tool: `python scripts/live_tool_check.py --record tests/recordings/live` with the key, then `pytest -m "not live and not live_auth"` (replays the recordings), then `pytest -m live` and `pytest -m live_auth`.
- Verify both sides: that the call succeeded and that the effect happened. A 200 alone proves nothing.
- Reference data is generated and verified, never hand-edited: `utils/action_types.json` (`scripts/gen_action_types.py` + `scripts/verify_action_types.py`, live-only findings go in `LIVE_ADDITIONS`), `utils/webhookscript.json` (`scripts/gen_webhookscript.py` + `scripts/verify_webhookscript.py`), `docs/TOOLS.md` and the README tool tables (`scripts/gen_tool_docs.py`).

## Account safety while testing

- The key lives in `.env.local` at the repo root (`WEBHOOK_SITE_API_KEY="..."`, gitignored). Export it for a run; never print it, commit it, or read the file from tests. Never send it to a capture URL: the platform stores request headers.
- Tokens created with the key are permanent. Every probe deletes what it creates in a `finally`, then confirms with `list_webhooks`.
- Custom actions run on incoming emails too: guard any `send_email` to a token's own inbox with a `condition` on `$request.type$` or it loops.
- Never point an outbound action or schedule at a webhook.site URL; use `https://example.com/`. Do not invite or delete users; do not send email to real addresses.
- Opening webhook.site in a logged-in browser creates a token on the account; delete it afterwards.

## Product stance

- Users with a key pay for their plan: do not remove capability for security. Use MCP tool annotations, not gates. The one hard line is `follow_email_link`, which only opens public hosts unless `FOLLOW_EMAIL_LINK_ALLOW_HOSTS` allows more.
- Free-text tool fields that may carry JSON are typed `JsonText` (the MCP SDK pre-parses JSON-looking strings).
- The API replaces records on PUT: every update merges into the saved record first.
- Every `webhook_token` is resolved once in `_execute` (UUID, alias, URL, inbox address); tools receive the UUID.
- Keep the catalogue under the token budget in `tests/test_unit.py`, and keep every description honest about what the tool actually does.

## Model evals

- `evals/` costs real money and creates real resources. Run it only when the owner asks (release testing).

## Release

- Commit at each verified step; do not push or tag until the live tool check is fully green. Versions to bump together: `pyproject.toml`, `server.json` (two fields), README install pins, CHANGELOG.
