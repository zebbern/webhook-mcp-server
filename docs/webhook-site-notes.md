# webhook.site behaviour this server relies on

Everything here was observed against the live API (2026-09-03/04) on a Pro account, not taken from the docs. Where the official docs say something else, that is noted. The code comments and `CHANGELOG.md` reference these facts; when the platform changes, `scripts/live_tool_check.py` is what notices.

## Tokens (URLs)

- `PUT /token/{id}` replaces the whole record. A body with only `alias` resets status, content, timeout and CORS. The server reads the token first and merges every update (same for actions, schedules, templates, variables, databases, users).
- `POST /token` ignores `listen`; only `PUT` sets it. `configure_webhook` sends a follow-up `PUT` when a new token asks for `listen`.
- With an API key, tokens are permanent (`premium: true`). `expiry` (max 604800 s) is optional; `WEBHOOK_SITE_DEFAULT_EXPIRY` sets a default.
- `description` is accepted and returned although the API reference does not list it.
- `request_limit` above 10000 is accepted where the plan allows it (20000 worked on Pro; Enterprise goes to 100000). The client no longer caps it at 10000.
- `alias: null` on `PUT` removes an alias (`configure_webhook(alias="")`). Aliases are 3-32 letters, digits, `-` or `_`.
- `GET /token/{alias}` returns the token although the docs say aliases are not accepted in API URLs. Sub-resource paths such as `/token/{alias}/requests` do 404, so every tool resolves an alias to the UUID once and uses the UUID from then on.
- Alias lookups are cached by webhook.site for about 120 s. After a settings change, the alias URL keeps answering with the previous settings until that cache expires; the UUID URL reflects the change immediately. `configure_webhook` reports this as `alias_cache_note`.
- Capture forms that all work: `https://webhook.site/{id}[/any/path]`, `https://{id}.webhook.site`, and `https://webhook.site/{id}/{status}`, which forces that response status (`force_status_url` in `get_webhook_info`).
- `POST /token` is rate limited (the docs say 10/min free, 60/min paid). A 429 with `Retry-After` up to `WEBHOOK_MCP_RATE_LIMIT_MAX_WAIT` seconds is waited out once.

## Requests and search

- The list endpoint pages at most 100 items and reports `is_last_page`; `export_webhook_data` pages through it. The account-level CSV export is limited to 3 calls per minute and answers 429 with `Retry-After`.
- `/request/latest` can 404 for one or two seconds after a capture; `get_request` retries once.
- Notes go to the singular path `PUT /token/{id}/request/{rid}`; the plural path in the docs answers 404. Notes are capped at 10000 characters.
- Set Response (`PUT /token/{id}/request/{rid}/response`, base64 body) returns `{"status": 3}` when it reached a waiting caller and `2` when nothing was waiting. A request is only held while `listen > 0` and a socket listener is subscribed, which is what `respond_to_next_request` does end to end.
- The search language accepts exclusion (`-method:GET`), `_exists_:field`, `note:`, geo fields (`country_code:DE`), date ranges (`created_at:[now-1h TO now]`) and the `sorting` field: `sorting:>N` returns exactly the requests created after the one with `sorting` N. `date_from` / `date_to` take date expressions such as `now-7d`.
- `request.sorting` (microsecond timestamp) is also a Custom Action variable.
- Requests dropped by Don't Save, Rate Limit or a failed Basic Auth never appear in the API.
- DNSHook lookups arrive with `type: dns` and the record type in `method`; every subdomain of `{id}.dnshook.site` is captured.

## Email

- The mail domain is `{id}@emailhook.site` (verified delivering); `{id}@email.webhook.site` still works.
- Email objects carry `sender`, `checks` (spam, virus, spf, dkim, dmarc), `destinations`, `email_truncated`, `files` and a `text_content` derived from the HTML.

## Custom Actions

- 63 action types; each was run through `test-action` for real (`utils/action_types.json`, `manage_custom_actions(action="types")`). `test-action` needs `order`; with `action_id` it tests against a saved action without changing it, contrary to the docs.
- Actions have a `name`. A `PUT` without it clears the name, so updates merge it in.
- Actions also run on incoming emails. A `send_email` action to the token's own inbox loops unless a `condition` on `$request.type$` guards it (37 emails in a minute, seen).
- Outbound actions (`http`, `send_request`, `slack_send_message`, schedules) pointed at a webhook.site URL are detected as recursion, disabled, and the account owner gets an email.
- `execute` re-runs all saved actions on a request and overwrites the stored output; `error_notifications` defaults to off.
- `conditions` (plural) accepts the operators `regex` (with `/delimiters/`), `nex`, `null`, `nnull` on top of the documented twenty; the singular `condition` answers "Unknown operator" for those. The operator maps come from the frontend bundle (`actionConditionOperators`).
- `set_variable` has modes `text`, `random`, `random_number` (`random_number.from/to`), `date` and `math` (`round(1 + 2.5, 0)` set 4).
- `text_map` uses the condition operator codes (`ew`, `ct`, ...), not their spelled-out names.
- `database` accepts `type: whdb` with `db_id` (a Webhook.site Database) and always wants `params` (`[]` when unused).
- `send_request` is legacy (the editor no longer offers it). The editor refuses `queue` on `modify_response`, `dont_save` and `rate_limit`; the API accepts it.
- Queue Profiles live at `/queues` (not in the API docs): `name`, `amount`, `duration`, `expiry`, `delay`; `GET /queues/{id}` 404s, the list is the source. Actions reference one through `queue_id`.
- Schedules accept `require_cert_expiry` (days) in addition to the documented fields; `run-now` answers 302.
- `GET /variables` (undocumented) lists the base variable names the platform defines.

## WebhookScript

- `manage_custom_actions(action="script_reference")` lists 138 functions generated from the docs, each called on the live engine by `scripts/verify_webhookscript.py`. The documented `base64_urlencode` and `number_length` do not exist; `base64url_encode`, `get`, `get_variable` and `length` exist although undocumented.
- Custom Action variables are not substituted inside a script: use `var('request.content')`. Arithmetic is strictly typed (`5 + "4"` errors).

## Connections and limits

- webhook.site drops idle keep-alive connections after a few seconds; reusing one fails with "Server disconnected without sending a response". The client expires idle connections after 4 s and retries idempotent calls (GET, HEAD, PUT, DELETE) once. POST is never replayed.
- The real-time socket at `ws.webhook.site` accepts Engine.IO 3 and 4; channel `private-token.{id}`, event `request.created` (emails and DNS included). The waiting tools fall back to polling when it drops.
- Requests to a capture URL are stored with their headers, so the server never sends the `Api-Key` header there.

## Only in the web app (no API)

Error log, providers (OAuth and credentials for actions), custom domains, API key management, notification settings, roles, share links and the form builder. `manage_users` cannot create API keys.
