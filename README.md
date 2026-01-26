# Webhook.site MCP Server

<!-- mcp-name: io.github.zebbern/webhook-mcp-server -->

[![Production Ready](https://img.shields.io/badge/status-production--ready-green.svg)](https://github.com/zebbern/webhook-mcp-server)
[![Version](https://img.shields.io/badge/version-2.0.0-blue.svg)](https://github.com/zebbern/webhook-mcp-server)
[![MCP Tools](https://img.shields.io/badge/mcp--tools-16-brightgreen.svg)](https://github.com/zebbern/webhook-mcp-server)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A **production-ready** Model Context Protocol (MCP) server for [webhook.site](https://webhook.site) - a free service for testing webhooks and HTTP requests. Built with robust error handling, comprehensive validation, and structured logging for reliable operation in production environments.

## Architecture

This project follows a **layered architecture** for maintainability, testability, and production reliability:

```
webhook-mcp-server/
├── server.py              # MCP entry point
├── handlers/              # Tool routing layer
│   ├── __init__.py
│   └── tool_handlers.py   # Routes MCP calls to services
├── services/              # Business logic layer
│   ├── __init__.py
│   ├── webhook_service.py # Webhook CRUD operations
│   ├── request_service.py # Request management
│   └── bugbounty_service.py # Bug bounty integrations
├── models/                # Data layer
│   ├── __init__.py
│   └── schemas.py         # Dataclasses, Tool definitions
├── utils/                 # Shared utilities
│   ├── __init__.py
│   ├── http_client.py     # Async HTTP client with retry logic
│   ├── logger.py          # Structured logging infrastructure
│   └── validation.py      # Input validation and sanitization
├── scripts/               # Helper scripts
│   ├── __init__.py
│   ├── check_webhook.py   # Check webhook for requests
│   └── get_temp_email.py  # Quick temp email creation
├── tests/                 # Comprehensive test suite
│   ├── test_webhook_service.py
│   ├── test_request_service.py
│   ├── test_wait_tools.py
│   ├── test_integration.py
│   └── test_bugbounty.py
├── pyproject.toml         # Project configuration
└── README.md              # This file
```

### Layer Responsibilities

- **Handlers**: MCP tool routing and initial request validation
- **Services**: Business logic, API interactions, and data processing
- **Models**: Data structures, schemas, and tool definitions
- **Utils**: Shared functionality (logging, validation, HTTP client)

## Features

### Production-Grade Capabilities

✅ **Robust Error Handling** - Graceful failure recovery with detailed error messages  
✅ **Input Validation** - UUID token validation, configuration value sanitization  
✅ **Structured Logging** - Comprehensive logging for debugging and monitoring  
✅ **Retry Logic** - Exponential backoff for transient API failures  
✅ **Type Safety** - Full type hints throughout the codebase  
✅ **Async Architecture** - Non-blocking I/O for optimal performance  
✅ **Comprehensive Testing** - Unit, integration, and real-world tests  
✅ **Security First** - Input validation, HTTPS enforcement, no hardcoded credentials

### 16 MCP Tools Available

| Tool                         | Description                                        |
| ---------------------------- | -------------------------------------------------- |
| `create_webhook`             | Create a new webhook endpoint                      |
| `create_webhook_with_config` | Create with custom response, status, CORS, timeout |
| `send_to_webhook`            | Send JSON data to a webhook                        |
| `get_webhook_requests`       | List all captured requests                         |
| `search_requests`            | Search with query filters                          |
| `get_latest_request`         | Get most recent request                            |
| `get_webhook_info`           | Get webhook settings and stats                     |
| `update_webhook`             | Modify webhook configuration                       |
| `delete_request`             | Delete a specific request                          |
| `delete_all_requests`        | Bulk delete with filters                           |
| `delete_webhook`             | Delete a webhook endpoint                          |
| `get_webhook_url`            | Get full URL for a token                           |
| `get_webhook_email`          | Get email address for a token                      |
| `get_webhook_dns`            | Get DNS subdomain for a token                      |
| `wait_for_request`           | Wait for new HTTP request (polling)                |
| `wait_for_email`             | Wait for email with magic link extraction          |

### Endpoints per Token

Each webhook token provides three unique endpoints:

- **URL**: `https://webhook.site/{token}` - for HTTP requests
- **Subdomain**: `https://{token}.webhook.site` - alternate URL format
- **Email**: `{token}@email.webhook.site` - for capturing emails
- **DNS**: `{token}.dnshook.site` - for DNS lookups

## Production Features

This server is built for production reliability and includes:

### Error Handling

- **Graceful Degradation**: All API failures return structured error messages
- **Retry Logic**: Automatic retry with exponential backoff for transient failures
- **Timeout Management**: Configurable timeouts prevent hanging operations
- **Detailed Logging**: Every error is logged with context for debugging

### Input Validation

- **UUID Token Validation**: Ensures all webhook tokens are valid UUIDs
- **Configuration Validation**: Validates status codes, content types, and CORS settings
- **Request Sanitization**: Safely handles malformed JSON and invalid data
- **Type Checking**: Runtime validation of all input parameters

### Logging Infrastructure

- **Structured Logging**: JSON-formatted logs for easy parsing
- **Log Levels**: DEBUG, INFO, WARNING, ERROR levels for different environments
- **Context Preservation**: Request IDs and tokens included in all log entries
- **Performance Tracking**: Operation timing and API response metrics

### API Reliability

- **Connection Pooling**: Efficient HTTP client with connection reuse
- **Exponential Backoff**: Smart retry logic for rate limits and transient errors
- **HTTPS Enforcement**: All connections use secure HTTPS
- **Error Recovery**: Automatic recovery from network failures

## Security

Security best practices implemented throughout:

### Input Security

- **UUID Validation**: All webhook tokens validated against UUID v4 format
- **Parameter Sanitization**: User inputs sanitized before API calls
- **Type Enforcement**: Strict type checking prevents injection attacks
- **Safe JSON Handling**: Malformed JSON handled gracefully without crashes

### Credential Management

- **No Hardcoded Secrets**: No API keys or credentials in source code
- **Environment Variables**: Sensitive data managed through environment
- **Token Isolation**: Each webhook token operates independently

### Network Security

- **HTTPS Only**: All webhook.site API calls use HTTPS
- **Timeout Limits**: Prevents resource exhaustion from slow responses
- **Rate Limit Awareness**: Respects API rate limits with backoff
- **Safe Error Messages**: Error messages don't leak sensitive information

## Installation

### Quick Install (Recommended)

Using `uvx` (no installation needed):

```bash
uvx webhook-mcp-server
```

Or install via pip:

```bash
pip install webhook-mcp-server
```

### For Development

Clone the repository and install dependencies:

```bash
git clone https://github.com/zebbern/webhook-mcp-server.git
cd webhook-mcp-server
pip install -e .
pip install pytest pytest-asyncio
```

### Requirements

- Python 3.10 or higher
- Dependencies:
  - `mcp>=1.1.0` - Model Context Protocol SDK
  - `httpx>=0.28.1` - Async HTTP client
  - `pytest>=8.3.4` - Testing framework (dev)
  - `pytest-asyncio>=0.25.2` - Async test support (dev)

## Configuration

### VS Code / Copilot

Add to your `.vscode/mcp.json`:

**Option 1: Using uvx (Recommended)**

```json
{
  "servers": {
    "webhook-site": {
      "type": "stdio",
      "command": "uvx",
      "args": ["webhook-mcp-server"]
    }
  }
}
```

**Option 2: Using pip installation**

```json
{
  "servers": {
    "webhook-site": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "webhook_mcp_server"]
    }
  }
}
```

**Option 3: Development mode (local)**

```json
{
  "servers": {
    "webhook-site": {
      "type": "stdio",
      "command": "python",
      "args": ["${workspaceFolder}/webhook-mcp-server/server.py"]
    }
  }
}
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "webhook-site": {
      "command": "python",
      "args": ["/path/to/webhook-mcp-server/server.py"]
    }
  }
}
```

## Development

### Running Tests

Run the comprehensive test suite:

```bash
cd webhook-mcp-server

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_webhook_service.py -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html

# Run integration tests only
pytest tests/test_integration.py -v
```

### Code Quality Standards

This project maintains high code quality standards:

- **PEP 8 Compliance**: All code follows PEP 8 style guidelines
- **Type Hints**: 100% type hint coverage for static analysis
- **Docstrings**: Google-style docstrings for all public functions
- **Async/Await**: Consistent async patterns throughout
- **Error Handling**: All exceptions properly caught and logged
- **Testing**: Comprehensive test coverage for all features

### Contributing Guidelines

1. **Fork and Clone**: Fork the repository and clone your fork
2. **Create Branch**: Create a feature branch (`git checkout -b feature/amazing-feature`)
3. **Write Tests**: Add tests for new functionality
4. **Follow Style**: Maintain PEP 8 and existing code patterns
5. **Type Hints**: Add type hints to all new functions
6. **Document**: Update docstrings and README as needed
7. **Test**: Ensure all tests pass (`pytest tests/ -v`)
8. **Commit**: Write clear, descriptive commit messages
9. **Push**: Push to your fork and submit a pull request

### Project Structure Guidelines

- **Handlers**: Only routing logic, no business logic
- **Services**: All business logic and API interactions
- **Models**: Data structures and schemas only
- **Utils**: Shared utilities used across layers
- **Tests**: Mirror source structure in tests directory

### Debugging

Enable debug logging:

```python
# Set environment variable
export LOG_LEVEL=DEBUG

# Or modify logger.py temporarily
logging.basicConfig(level=logging.DEBUG)
```

## Usage Examples

### Create a Webhook

```
Use create_webhook tool to get a new endpoint URL.
```

### Create with Custom Response

```
Use create_webhook_with_config with:
- default_status: 201
- default_content: {"status": "created"}
- cors: true
```

### Search Requests

```
Use search_requests with:
- webhook_token: "your-token"
- query: "method:POST"
- sorting: "newest"
```

## Roadmap

- [ ] PyPI publication
- [ ] MCP Registry listing
- [ ] Enhanced webhook statistics
- [ ] Webhook template library
- [ ] WebSocket support for real-time updates
- [ ] Advanced filtering and search capabilities

## Version History

**v2.0.0** (Current - Production Ready)

- ✅ Production-grade error handling
- ✅ Comprehensive input validation
- ✅ Structured logging infrastructure
- ✅ Retry logic with exponential backoff
- ✅ Enhanced security measures
- ✅ Full type hint coverage
- ✅ Comprehensive test suite

**v1.x** (Legacy)

- Basic webhook operations
- Initial MCP tool implementation

## Support

- **Issues**: [GitHub Issues](https://github.com/zebbern/webhook-mcp-server/issues)
- **Discussions**: [GitHub Discussions](https://github.com/zebbern/webhook-mcp-server/discussions)
- **Documentation**: This README and inline code documentation

## License

MIT License - see [LICENSE](LICENSE) file for details

## Acknowledgments

- [webhook.site](https://webhook.site) - Excellent webhook testing service
- [Anthropic](https://anthropic.com) - Model Context Protocol specification
- Python asyncio and httpx communities

---

**Ready for production use** • **Actively maintained** • **Contributions welcome**
