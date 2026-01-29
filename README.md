# Webhook.site MCP Server

[![PyPI](https://img.shields.io/pypi/v/webhook-mcp-server.svg)](https://pypi.org/project/webhook-mcp-server/)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-23%20tools-brightgreen.svg)](https://modelcontextprotocol.io/)

A Model Context Protocol (MCP) server for [webhook.site](https://webhook.site) - instantly capture HTTP requests, emails, and DNS lookups. Perfect for testing webhooks, debugging API callbacks, security testing, and bug bounty hunting.

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
pytest tests/ -v
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
