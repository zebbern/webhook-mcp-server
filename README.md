# Webhook.site MCP Server

[![PyPI](https://img.shields.io/pypi/v/webhook-mcp-server.svg)](https://pypi.org/project/webhook-mcp-server/)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-29%20tools-brightgreen.svg)](https://modelcontextprotocol.io/)

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
- [Architecture](#architecture)
- [Development](#development)
- [Contributing](#contributing)
- [Requirements](#requirements)
- [Changelog](#changelog)
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

Use `3.0.0` or newer. `2.1.3` does not start on MCP 2.0; 3.0 renames a few tools (see Upgrading from 2.x).

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
| `WEBHOOK_SITE_API_KEY` | Your webhook.site API key. Makes new URLs permanent (your plan's quota) and unlocks `list_webhooks`, Custom Actions, Schedules, Global Variables, Groups, Templates, Databases, Users and CSV export |
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

### Creative/Practical:

```
"Create a webhook that pretends to be a Stripe payment API"
"Make a fake login endpoint that captures credentials (for pentesting)"
"Set up an email inbox that auto-extracts verification codes"
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

29 tools. Everything works without an account for anonymous 7-day URLs; with `WEBHOOK_SITE_API_KEY` set, URLs are permanent and the account tools below unlock the features of your plan.

### Diagnostics

| Tool            | Description                                                                                          |
| --------------- | ---------------------------------------------------------------------------------------------------- |
| `server_status` | API key present, account reachable and authenticated, plan hint, real-time socket, env config, problems |

### Webhooks

| Tool                | Description                                                                                       |
| ------------------- | ------------------------------------------------------------------------------------------------- |
| `create_webhook`    | Start here: disposable URL, temp email, and DNS for sign-up or callbacks                          |
| `configure_webhook` | Create with, or update to, custom status / body / content type / timeout / CORS, alias, expiry, `request_limit`, `listen`, actions on/off, `clone_from`, `group_id`; DNSHook answers via a JSON `default_content` |
| `get_webhook_info`  | Settings, expiry, request count and every address (`url`, `subdomain_url`, `api_url`, `email`, `dns`) |
| `get_webhook_email` | Temp inbox `{token}@email.webhook.site` for sign-up / verify / magic-link / reset                  |
| `list_webhooks`     | List the account's URLs with aliases, request counts and `latest_request_at` (API key)             |
| `delete_webhook`    | Delete a webhook and all its data                                                                 |

### Requests

| Tool                    | Description                                                                                  |
| ----------------------- | -------------------------------------------------------------------------------------------- |
| `send_requests`         | Send one body (`data`) or many (`payloads`) to the URL, any HTTP method, optional delay        |
| `get_webhook_requests`  | List captured events page by page (`page`, `pagination` in the result)                         |
| `search_requests`       | webhook.site search syntax (`method:POST`, `content:verify`, `type:email AND ...`), dates, pages |
| `get_request`           | Newest event or a specific `request_id`; `raw=true` adds the untouched body                    |
| `update_request`        | Attach a note, or call Set Response for a request the webhook.site CLI is holding (`listen` > 0) |
| `download_request_file` | Download an uploaded file or email attachment (base64)                                         |
| `delete_request`        | Delete a specific request                                                                     |
| `delete_all_requests`   | Bulk delete, optionally by date expression or search query                                    |
| `export_webhook_data`   | Full dump with HTML and untruncated bodies: paged JSON, or the account's CSV export            |

### Real-Time Waiting

| Tool                | Description                                                                                         |
| ------------------- | --------------------------------------------------------------------------------------------------- |
| `wait_for_request`  | Wait for a **new** HTTP / DNS event (1-120s) over webhook.site's socket, polling as backstop. `return_existing` reuses old traffic |
| `wait_for_email`    | After sign-up: wait for verify / magic-link / reset mail; returns links, OTP codes, sender, spam / DKIM checks, attachments |
| `follow_email_link` | Open a captured verify / magic / reset URL and return the page preview (public hosts only unless allowlisted) |

### Account Features (API key)

| Tool                      | Description                                                                                        |
| ------------------------- | -------------------------------------------------------------------------------------------------- |
| `manage_custom_actions`   | list / create / update / delete / test / execute the Custom Actions a token runs on each request or email; `types` and `variables` return the built-in reference (63 action types, each verified against the live API, plus every `$request.*$` variable) and required parameters are checked before the call |
| `manage_schedules`        | list / get / create / update / delete / run / logs for Schedules that call a URL on an interval or cron |
| `manage_global_variables` | list / create / update / delete Global Variables usable as `$name$` in actions and schedules          |
| `manage_groups`           | list / create / update / delete Groups that organise URLs                                            |
| `manage_templates`        | list / create / update / delete reusable Custom Action Templates                                     |
| `manage_databases`        | list / create / update / delete Databases and run SQL queries                                        |
| `manage_users`            | list / invite / update / delete team users (Enterprise)                                              |

### Bug Bounty / Security

| Tool                         | Description                                                                 |
| ---------------------------- | --------------------------------------------------------------------------- |
| `generate_oob_payloads`      | SSRF URLs, XSS callbacks, or canary URL / DNS / email tokens (`kind=`)       |
| `check_for_callbacks`        | Quick check for OOB callbacks                                               |
| `extract_links_from_request` | Pull confirm / reset / magic-link URLs and OTP from a captured email or body |

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

1. `create_webhook` — get `email` (`{token}@email.webhook.site`)
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
  "email": "abc123-def456-...@email.webhook.site",
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

### SSRF Testing Payload

```json
// Response from generate_ssrf_payload
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

| Endpoint      | Format                         | Use Case                    |
| ------------- | ------------------------------ | --------------------------- |
| **HTTP URL**  | `https://webhook.site/{token}` | Capture HTTP/HTTPS requests |
| **Subdomain** | `https://{token}.webhook.site` | Alternative URL format      |
| **Email**     | `{token}@email.webhook.site`   | Capture incoming emails     |
| **DNS**       | `{token}.dnshook.site`         | Capture DNS lookups         |

---

## Architecture

```
webhook-mcp-server/
├── server.py              # MCPServer entry point + lifespan
├── handlers/              # Typed @mcp.tool() registrations
├── services/              # Business logic
│   ├── webhook_service.py # Webhook CRUD
│   ├── request_service.py # Request management
│   └── bugbounty_service.py # Security payloads
├── models/                # Config / filter / result types
└── utils/                 # HTTP client, logging, validation
```

### Key Features

- **Async Architecture** - Non-blocking I/O for optimal performance
- **Retry Logic** - Exponential backoff for transient failures
- **Input Validation** - UUID validation, parameter sanitization
- **Structured Logging** - JSON logs for debugging and monitoring
- **Type Safety** - Full type hints throughout

---

## Development

### Setup

```bash
git clone https://github.com/zebbern/webhook-mcp-server.git
cd webhook-mcp-server
pip install -e ".[dev]"
```

### Run Tests

```bash
# Offline unit tests (default for CI)
pytest -m "not live" -v

# Live webhook.site tests
pytest -m live -v
```

### Run Locally

```bash
python server.py
```

---

## Requirements

- Python 3.10+
- `mcp >= 2.0.0`
- `httpx >= 0.26.0`, `httpcore >= 1.0.0`, `anyio >= 4.0.0`
- `python-socketio[asyncio_client] >= 5.11.0` (real-time waiting; the tools fall back to polling without it)

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.

---

## Contributing

Contributions are welcome! Here's how you can help:

1. **Report bugs** - Open an issue describing the problem
2. **Suggest features** - Open an issue with your idea
3. **Submit PRs** - Fork the repo and submit a pull request

### Development Setup

```bash
git clone https://github.com/zebbern/webhook-mcp-server.git
cd webhook-mcp-server
pip install -e ".[dev]"
pytest -m "not live" -v
```

### Guidelines

- Follow existing code style
- Add tests for new features
- Update documentation as needed
- Keep PRs focused on a single change

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
