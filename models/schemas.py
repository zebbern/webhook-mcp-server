"""
Data models and MCP tool schemas for the webhook.site MCP server.

This module contains:
- Dataclasses for structured data (WebhookConfig, WebhookInfo, etc.)
- MCP Tool definitions with input schemas
- Response models for consistent API responses
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any
from mcp.types import Tool


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class WebhookConfig:
    """Configuration for creating/updating a webhook.
    
    Args:
        default_status: HTTP status code for responses (200-599)
        default_content: Response body content
        default_content_type: Content-Type header value
        timeout: Seconds to wait before responding (0-30)
        cors: Enable CORS headers
        alias: Custom URL alias (3-32 alphanumeric chars)
        expiry: Seconds until auto-expiration (max 604800)
    """
    default_status: int | None = None
    default_content: str | None = None
    default_content_type: str | None = None
    timeout: int | None = None
    cors: bool | None = None
    alias: str | None = None
    expiry: int | None = None
    
    def to_payload(self) -> dict[str, Any]:
        """Convert to API payload, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class WebhookInfo:
    """Detailed information about a webhook.
    
    Args:
        token: The webhook UUID
        alias: Custom alias if set
        url: Full webhook URL
        default_status: Response status code
        default_content: Response content
        default_content_type: Content-Type header
        timeout: Response delay in seconds
        cors: CORS enabled flag
        premium: Premium status
        actions: Custom actions enabled
        created_at: Creation timestamp
        updated_at: Last update timestamp
        expires_at: Expiration timestamp
        requests_count: Total requests received
    """
    token: str
    alias: str | None
    url: str
    default_status: int
    default_content: str
    default_content_type: str
    timeout: int
    cors: bool
    premium: bool
    actions: bool
    created_at: str
    updated_at: str
    expires_at: str | None
    premium_expires_at: str | None = None
    latest_request_at: str | None = None
    requests_count: int | None = None


@dataclass
class WebhookRequest:
    """A captured request to a webhook.
    
    Args:
        uuid: Request unique identifier
        method: HTTP method (GET, POST, etc.)
        content: Request body content
        headers: Request headers
        query: Query string parameters
        url: Full request URL
        ip: Client IP address
        created_at: Request timestamp
    """
    uuid: str
    method: str
    content: str | None
    headers: dict[str, list[str]] | None
    query: dict[str, str] | None = None
    url: str | None = None
    ip: str | None = None
    created_at: str | None = None
    
    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> WebhookRequest:
        """Create from API response data."""
        return cls(
            uuid=data.get("uuid", ""),
            method=data.get("method", ""),
            content=data.get("content"),
            headers=data.get("headers"),
            query=data.get("query"),
            url=data.get("url"),
            ip=data.get("ip"),
            created_at=data.get("created_at"),
        )


@dataclass
class SearchFilters:
    """Filters for searching webhook requests.
    
    Args:
        request_type: Filter by type ('web', 'email', 'dns')
        query: Additional search query string (e.g., 'method:POST', 'content:hello')
        date_from: Start date filter (format: yyyy-MM-dd HH:mm:ss)
        date_to: End date filter (format: yyyy-MM-dd HH:mm:ss)
        sorting: Sort order ('newest' or 'oldest')
        limit: Maximum results to return
    """
    request_type: str | None = None
    query: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    sorting: str = "newest"
    limit: int = 20
    
    def to_params(self) -> dict[str, Any]:
        """Convert to query parameters."""
        params = {"per_page": self.limit, "sorting": self.sorting}
        
        # Build query string with type filter if specified
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
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        result = {"success": self.success, "message": self.message}
        result.update(self.data)
        return json.dumps(result, indent=2)


# =============================================================================
# MCP TOOL DEFINITIONS
# =============================================================================

TOOL_DEFINITIONS: list[Tool] = [
    Tool(
        name="create_webhook",
        description="Create a new webhook.site endpoint. Returns the unique token/URL for the webhook.",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": []
        }
    ),
    Tool(
        name="create_webhook_with_config",
        description="Create a new webhook.site endpoint with custom configuration (response content, status, timeout, CORS, alias).",
        inputSchema={
            "type": "object",
            "properties": {
                "default_status": {
                    "type": "integer",
                    "description": "Default HTTP response status code (200-599)",
                    "default": 200
                },
                "default_content": {
                    "type": "string",
                    "description": "Default response content/body",
                    "default": ""
                },
                "default_content_type": {
                    "type": "string",
                    "description": "Default response Content-Type header",
                    "default": "text/html"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Seconds to wait before returning response (0-30)",
                    "default": 0
                },
                "cors": {
                    "type": "boolean",
                    "description": "Enable CORS headers for cross-domain requests",
                    "default": False
                },
                "alias": {
                    "type": "string",
                    "description": "Custom alias for the webhook URL (3-32 alphanumeric chars)"
                },
                "expiry": {
                    "type": "integer",
                    "description": "Seconds until webhook auto-expires (max 604800 = 1 week)"
                }
            },
            "required": []
        }
    ),
    Tool(
        name="send_to_webhook",
        description="Send a POST request with JSON data to a webhook.site endpoint.",
        inputSchema={
            "type": "object",
            "properties": {
                "webhook_token": {
                    "type": "string",
                    "description": "The webhook token (UUID) from webhook.site"
                },
                "data": {
                    "type": "object",
                    "description": "JSON data to send to the webhook"
                },
                "headers": {
                    "type": "object",
                    "description": "Optional custom headers to include in the request",
                    "default": {}
                }
            },
            "required": ["webhook_token", "data"]
        }
    ),
    Tool(
        name="get_webhook_requests",
        description="Get all requests that have been sent to a webhook.site endpoint.",
        inputSchema={
            "type": "object",
            "properties": {
                "webhook_token": {
                    "type": "string",
                    "description": "The webhook token (UUID) from webhook.site"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of requests to retrieve (default: 10)",
                    "default": 10
                },
                "request_type": {
                    "type": "string",
                    "description": "Filter by request type: 'web' (HTTP requests), 'email', or 'dns'",
                    "enum": ["web", "email", "dns"]
                }
            },
            "required": ["webhook_token"]
        }
    ),
    Tool(
        name="search_requests",
        description="Search requests sent to a webhook with query filters (method, content, headers, date range, type).",
        inputSchema={
            "type": "object",
            "properties": {
                "webhook_token": {
                    "type": "string",
                    "description": "The webhook token (UUID) from webhook.site"
                },
                "request_type": {
                    "type": "string",
                    "description": "Filter by request type: 'web' (HTTP requests), 'email', or 'dns'",
                    "enum": ["web", "email", "dns"]
                },
                "query": {
                    "type": "string",
                    "description": "Additional search query (e.g., 'method:POST', 'content:foobar', 'headers.user-agent:Mozilla')"
                },
                "date_from": {
                    "type": "string",
                    "description": "Filter from date (format: yyyy-MM-dd HH:mm:ss)"
                },
                "date_to": {
                    "type": "string",
                    "description": "Filter to date (format: yyyy-MM-dd HH:mm:ss)"
                },
                "sorting": {
                    "type": "string",
                    "description": "Sort order: 'newest' or 'oldest'",
                    "default": "newest"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of requests to retrieve",
                    "default": 20
                }
            },
            "required": ["webhook_token"]
        }
    ),
    Tool(
        name="get_latest_request",
        description="Get the most recent request sent to a webhook.site endpoint.",
        inputSchema={
            "type": "object",
            "properties": {
                "webhook_token": {
                    "type": "string",
                    "description": "The webhook token (UUID) from webhook.site"
                }
            },
            "required": ["webhook_token"]
        }
    ),
    Tool(
        name="get_webhook_info",
        description="Get detailed information about a webhook (settings, expiry, stats).",
        inputSchema={
            "type": "object",
            "properties": {
                "webhook_token": {
                    "type": "string",
                    "description": "The webhook token (UUID) from webhook.site"
                }
            },
            "required": ["webhook_token"]
        }
    ),
    Tool(
        name="update_webhook",
        description="Update webhook settings (response content, status code, timeout, CORS).",
        inputSchema={
            "type": "object",
            "properties": {
                "webhook_token": {
                    "type": "string",
                    "description": "The webhook token (UUID) from webhook.site"
                },
                "default_status": {
                    "type": "integer",
                    "description": "Default HTTP response status code (200-599)"
                },
                "default_content": {
                    "type": "string",
                    "description": "Default response content/body"
                },
                "default_content_type": {
                    "type": "string",
                    "description": "Default response Content-Type header"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Seconds to wait before returning response (0-30)"
                },
                "cors": {
                    "type": "boolean",
                    "description": "Enable CORS headers for cross-domain requests"
                }
            },
            "required": ["webhook_token"]
        }
    ),
    Tool(
        name="delete_webhook",
        description="Delete a webhook.site endpoint and all its data.",
        inputSchema={
            "type": "object",
            "properties": {
                "webhook_token": {
                    "type": "string",
                    "description": "The webhook token (UUID) from webhook.site"
                }
            },
            "required": ["webhook_token"]
        }
    ),
    Tool(
        name="delete_request",
        description="Delete a specific request from a webhook.",
        inputSchema={
            "type": "object",
            "properties": {
                "webhook_token": {
                    "type": "string",
                    "description": "The webhook token (UUID) from webhook.site"
                },
                "request_id": {
                    "type": "string",
                    "description": "The request UUID to delete"
                }
            },
            "required": ["webhook_token", "request_id"]
        }
    ),
    Tool(
        name="delete_all_requests",
        description="Delete all requests from a webhook, optionally filtered by date range or query.",
        inputSchema={
            "type": "object",
            "properties": {
                "webhook_token": {
                    "type": "string",
                    "description": "The webhook token (UUID) from webhook.site"
                },
                "date_from": {
                    "type": "string",
                    "description": "Delete requests from this date (format: yyyy-MM-dd HH:mm:ss or 'now-7d')"
                },
                "date_to": {
                    "type": "string",
                    "description": "Delete requests until this date (format: yyyy-MM-dd HH:mm:ss or 'now-7d')"
                },
                "query": {
                    "type": "string",
                    "description": "Delete only requests matching this search query"
                }
            },
            "required": ["webhook_token"]
        }
    ),
    Tool(
        name="get_webhook_url",
        description="Get the full URL for a webhook token. Optionally validate that the token exists.",
        inputSchema={
            "type": "object",
            "properties": {
                "webhook_token": {
                    "type": "string",
                    "description": "The webhook token (UUID) from webhook.site"
                },
                "validate": {
                    "type": "boolean",
                    "description": "If true, verify the token exists via API call before returning URL",
                    "default": False
                }
            },
            "required": ["webhook_token"]
        }
    ),
    Tool(
        name="get_webhook_email",
        description="Get the unique email address for a webhook token. Any emails sent to this address will be captured by the webhook. Optionally validate that the token exists.",
        inputSchema={
            "type": "object",
            "properties": {
                "webhook_token": {
                    "type": "string",
                    "description": "The webhook token (UUID) from webhook.site"
                },
                "validate": {
                    "type": "boolean",
                    "description": "If true, verify the token exists via API call before returning email",
                    "default": False
                }
            },
            "required": ["webhook_token"]
        }
    ),
    Tool(
        name="get_webhook_dns",
        description="Get the unique DNSHook domain for a webhook token. Any DNS lookups to this domain (or subdomains) will be captured. Useful for bypassing firewalls or as canary tokens. Optionally validate that the token exists.",
        inputSchema={
            "type": "object",
            "properties": {
                "webhook_token": {
                    "type": "string",
                    "description": "The webhook token (UUID) from webhook.site"
                },
                "validate": {
                    "type": "boolean",
                    "description": "If true, verify the token exists via API call before returning DNS domain",
                    "default": False
                }
            },
            "required": ["webhook_token"]
        }
    ),
    Tool(
        name="wait_for_request",
        description="Wait for a new HTTP request to be received by the webhook. Uses real-time streaming (SSE) to efficiently wait without polling. Useful for testing webhooks, callbacks, and API integrations.",
        inputSchema={
            "type": "object",
            "properties": {
                "webhook_token": {
                    "type": "string",
                    "description": "The webhook token (UUID) from webhook.site"
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Maximum time to wait in seconds (default: 60)",
                    "default": 60
                },
                "request_type": {
                    "type": "string",
                    "description": "Filter by request type: 'web' (HTTP requests), 'email', or 'dns'. Leave empty for any type.",
                    "enum": ["web", "email", "dns"]
                }
            },
            "required": ["webhook_token"]
        }
    ),
    Tool(
        name="wait_for_email",
        description="Wait for an email to be received at the webhook's email address ({token}@email.webhook.site). Uses real-time streaming (SSE) to efficiently wait. Automatically extracts links from the email, including magic/auth links for login flows.",
        inputSchema={
            "type": "object",
            "properties": {
                "webhook_token": {
                    "type": "string",
                    "description": "The webhook token (UUID) from webhook.site"
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Maximum time to wait in seconds (default: 60)",
                    "default": 60
                },
                "extract_links": {
                    "type": "boolean",
                    "description": "Whether to extract all URLs from the email body (default: true)",
                    "default": True
                }
            },
            "required": ["webhook_token"]
        }
    ),
    # =========================================================================
    # BUG BOUNTY TOOLS
    # =========================================================================
    Tool(
        name="generate_ssrf_payload",
        description="Generate SSRF (Server-Side Request Forgery) test payloads for bug bounty testing. Creates unique identifiable URLs that can be injected into targets to detect blind SSRF vulnerabilities.",
        inputSchema={
            "type": "object",
            "properties": {
                "webhook_token": {
                    "type": "string",
                    "description": "The webhook token (UUID) from webhook.site"
                },
                "identifier": {
                    "type": "string",
                    "description": "Custom identifier to include in payload (e.g., 'param1', 'header-injection')"
                },
                "include_dns": {
                    "type": "boolean",
                    "description": "Include DNS-based payload for blind SSRF detection (default: true)",
                    "default": True
                },
                "include_ip": {
                    "type": "boolean",
                    "description": "Include IP-based payloads to bypass domain filters (default: true)",
                    "default": True
                }
            },
            "required": ["webhook_token"]
        }
    ),
    Tool(
        name="check_for_callbacks",
        description="Quick check if any OOB (Out-of-Band) callbacks have been received. Useful for bug bounty to verify if SSRF, XXE, or blind injection payloads were triggered.",
        inputSchema={
            "type": "object",
            "properties": {
                "webhook_token": {
                    "type": "string",
                    "description": "The webhook token (UUID) from webhook.site"
                },
                "since_minutes": {
                    "type": "integer",
                    "description": "Only check requests from the last N minutes (default: 60)",
                    "default": 60
                },
                "identifier": {
                    "type": "string",
                    "description": "Filter for specific identifier in request URL/content"
                }
            },
            "required": ["webhook_token"]
        }
    ),
    Tool(
        name="generate_xss_callback",
        description="Generate XSS (Cross-Site Scripting) callback payloads for bug bounty testing. Creates JavaScript payloads that ping your webhook when executed, useful for detecting blind XSS.",
        inputSchema={
            "type": "object",
            "properties": {
                "webhook_token": {
                    "type": "string",
                    "description": "The webhook token (UUID) from webhook.site"
                },
                "identifier": {
                    "type": "string",
                    "description": "Custom identifier to track which injection point triggered (e.g., 'comment-field', 'profile-name')"
                },
                "include_cookies": {
                    "type": "boolean",
                    "description": "Include payload that exfiltrates cookies (default: true)",
                    "default": True
                },
                "include_dom": {
                    "type": "boolean",
                    "description": "Include payload that captures DOM info like URL and referrer (default: true)",
                    "default": True
                }
            },
            "required": ["webhook_token"]
        }
    ),
    Tool(
        name="generate_canary_token",
        description="Generate canary tokens for detecting unauthorized access or data leakage. Creates trackable URLs that alert you when accessed.",
        inputSchema={
            "type": "object",
            "properties": {
                "webhook_token": {
                    "type": "string",
                    "description": "The webhook token (UUID) from webhook.site"
                },
                "token_type": {
                    "type": "string",
                    "description": "Type of canary token: 'url' (web link), 'dns' (DNS lookup), 'email' (email tracker)",
                    "enum": ["url", "dns", "email"],
                    "default": "url"
                },
                "identifier": {
                    "type": "string",
                    "description": "Custom identifier for the canary (e.g., 'confidential-doc', 'admin-panel')"
                }
            },
            "required": ["webhook_token"]
        }
    ),
    Tool(
        name="extract_links_from_request",
        description="Extract and analyze all URLs/links from a captured request. Useful for finding password reset links, verification tokens, and other sensitive URLs.",
        inputSchema={
            "type": "object",
            "properties": {
                "webhook_token": {
                    "type": "string",
                    "description": "The webhook token (UUID) from webhook.site"
                },
                "request_id": {
                    "type": "string",
                    "description": "Specific request UUID to analyze (optional, defaults to latest)"
                },
                "filter_domain": {
                    "type": "string",
                    "description": "Only return links matching this domain"
                }
            },
            "required": ["webhook_token"]
        }
    ),
]
