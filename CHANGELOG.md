# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Improvement plan for future enhancements

### Changed

- Code cleanup and dead code removal

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

[Unreleased]: https://github.com/zebbern/webhook-mcp-server/compare/v2.0.6...HEAD
[2.0.6]: https://github.com/zebbern/webhook-mcp-server/compare/v2.0.5...v2.0.6
[2.0.5]: https://github.com/zebbern/webhook-mcp-server/compare/v2.0.4...v2.0.5
[2.0.4]: https://github.com/zebbern/webhook-mcp-server/compare/v2.0.3...v2.0.4
[2.0.3]: https://github.com/zebbern/webhook-mcp-server/compare/v2.0.2...v2.0.3
[2.0.2]: https://github.com/zebbern/webhook-mcp-server/compare/v2.0.1...v2.0.2
[2.0.1]: https://github.com/zebbern/webhook-mcp-server/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/zebbern/webhook-mcp-server/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/zebbern/webhook-mcp-server/releases/tag/v1.0.0
