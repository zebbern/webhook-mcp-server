# Webhook.site MCP Server

[![PyPI](https://img.shields.io/pypi/v/webhook-mcp-server.svg)](https://pypi.org/project/webhook-mcp-server/)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-31%20tools-brightgreen.svg)](https://modelcontextprotocol.io/)

A Model Context Protocol (MCP) server for [webhook.site](https://webhook.site) - instantly capture HTTP requests, emails, and DNS lookups. Perfect for testing webhooks, debugging API callbacks, security testing, and bug bounty hunting.

<!-- mcp-name: io.github.zebbern/webhook-mcp-server -->

Security helper tools (SSRF, XSS, canary tokens) are for **authorized testing only** — systems you own or have explicit permission to test.

---

## Table of Contents

- [Quick Start](#quick-start)
- [What Can You Do?](#what-can-you-do)
- [Tools Reference](#tools-reference)
- [Examples](#examples)
- [Each Webhook Token Provides](#each-webhook-token-provides)
- [Documentation](#documentation)
- [Development](#development)
- [Requirements](#requirements)
- [Contributing](#contributing)
- [Credits](#credits)
- [Links](#links)

---

## Quick Start

### Installation

```bash
# Using uvx (recommended - no install needed)
uvx webhook-mcp-server==3.0.0

# Or install via pip
pip install webhook-mcp-server==3.0.0
```

Use `3.0.0` or newer. `2.1.3` does not start on MCP 2.0; 3.0 renames a few tools (see [Upgrading from 2.x](#upgrading-from-2x)).

### VS Code / GitHub Copilot

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "webhook-mcp-server": {
      "type": "stdio",
      "command": "uvx",
      "args": ["webhook-mcp-server==3.0.0"]
    }
  }
}
```

### Cursor

Add to `.cursor/mcp.json` (project) or your user MCP config:

```json
{
  "mcpServers": {
    "webhook-mcp-server": {
      "command": "uvx",
      "args": ["webhook-mcp-server==3.0.0"]
    }
  }
}
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "webhook-mcp-server": {
      "command": "uvx",
      "args": ["webhook-mcp-server==3.0.0"]
    }
  }
}
```

### Configuration

All settings are environment variables on the server process. Put them in the `env` block of your MCP client config.

| Variable | Purpose |
| -------- | ------- |
| `WEBHOOK_SITE_API_KEY` | Your webhook.site API key. Makes new URLs permanent (your plan's quota) and unlocks `list_webhooks`, Custom Actions, Schedules, Global Variables, Groups, Queue Profiles, Templates, Databases, Users and CSV export |
| `WEBHOOK_SITE_DEFAULT_EXPIRY` | Seconds until new URLs expire when the call does not pass `expiry`. Unset means permanent on a paid account (7 days for anonymous URLs) |
| `WEBHOOK_MCP_RATE_LIMIT_MAX_WAIT` | When webhook.site answers 429 with a `Retry-After` up to this many seconds (default 15), the call waits and retries once; longer waits are reported as an error naming the wait |
| `FOLLOW_EMAIL_LINK_ALLOW_HOSTS` | `follow_email_link` only opens links to public internet hosts, and connects to the address it checked (no DNS rebinding). To test a sign-up flow on your own machine or intranet, list what to allow: `localhost,127.0.0.1,*.corp.example,10.0.0.0/8` |
| `HTTPS_PROXY` / `HTTP_PROXY` / `NO_PROXY` | Honoured by `follow_email_link`. The proxy makes the connection, so the target is checked before the request instead of being pinned |
| `SSL_CERT_FILE` / `SSL_CERT_DIR` | Custom CA bundle for `follow_email_link`, for corporate TLS interception |

If a verification link succeeds and then redirects somewhere that is not allowed (a local dev server, an intranet dashboard), the tool reports success with the redirect in `blocked_redirect` instead of failing: the request that consumed the token already went through.

---

## What Can You Do?

### Capture Webhooks

```
"Create a webhook and show me the URL"
"What requests have been sent to my webhook?"
"Wait for a request to come in"
```

<img width="555" height="555" alt="Webhooks" src="https://github.com/user-attachments/assets/75558234-9d93-4b79-817e-373a5ce75382" />

### Security/Bug Bounty:

```
"Generate an SSRF payload to test for blind vulnerabilities"
"Create XSS callback payloads to detect blind XSS attacks"
"Make me a canary token to detect if someone accesses a URL"
```

<img width="555" height="555" alt="Security" src="https://github.com/user-attachments/assets/12150308-932a-4872-acd9-5473c7dde6ff" />

### Email Automation:

```
"Create a temp email and wait for a password reset link"
"Monitor this webhook for emails and extract all links from them"
"Give me 3 temporary emails at once" (batch creation)
```

<img width="555" height="555" alt="Email" src="https://github.com/user-attachments/assets/04af7d6e-e8aa-4e35-a817-2204cde8f5e7" />

### API Testing:

```
"Create a webhook that returns a 404 error with a custom message"
"Make a webhook with CORS enabled that waits 5 seconds before responding"
"Send 10 different test requests to a webhook and show me all the captured data"
"Hold the next request and answer it with a 402 and this JSON body"
```

<img width="555" height="555" alt="API" src="https://github.com/user-attachments/assets/d8f2c46b-fb40-4e57-8957-0edef8e94db6" />

### Real-time Monitoring:

```
"Create a webhook and wait for any HTTP request to arrive"
"Monitor for DNS lookups to detect if a server is making DNS queries"
"Search all requests for ones containing 'password' in the body"
```

<img width="555" height="555" alt="Monitoring" src="https://github.com/user-attachments/assets/12c9d270-f9df-489a-8be1-9afb4726404b" />

### Data Analysis:

```
"Export all captured webhook requests to JSON format"
"Show me statistics on requests received in the last hour"
"Filter and show only POST requests with specific headers"
```

<img width="555" height="555" alt="Data" src="https://github.com/user-attachments/assets/51cd0032-d92b-46e7-9f0c-6cee96b6e4f3" />

### Automate with your account:

```
"Add a Custom Action that forwards every request to my staging API"
"Schedule a health check of https://example.com every 5 minutes and alert on a bad status"
"Write a WebhookScript that answers with the request's JSON field 'id'"
```

<img width="555" height="555" alt="Practical" src="https://github.com/user-attachments/assets/a15bcbc4-087a-40bb-a1e5-a42475bd1301" />

### Canary Tokens

```
"Create a canary URL to track document access"
"Generate a DNS canary for the config file"
"Set up an email tracker pixel"
```

<img width="555" height="555" alt="CanaryTokens" src="https://github.com/user-attachments/assets/2e6af1f5-55d6-4670-b899-6809f3031439" />

---

## Tools Reference

Everything works without an account on anonymous 7-day URLs. With `WEBHOOK_SITE_API_KEY` set, URLs are permanent and the account tools unlock the features of your plan. Every `webhook_token` accepts the UUID, an alias, a pasted `https://webhook.site/...` URL or the inbox address. Full parameters for each tool: [docs/TOOLS.md](docs/TOOLS.md).

<!-- tools:start -->

31 tools, generated from the server by `scripts/gen_tool_docs.py`.

#### Diagnostics

| Tool | What it does |
| --- | --- |
| `server_status` | Check this server's setup: API key, account reachability, plan, real-time socket, env config. |

#### Webhooks

| Tool | What it does |
| --- | --- |
| `create_webhook` | Create a disposable inbox to sign up on a website: HTTP URL, temp email, DNS. |
| `configure_webhook` | Create a webhook with custom settings, or update one (pass webhook_token). |
| `get_webhook_info` | Show a webhook's settings, expiry, request count and every address. |
| `get_webhook_email` | Return the temp inbox to sign up, verify, magic-link, or reset a password. |
| `list_webhooks` | List the webhooks (URLs / inboxes) in the account. Needs WEBHOOK_SITE_API_KEY. |
| `delete_webhook` | Permanently delete a webhook and every captured request/email. |

#### Requests

| Tool | What it does |
| --- | --- |
| `send_requests` | Send one JSON body (data) or several (payloads) to the webhook URL to test capture. |
| `get_webhook_requests` | List captured HTTP, email, or DNS events for a webhook, one page at a time. |
| `search_requests` | Search captured events by method, body text, headers, type, or date. |
| `get_request` | Return one captured event: the newest by default, or request_id. |
| `update_request` | Attach a note to a captured request, or set its dynamic response. |
| `download_request_file` | Download an uploaded file or email attachment (base64) by its file_id. |
| `delete_request` | Delete one captured HTTP, email, or DNS event by request id. |
| `delete_all_requests` | Clear captured events on a webhook, optionally by date or search query. |
| `export_webhook_data` | Full dump of captured events with HTML and untruncated bodies, as JSON or CSV. |

#### Real-time

| Tool | What it does |
| --- | --- |
| `wait_for_request` | Wait until a new HTTP (or DNS) callback hits the webhook (1-120s). |
| `wait_for_email` | Wait for a sign-up, verify, magic-link, or password-reset email (1-120s). |
| `respond_to_next_request` | Hold the next request that hits the webhook and answer it with your own status, headers and body. |
| `follow_email_link` | Open the verify / magic-link / reset URL from a captured sign-up email. |

#### Account features (API key)

| Tool | What it does |
| --- | --- |
| `manage_custom_actions` | Manage the Custom Actions webhook.site runs on every request or email a token receives. |
| `manage_schedules` | Manage Schedules: webhook.site calls request_url on an interval (needs API key). |
| `manage_global_variables` | Manage Global Variables shared by all URLs, usable as $name$ in Custom Actions and Schedules. |
| `manage_groups` | Manage Groups that organise the account's webhooks (needs API key). |
| `manage_queues` | Manage Queue Profiles that throttle queued Custom Actions (needs API key). |
| `manage_templates` | Manage Templates: reusable sets of Custom Actions plus predefined variables (needs API key). |
| `manage_databases` | Manage webhook.site Databases and run SQL against them (needs API key). |
| `manage_users` | Manage team users on an Enterprise account (needs an administrator API key). |

#### Security testing

| Tool | What it does |
| --- | --- |
| `generate_oob_payloads` | Build authorized out-of-band payloads that ping this webhook: SSRF URLs, XSS callbacks, or canary tokens. |
| `check_for_callbacks` | See if SSRF, XSS, or canary callbacks arrived in the last N minutes. |
| `extract_links_from_request` | Pull confirm, reset, magic-link, and other URLs from a captured email or HTTP body. |

<!-- tools:end -->

### Upgrading from 2.x

| 2.x tool | 3.0 replacement |
| -------- | --------------- |
| `create_webhook_with_config`, `update_webhook` | `configure_webhook` (pass `webhook_token` to update) |
| `get_webhook_url`, `get_webhook_dns` | fields of `get_webhook_info` |
| `get_latest_request` | `get_request` |
| `send_to_webhook`, `send_multiple_requests` | `send_requests` (`data` or `payloads`) |
| `generate_ssrf_payload`, `generate_xss_callback`, `generate_canary_token` | `generate_oob_payloads` (`kind=ssrf\|xss\|canary`, `canary_type`) |

---

## Examples

### Sign up on a website

1. `create_webhook` — get `email` (`{token}@emailhook.site`)
2. Use that address on the site (sign-up, verify, magic link, or password reset)
3. `wait_for_email` — receive the message, confirm / login / reset URLs, and any OTP
4. `follow_email_link` to open a verify link, or type `verification_codes` on the site

If you already have a token, `get_webhook_email` returns the same inbox.

### Create a Webhook

```json
// Response from create_webhook
{
  "token": "abc123-def456-...",
  "url": "https://webhook.site/abc123-def456-...",
  "email": "abc123-def456-...@emailhook.site",
  "dns": "abc123-def456-....dnshook.site"
}
```

### Wait for Password Reset Email

```json
// Response from wait_for_email
{
  "email_received": true,
  "subject": "Password Reset Request",
  "from": "noreply@example.com",
  "auth_links": ["https://example.com/reset?token=xyz789"],
  "verification_codes": ["847291"]
}
```

### Poll for new events without paging

```json
// get_webhook_requests(webhook_token, since=<next_since from the previous call>)
{
  "requests": [ ... only what arrived after the cursor ... ],
  "next_since": 1788472548944304
}
```

### SSRF Testing Payload

```json
// Response from generate_oob_payloads(kind="ssrf")
{
  "payloads": {
    "http": "https://webhook.site/token?id=ssrf-test",
    "dns": "ssrf-test.token.dnshook.site",
    "ip_decimal": "http://2130706433/token",
    "ip_hex": "http://0x7f000001/token"
  }
}
```

---

## Each Webhook Token Provides

| Endpoint          | Format                                  | Use Case                                        |
| ----------------- | --------------------------------------- | ----------------------------------------------- |
| **HTTP URL**      | `https://webhook.site/{token}`          | Capture HTTP/HTTPS requests (any sub-path too)  |
| **Subdomain**     | `https://{token}.webhook.site`          | Alternative URL format                          |
| **Forced status** | `https://webhook.site/{token}/{status}` | Answer with that status, for retry-logic tests  |
| **Email**         | `{token}@emailhook.site`                | Capture incoming emails                         |
| **DNS**           | `{token}.dnshook.site`                  | Capture DNS lookups (every subdomain)           |

---

## Documentation

| Page | Contents |
| ---- | -------- |
| [docs/TOOLS.md](docs/TOOLS.md) | Every tool with parameters and hints, generated from the server |
| [docs/webhook-site-notes.md](docs/webhook-site-notes.md) | What webhook.site actually does, verified live, including where the official docs are wrong |
| [docs/testing.md](docs/testing.md) | The four test layers, recordings, verification scripts, model evals, account safety |
| [docs/releasing.md](docs/releasing.md) | Version bumps, tagging, the publish workflow |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

---

## Development

```bash
git clone https://github.com/zebbern/webhook-mcp-server.git
cd webhook-mcp-server
pip install -e ".[dev]"
pytest -m "not live and not live_auth"     # offline suite incl. replay of recorded live exchanges
python server.py                            # run the server on stdio
```

The offline suite replays real recorded webhook.site exchanges; the live tool check and the `live` / `live_auth` tiers hit the real API. Details in [docs/testing.md](docs/testing.md).

Layout: `server.py` (entry point and lifespan), `handlers/tools.py` (tool registrations), `services/` (one module per API area), `utils/` (HTTP client, real-time socket, URL safety, references), `scripts/` (live check, generators, verifiers), `evals/` (model-in-the-loop prompts).

---

## Requirements

- Python 3.10+
- `mcp >= 2.0.0`
- `httpx >= 0.26.0`, `httpcore >= 1.0.0`, `anyio >= 4.0.0`
- `python-socketio[asyncio_client] >= 5.11.0` (real-time waiting; the tools fall back to polling without it)

---

## Contributing

Bug reports and PRs are welcome. Keep a PR to one change, add a test whose expectation was checked against the real API (see [docs/testing.md](docs/testing.md)), and run `python scripts/gen_tool_docs.py` after touching a tool.

---

## Credits

- [Simon Fredsted (Founder of webhook.site)](https://github.com/fredsted)
- [Official webhook.site open source repo](https://github.com/webhooksite/webhook.site)

This project is not affiliated with or endorsed by webhook.site

## Links

- 📦 [PyPI Package](https://pypi.org/project/webhook-mcp-server/)
- 🐙 [GitHub Repository](https://github.com/zebbern/webhook-mcp-server)
- 🌐 [webhook.site](https://webhook.site) - The service this MCP wraps
- 📖 [Model Context Protocol](https://modelcontextprotocol.io/) - MCP specification

---

**Made with ❤️ for the MCP community**
