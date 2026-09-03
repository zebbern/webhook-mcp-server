# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.0.0] - 2026-09-03

Full coverage of the documented webhook.site API. With `WEBHOOK_SITE_API_KEY` set you get what your plan pays for; without it everything still works on anonymous URLs.

### Added

- `list_webhooks`, `configure_webhook` (all token settings: `listen`, `request_limit`, `actions`, `clone_from`, `group_id`, alias, expiry), `get_request` (latest or by id, `raw`), `update_request` (notes, dynamic responses), `download_request_file`
- `manage_custom_actions` (list / create / update / delete / test / execute), `manage_schedules` (incl. run-now and logs), `manage_global_variables`, `manage_groups`, `manage_templates`, `manage_databases` (incl. SQL query), `manage_users`
- `export_webhook_data` pages through the requests list (the API caps a page at 100) and can return the account's CSV export
- `wait_for_request` / `wait_for_email` listen on `ws.webhook.site` (socket.io) and fall back to polling; results carry `source`
- Emails expose `sender`, `checks` (spam, virus, SPF, DKIM, DMARC), `email_truncated` and `attachments`; list results carry `pagination`
- MCP tool annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`) on every tool
- `WEBHOOK_SITE_DEFAULT_EXPIRY` for operators who want new URLs to auto-expire
- `live_auth` test tier that runs the real sign-up flow (create URL, send a verification-style email through a Custom Action, `wait_for_email`, `follow_email_link`) when `WEBHOOK_SITE_API_KEY` is set
- `FOLLOW_EMAIL_LINK_ALLOW_HOSTS`: operator-configured hosts, `*.suffixes`, IPs or networks that `follow_email_link` may open although they are local or private (for testing your own sign-up flow on `localhost` or an intranet)
- `follow_email_link` honours `HTTPS_PROXY` / `HTTP_PROXY` / `NO_PROXY`; proxied targets are checked before the request since the proxy makes the connection
- `follow_email_link` reports a redirect refused after a completed public hop as `blocked_redirect`, with that hop's status, instead of failing the whole call
- `manage_custom_actions(action="script_reference")`: every WebhookScript function with its signature and summary, generated from the docs and checked name-by-name against the live engine (two documented names do not exist there), plus language notes (`var()` is required, strict typing, regex literals)
- Action-type reference corrections found in the frontend bundle and confirmed live: `set_variable` modes `math` and `random_number`, `conditions` operators `regex`/`nex`/`null`/`nnull` (the singular `condition` rejects them), `text_map` operator codes, `database` type `whdb` with `db_id`, the editor's no-queue types
- Custom actions carry a `name`; updates keep it (the API drops it on a bare PUT). Schedules accept `require_cert_expiry` (days before the HTTPS certificate expires)
- Every `webhook_token` accepts an alias, a pasted `https://webhook.site/...` URL, the subdomain form, the inbox address or the DNSHook name; aliases resolve through `GET /token/{alias}` (works live although the docs say otherwise)
- `configure_webhook` on an aliased token returns `alias_cache_note`: webhook.site serves the previous settings on the alias URL for about two minutes after a change (measured), the UUID URL updates at once
- `since` / `next_since` on `get_webhook_requests` and `search_requests`: a `sorting` cursor that returns only what arrived after the previous call, without paging or de-duplicating
- `configure_webhook(alias="")` removes an alias; `get_webhook_info` returns `force_status_url` (`https://webhook.site/{token}/{status}` answers with that status); `search_requests` documents exclusion (`-method:GET`), `_exists_:`, `note:` and geo fields

### Changed

- The HTTP client expires idle keep-alive connections after 4 s and retries idempotent calls once after a dropped connection (webhook.site closes idle connections after a few seconds)

- Documentation consolidated under `docs/`: generated tool reference and README tables, verified webhook.site notes, testing and releasing guides; the stale publishing guide and manual test scripts are gone
- Email addresses use the current `{token}@emailhook.site` domain (the old `email.webhook.site` form still delivers)
- `request_limit` is no longer capped client-side at 10000; the API enforces the plan's ceiling (up to 100000 on Enterprise)
- Tool merges (no capability removed): `create_webhook_with_config` + `update_webhook` -> `configure_webhook`; `get_webhook_url` + `get_webhook_dns` -> fields of `get_webhook_info`; `get_latest_request` -> `get_request`; `send_to_webhook` + `send_multiple_requests` -> `send_requests`; `generate_ssrf_payload` + `generate_xss_callback` + `generate_canary_token` -> `generate_oob_payloads`
- Tokens created with an API key are permanent by default (pass `expiry` or set `WEBHOOK_SITE_DEFAULT_EXPIRY` to change that)
- The HTTP client now raises `WebhookApiError` on failed DELETEs like every other verb, and every API error carries webhook.site's own validation message
- `configure_webhook` on an existing token no longer wipes the other settings: `PUT /token/{id}` replaces them, so a 2.x `update_webhook(cors=true)` silently reset the canned status, body and timeout. The current settings are merged in first
- Verified against the live API rather than the docs: notes and Set Response live on `/request/{id}` (singular); updates of actions, schedules, templates, global variables, databases and users send the full record because the API replaces it (a value-only variable update would have wiped its name); `run-now` answers with a redirect; `check_for_callbacks` matches the identifier anywhere in the captured request, not only in the body
- `scripts/live_tool_check.py` drives the real server over stdio and exercises all 28 tools against the live API
- `respond_to_next_request`: hold the next request and answer it with a chosen status, headers and body, the mechanism `whcli forward` uses (token `listen` set by PUT, socket listener, Set Response on the event). Verified live: the waiting caller received the reply in 0.2 s. `listen` is silently ignored by `POST /token`, so `configure_webhook` now applies it with a follow-up PUT
- Found by mapping the web app rather than the docs: `manage_queues` (Queue Profiles at `/queues`, with `queue_id` on custom actions), the `description` field on `configure_webhook`, and the live `GET /variables` names merged into the variables reference. Error log, providers, domains, API keys, notifications, roles and the form builder need a browser session and are not exposed
- `docs/TOOLS.md`, generated from the server's own catalogue (`scripts/gen_tool_docs.py`); CI fails when it or the README tool tables drift
- Real-socket tests for `follow_email_link` against a local web server and a local HTTP proxy (allowlist, `HTTP_PROXY`, `NO_PROXY`), no mocks involved
- `server_status` diagnostics tool (key, account, plan, socket, env, problems in plain words)
- Rate limits: a 429 with a short `Retry-After` is waited out and retried once (`WEBHOOK_MCP_RATE_LIMIT_MAX_WAIT`, default 15 s); longer waits are reported with the exact wait instead of hanging. A socket dropped mid-wait switches the wait tools to fast polling
- Recorded-truth tests: `scripts/live_tool_check.py --record` captures every real HTTP exchange and tool result; `tests/test_replay_recordings.py` replays them through the real service code offline and expects the recorded results, so offline CI asserts on what webhook.site actually returned
- Built-in Custom Action reference: `manage_custom_actions(action="types")` lists 63 action types (two of them, `mock` and `validate_json`, exist live but are missing from the API docs) with parameters, live-verified status and a working example; `action="variables"` lists the `$request.*$` variables checked live. Required parameters are validated before the API is called, including three the docs call optional but the API insists on. Regenerate with `scripts/gen_action_types.py` and re-verify with `scripts/verify_action_types.py`
- Catalog token budget raised to 10000 for the 31-tool catalog
- New dependency: `python-socketio[asyncio_client]`

### Fixed

- `follow_email_link` now connects to the address it vetted (no DNS rebinding), also blocks cloud metadata and NAT64 / IPv4-mapped private addresses, resolves hosts without blocking the event loop, treats a 3xx without `Location` as the final page, rejects `javascript:` and other non-http redirects cleanly, and reports the ranked `auth_links` it chose from. When an environment proxy applies, the target is checked with the resolver before the request, because the proxy makes the connection and pinning cannot apply
- `follow_email_link` picks the email that contains `url=`, or the newest email with a verify / confirm / magic link, instead of the newest email with any login link
- Link extraction ignores the raw quoted-printable message when decoded text or HTML exists, decodes `&amp;` in hrefs (but leaves `&region=`-style query strings alone), handles IPv6-literal URLs, ranks verify / confirm links and "Verify your email" anchor text ahead of login links, and never returns unsubscribe or asset links as `auth_links`
- `verification_codes` understands "code is 512930", "code: 123 456", "G-847291 is your code" and "847291 is your code", ignores zip / promo / sort codes and order numbers, and no longer lists CSS colours ahead of the real OTP; markup stripping is linear on hostile input

## [2.2.2] - 2026-08-16

### Added

- `follow_email_link` opens a verify / magic / reset URL already captured in the inbox
- `wait_for_email` and `extract_links_from_request` now return `verification_codes` (OTP)
- CI budget: the MCP tool catalog must stay under 5000 tokens

### Changed

- List and wait tools omit HTML and truncate bodies; use `export_webhook_data` for the full dump
- Default MCP install configs no longer mention an API key

## [2.2.1] - 2026-08-16

### Changed

- Tool descriptions now say when to use each tool, including the sign-up / verify / magic-link / password-reset email flow
- README install examples pin `uvx webhook-mcp-server==2.2.1` so clients do not keep 2.1.3

## [2.2.0] - 2026-08-16

### Changed

- Migrated the MCP entry point to Python SDK 2.0 `MCPServer` with typed `@mcp.tool()` handlers
- Reuse one HTTP client for the process lifetime and read `WEBHOOK_SITE_API_KEY` from the environment
- `wait_for_request` and `wait_for_email` now wait for **new** events by default (add `return_existing=true` for the old behavior)
- SSRF output is split into `callback_payloads` and `local_bypass_examples`
- Require `mcp>=2.0.0`

### Fixed

- Server failed to start on MCP SDK 2.0 (`Server.list_tools` removed)
- `ToolResult.to_json()` crashed when `data` was `None`
- Token UUID validation was skipped on several tools, including `get_webhook_dns`
- Tests called async `get_url` / `get_email` / `get_dns` without `await`

### Added

- Offline unit tests and a GitHub Actions test workflow
- Official `server.json` for the MCP Registry
- Cursor MCP config and authorized-use notes in the README

## [2.1.3] - 2026-01-27

### Changed

- **Smart waiting**: `wait_for_email` and `wait_for_request` now check for existing items first
  - Returns immediately if matching email/request already exists (with `"waited": false`)
  - Only polls if nothing exists yet
  - Eliminates unnecessary 60-120 second waits when emails arrive before the wait call
- Updated docstrings to document smart behavior

## [2.1.2] - 2026-01-26

### Removed

- Removed `clone_webhook` tool due to webhook.site API compatibility issues (24 → 23 tools)

### Changed

- Updated README and badges to reflect 23 tools

## [2.1.1] - 2026-01-26

### Fixed

- Fixed `clone_webhook` bug - was incorrectly calling `.raise_for_status()` on dict instead of Response object

## [2.1.0] - 2026-01-26

### Added

- **3 New Tools** (21 → 24 total):
  - `send_multiple_requests` - Send batch of requests for load testing
  - `clone_webhook` - Copy webhook with all settings to a new token
  - `export_webhook_data` - Export all requests to JSON format
- `post_raw()` method in HTTP client for absolute URLs

### Changed

- Updated README badge (21 → 24 tools)
- Added "Batch & Utility" tools section to README

## [2.0.7] - 2026-01-26

### Changed

- Complete README rewrite with professional MCP-focused structure
- Updated tool count badge (16 → 21)
- Added natural language examples and use cases
- Improved documentation with JSON response examples

## [2.0.6] - 2026-01-26

### Removed

- Removed 5 redundant script/test files (~800 lines)
- Removed unused `get_http_client()` function
- Removed unused `sanitize_identifier()` function
- Removed unused `WebhookInfo` class
- Removed unused `WebhookRequest` class
- Cleaned up unused imports across 5 files

### Added

- `LICENSE` file (MIT)
- `CHANGELOG.md` (this file)
- Improvement plan documentation

## [2.0.5] - 2026-01-26

### Fixed

- Console script wrapper for proper uvx execution
- Entry point configuration for MCP server

## [2.0.4] - 2026-01-26

### Fixed

- F-string syntax error in request service

## [2.0.3] - 2026-01-26

### Fixed

- uvx compatibility for MCP server startup
- Module path resolution issues

## [2.0.2] - 2026-01-26

### Fixed

- Syntax error in request_service.py
- Import organization issues

## [2.0.1] - 2026-01-26

### Fixed

- Package structure and imports
- Build configuration

## [2.0.0] - 2026-01-25

### Added

- Complete rewrite with 21 MCP tools
- Webhook management tools (create, configure, update, delete)
- Request management tools (list, search, delete)
- Bug bounty payload generators (SSRF, XSS, canary tokens)
- Email and DNS endpoint support
- Real-time request waiting with SSE
- Link extraction from captured requests
- Comprehensive validation and error handling
- Async HTTP client with proper connection management
- Structured logging with configurable levels

### Changed

- Migrated to MCP SDK 1.0.0
- Improved code architecture with service layer pattern
- Enhanced type hints throughout codebase

## [1.0.0] - 2026-01-24

### Added

- Initial release with basic webhook.site integration
- Core webhook creation and management
- Request capture and retrieval

[Unreleased]: https://github.com/zebbern/webhook-mcp-server/compare/v2.2.2...HEAD
[2.2.2]: https://github.com/zebbern/webhook-mcp-server/compare/v2.2.1...v2.2.2
[2.2.1]: https://github.com/zebbern/webhook-mcp-server/compare/v2.2.0...v2.2.1
[2.2.0]: https://github.com/zebbern/webhook-mcp-server/compare/v2.1.3...v2.2.0
[2.1.3]: https://github.com/zebbern/webhook-mcp-server/compare/v2.1.2...v2.1.3
[2.1.2]: https://github.com/zebbern/webhook-mcp-server/compare/v2.1.1...v2.1.2
[2.1.1]: https://github.com/zebbern/webhook-mcp-server/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/zebbern/webhook-mcp-server/compare/v2.0.7...v2.1.0
[2.0.7]: https://github.com/zebbern/webhook-mcp-server/compare/v2.0.6...v2.0.7
[2.0.6]: https://github.com/zebbern/webhook-mcp-server/compare/v2.0.5...v2.0.6
[2.0.5]: https://github.com/zebbern/webhook-mcp-server/compare/v2.0.4...v2.0.5
[2.0.4]: https://github.com/zebbern/webhook-mcp-server/compare/v2.0.3...v2.0.4
[2.0.3]: https://github.com/zebbern/webhook-mcp-server/compare/v2.0.2...v2.0.3
[2.0.2]: https://github.com/zebbern/webhook-mcp-server/compare/v2.0.1...v2.0.2
[2.0.1]: https://github.com/zebbern/webhook-mcp-server/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/zebbern/webhook-mcp-server/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/zebbern/webhook-mcp-server/releases/tag/v1.0.0
