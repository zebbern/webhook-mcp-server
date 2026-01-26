# Webhook.site MCP Server

[![PyPI](https://img.shields.io/pypi/v/webhook-mcp-server.svg)](https://pypi.org/project/webhook-mcp-server/)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-23%20tools-brightgreen.svg)](https://modelcontextprotocol.io/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A Model Context Protocol (MCP) server for [webhook.site](https://webhook.site) - instantly capture HTTP requests, emails, and DNS lookups. Perfect for testing webhooks, debugging API callbacks, security testing, and bug bounty hunting.

## Quick Start

### Installation

```bash
# Using uvx (recommended - no install needed)
uvx webhook-mcp-server

# Or install via pip
pip install webhook-mcp-server
```

### VS Code / GitHub Copilot

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "webhook-mcp-server": {
      "type": "stdio",
      "command": "uvx",
      "args": ["webhook-mcp-server"]
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
      "args": ["webhook-mcp-server"]
    }
  }
}
```

---

## What Can You Do?

### Capture Webhooks

```
"Create a webhook and show me the URL"
"What requests have been sent to my webhook?"
"Wait for a request to come in"
```

### Receive Emails

```
"Give me a temporary email address"
"Wait for a password reset email and extract the link"
"Check if any emails arrived"
```

### Bug Bounty Testing

```
"Generate SSRF payloads for testing"
"Create an XSS callback to detect blind XSS"
"Check if any out-of-band callbacks came in"
```

### Canary Tokens

```
"Create a canary URL to track document access"
"Generate a DNS canary for the config file"
"Set up an email tracker pixel"
```

---

## Tools Reference

### Webhook Management

| Tool                         | Description                                        |
| ---------------------------- | -------------------------------------------------- |
| `create_webhook`             | Create a new webhook endpoint                      |
| `create_webhook_with_config` | Create with custom response, status, CORS, timeout |
| `get_webhook_url`            | Get the full URL for a webhook token               |
| `get_webhook_email`          | Get the email address for a webhook                |
| `get_webhook_dns`            | Get the DNS subdomain for a webhook                |
| `get_webhook_info`           | Get webhook settings and statistics                |
| `update_webhook`             | Modify webhook configuration                       |
| `delete_webhook`             | Delete a webhook endpoint                          |

### Request Handling

| Tool                   | Description                                 |
| ---------------------- | ------------------------------------------- |
| `send_to_webhook`      | Send JSON data to a webhook                 |
| `get_webhook_requests` | List all captured requests                  |
| `search_requests`      | Search with filters (method, content, date) |
| `delete_request`       | Delete a specific request                   |
| `delete_all_requests`  | Bulk delete with filters                    |

### Real-Time Waiting

| Tool               | Description                                   |
| ------------------ | --------------------------------------------- |
| `wait_for_request` | Wait for an HTTP request (polling)            |
| `wait_for_email`   | Wait for email with automatic link extraction |

### Bug Bounty / Security

| Tool                         | Description                                          |
| ---------------------------- | ---------------------------------------------------- |
| `generate_ssrf_payload`      | Create SSRF test payloads (HTTP, DNS, IP-based)      |
| `generate_xss_callback`      | Create XSS callback payloads with cookie/DOM capture |
| `generate_canary_token`      | Create trackable URLs, DNS, or email canaries        |
| `check_for_callbacks`        | Quick check for OOB callbacks                        |
| `extract_links_from_request` | Extract URLs from captured requests                  |

### Batch & Utility

| Tool                     | Description                             |
| ------------------------ | --------------------------------------- |
| `send_multiple_requests` | Send batch of requests for load testing |
| `export_webhook_data`    | Export all requests to JSON             |

---

## Examples

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
  "links_found": ["https://example.com/reset?token=xyz789"]
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
├── server.py              # MCP entry point
├── handlers/              # Tool routing layer
├── services/              # Business logic
│   ├── webhook_service.py # Webhook CRUD
│   ├── request_service.py # Request management
│   └── bugbounty_service.py # Security payloads
├── models/                # Tool definitions & schemas
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
pytest tests/ -v
```

### Run Locally

```bash
python server.py
```

---

## Requirements

- Python 3.10+
- `mcp >= 1.0.0`
- `httpx >= 0.25.0`

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.

---

## Links

- 📦 [PyPI Package](https://pypi.org/project/webhook-mcp-server/)
- 🐙 [GitHub Repository](https://github.com/zebbern/webhook-mcp-server)
- 🌐 [webhook.site](https://webhook.site) - The service this MCP wraps
- 📖 [Model Context Protocol](https://modelcontextprotocol.io/) - MCP specification

---

**Made with ❤️ for the MCP community**
