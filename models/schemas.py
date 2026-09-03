"""
Data models for the webhook.site MCP server.

This module contains dataclasses for structured data
(WebhookConfig, SearchFilters, etc.) and a consistent tool result type.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class WebhookConfig:
    """Configuration for creating/updating a webhook.

    Args:
        default_status: HTTP status code for responses (200-599)
        default_content: Response body content
        default_content_type: Content-Type header value
        timeout: Seconds to wait before responding (0-30)
        listen: Seconds to wait for a Set Response call (0-10)
        cors: Enable CORS headers
        alias: Custom URL alias (3-32 alphanumeric chars)
        expiry: Seconds until auto-expiration (max 604800)
        request_limit: Request history size (0 stores nothing, max 10000)
        actions: Whether Custom Actions run on each request
        clone_from: Token UUID or alias to copy settings and actions from
        group_id: Group to add the token to
    """

    default_status: int | None = None
    default_content: str | None = None
    default_content_type: str | None = None
    timeout: int | None = None
    listen: int | None = None
    cors: bool | None = None
    alias: str | None = None
    expiry: int | None = None
    request_limit: int | None = None
    actions: bool | None = None
    clone_from: str | None = None
    group_id: int | None = None

    def to_payload(self) -> dict[str, Any]:
        """Convert to API payload, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class SearchFilters:
    """Filters for searching webhook requests.

    Args:
        request_type: Filter by type ('web', 'email', 'dns')
        query: Additional search query string (e.g., 'method:POST', 'content:hello')
        date_from: Start date filter (format: yyyy-MM-dd HH:mm:ss)
        date_to: End date filter (format: yyyy-MM-dd HH:mm:ss)
        sorting: Sort order ('newest' or 'oldest')
        limit: Maximum results to return per page (max 100)
        page: Page number (1-based)
    """

    request_type: str | None = None
    query: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    sorting: str = "newest"
    limit: int = 20
    page: int = 1

    def to_params(self) -> dict[str, Any]:
        """Convert to query parameters."""
        params: dict[str, Any] = {"per_page": self.limit, "sorting": self.sorting, "page": self.page}

        query_parts = []
        if self.request_type:
            query_parts.append(f"type:{self.request_type}")
        if self.query:
            query_parts.append(self.query)
        if query_parts:
            params["query"] = " ".join(query_parts)

        if self.date_from:
            params["date_from"] = self.date_from
        if self.date_to:
            params["date_to"] = self.date_to
        return params


@dataclass
class DeleteFilters:
    """Filters for bulk deleting requests.

    Args:
        date_from: Delete from date (format: yyyy-MM-dd HH:mm:ss or 'now-7d')
        date_to: Delete until date (format: yyyy-MM-dd HH:mm:ss or 'now-7d')
        query: Delete only matching requests
    """

    date_from: str | None = None
    date_to: str | None = None
    query: str | None = None

    def to_params(self) -> dict[str, str]:
        """Convert to query parameters."""
        params = {}
        if self.date_from:
            params["date_from"] = self.date_from
        if self.date_to:
            params["date_to"] = self.date_to
        if self.query:
            params["query"] = self.query
        return params


@dataclass
class ToolResult:
    """Standardized result from a tool operation.

    Args:
        success: Whether the operation succeeded
        message: Human-readable result message
        data: Additional result data
    """

    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.data is None:
            self.data = {}

    def to_dict(self) -> dict[str, Any]:
        """Flatten to a JSON-compatible payload."""
        result = {"success": self.success, "message": self.message}
        result.update(self.data)
        return result

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
