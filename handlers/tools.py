"""Typed MCP tool registrations for webhook.site operations."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver import Context

from models.app_context import AppContext
from models.schemas import DeleteFilters, SearchFilters, ToolResult, WebhookConfig
from utils.http_client import WebhookApiError
from utils.logger import setup_logger
from utils.validation import (
    ValidationError,
    validate_alias,
    validate_expiry,
    validate_http_status_code,
    validate_positive_int,
    validate_webhook_token,
)

logger = setup_logger(__name__)

RequestType = Literal["web", "email", "dns"]
CanaryType = Literal["url", "dns", "email"]


def _app(ctx: Context[AppContext]) -> AppContext:
    return ctx.request_context.lifespan_context


def _error_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ValidationError):
        return {"success": False, "message": f"Validation Error: {exc}"}
    if isinstance(exc, WebhookApiError):
        return {"success": False, "message": f"API Error: {exc}"}
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return {"success": False, "message": f"Error: {exc}"}
    logger.exception("Unexpected error in tool")
    return {
        "success": False,
        "message": "An unexpected error occurred. Please report this issue.",
    }


async def _execute(action: Callable[[], Any]) -> dict[str, Any]:
    try:
        result = action()
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, ToolResult):
            return result.to_dict()
        return result
    except Exception as exc:
        return _error_payload(exc)


def register_tools(mcp: MCPServer[AppContext]) -> None:
    """Register all webhook.site tools on the MCP server."""

    @mcp.tool()
    async def create_webhook(ctx: Context[AppContext]) -> dict[str, Any]:
        """Create a new webhook.site endpoint. Returns the unique token/URL for the webhook."""
        return await _execute(lambda: _app(ctx).webhooks.create())

    @mcp.tool()
    async def create_webhook_with_config(
        ctx: Context[AppContext],
        default_status: int | None = None,
        default_content: str | None = None,
        default_content_type: str | None = None,
        timeout: int | None = None,
        cors: bool | None = None,
        alias: str | None = None,
        expiry: int | None = None,
    ) -> dict[str, Any]:
        """Create a webhook.site endpoint with custom response, status, timeout, CORS, or alias."""

        def _op() -> Awaitable[ToolResult]:
            if default_status is not None:
                validate_http_status_code(default_status)
            if timeout is not None:
                validate_positive_int(timeout, "timeout", min_val=0, max_val=30)
            if alias is not None:
                validate_alias(alias)
            if expiry is not None:
                validate_expiry(expiry)
            config = WebhookConfig(
                default_status=default_status,
                default_content=default_content,
                default_content_type=default_content_type,
                timeout=timeout,
                cors=cors,
                alias=alias,
                expiry=expiry,
            )
            return _app(ctx).webhooks.create_with_config(config)

        return await _execute(_op)

    @mcp.tool()
    async def send_to_webhook(
        webhook_token: str,
        data: dict[str, Any],
        ctx: Context[AppContext],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Send a POST request with JSON data to a webhook.site endpoint."""

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).webhooks.send_data(webhook_token, data, headers)

        return await _execute(_op)

    @mcp.tool()
    async def get_webhook_requests(
        webhook_token: str,
        ctx: Context[AppContext],
        limit: int = 10,
        request_type: RequestType | None = None,
    ) -> dict[str, Any]:
        """Get requests that have been sent to a webhook.site endpoint."""

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).requests.get_all(webhook_token, limit, request_type)

        return await _execute(_op)

    @mcp.tool()
    async def search_requests(
        webhook_token: str,
        ctx: Context[AppContext],
        request_type: RequestType | None = None,
        query: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sorting: str = "newest",
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search requests with filters (method, content, headers, date range, type)."""

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            filters = SearchFilters(
                request_type=request_type,
                query=query,
                date_from=date_from,
                date_to=date_to,
                sorting=sorting,
                limit=limit,
            )
            return _app(ctx).requests.search(webhook_token, filters)

        return await _execute(_op)

    @mcp.tool()
    async def get_latest_request(
        webhook_token: str,
        ctx: Context[AppContext],
    ) -> dict[str, Any]:
        """Get the most recent request sent to a webhook.site endpoint."""

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).requests.get_latest(webhook_token)

        return await _execute(_op)

    @mcp.tool()
    async def get_webhook_info(
        webhook_token: str,
        ctx: Context[AppContext],
    ) -> dict[str, Any]:
        """Get detailed information about a webhook (settings, expiry, stats)."""

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).webhooks.get_info(webhook_token)

        return await _execute(_op)

    @mcp.tool()
    async def update_webhook(
        webhook_token: str,
        ctx: Context[AppContext],
        default_status: int | None = None,
        default_content: str | None = None,
        default_content_type: str | None = None,
        timeout: int | None = None,
        cors: bool | None = None,
    ) -> dict[str, Any]:
        """Update webhook settings (response content, status code, timeout, CORS)."""

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            if default_status is not None:
                validate_http_status_code(default_status)
            if timeout is not None:
                validate_positive_int(timeout, "timeout", min_val=0, max_val=30)
            config = WebhookConfig(
                default_status=default_status,
                default_content=default_content,
                default_content_type=default_content_type,
                timeout=timeout,
                cors=cors,
            )
            return _app(ctx).webhooks.update(webhook_token, config)

        return await _execute(_op)

    @mcp.tool()
    async def delete_webhook(
        webhook_token: str,
        ctx: Context[AppContext],
    ) -> dict[str, Any]:
        """Delete a webhook.site endpoint and all its data."""

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).webhooks.delete(webhook_token)

        return await _execute(_op)

    @mcp.tool()
    async def delete_request(
        webhook_token: str,
        request_id: str,
        ctx: Context[AppContext],
    ) -> dict[str, Any]:
        """Delete a specific request from a webhook."""

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).requests.delete_one(webhook_token, request_id)

        return await _execute(_op)

    @mcp.tool()
    async def delete_all_requests(
        webhook_token: str,
        ctx: Context[AppContext],
        date_from: str | None = None,
        date_to: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Delete all requests from a webhook, optionally filtered by date range or query."""

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            filters = None
            if any(value is not None for value in (date_from, date_to, query)):
                filters = DeleteFilters(date_from=date_from, date_to=date_to, query=query)
            return _app(ctx).requests.delete_all(webhook_token, filters)

        return await _execute(_op)

    @mcp.tool()
    async def get_webhook_url(
        webhook_token: str,
        ctx: Context[AppContext],
        validate: bool = False,
    ) -> dict[str, Any]:
        """Get the full URL for a webhook token. Optionally verify that the token exists."""

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).webhooks.get_url(webhook_token, validate=validate)

        return await _execute(_op)

    @mcp.tool()
    async def get_webhook_email(
        webhook_token: str,
        ctx: Context[AppContext],
        validate: bool = False,
    ) -> dict[str, Any]:
        """Get the unique email address for a webhook token. Emails sent there are captured."""

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).webhooks.get_email(webhook_token, validate=validate)

        return await _execute(_op)

    @mcp.tool()
    async def get_webhook_dns(
        webhook_token: str,
        ctx: Context[AppContext],
        validate: bool = False,
    ) -> dict[str, Any]:
        """Get the DNSHook domain for a webhook token. DNS lookups to it are captured."""

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).webhooks.get_dns(webhook_token, validate=validate)

        return await _execute(_op)

    @mcp.tool()
    async def wait_for_request(
        webhook_token: str,
        ctx: Context[AppContext],
        timeout_seconds: int = 60,
        request_type: RequestType | None = None,
        return_existing: bool = False,
    ) -> dict[str, Any]:
        """Wait for a new HTTP request by polling webhook.site (1-120 seconds).

        By default this waits for a request that arrives after the call starts.
        Set return_existing=true to return a matching request that is already present.
        """

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).requests.wait_for_request(
                webhook_token,
                timeout_seconds=timeout_seconds,
                request_type=request_type,
                return_existing=return_existing,
            )

        return await _execute(_op)

    @mcp.tool()
    async def wait_for_email(
        webhook_token: str,
        ctx: Context[AppContext],
        timeout_seconds: int = 60,
        extract_links: bool = True,
        return_existing: bool = False,
    ) -> dict[str, Any]:
        """Wait for a new email at {token}@email.webhook.site by polling (1-120 seconds).

        By default this waits for an email that arrives after the call starts.
        Set return_existing=true to return an email that is already present.
        """

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).requests.wait_for_email(
                webhook_token,
                timeout_seconds=timeout_seconds,
                extract_links=extract_links,
                return_existing=return_existing,
            )

        return await _execute(_op)

    @mcp.tool()
    async def generate_ssrf_payload(
        webhook_token: str,
        ctx: Context[AppContext],
        identifier: str | None = None,
        include_dns: bool = True,
        include_ip: bool = True,
    ) -> dict[str, Any]:
        """Generate authorized SSRF test payloads that callback to this webhook.

        For use only on systems you are authorized to test. callback_payloads can be
        confirmed with check_for_callbacks; local_bypass_examples cannot.
        """

        def _op() -> ToolResult:
            validate_webhook_token(webhook_token)
            return _app(ctx).bounty.generate_ssrf_payload(
                webhook_token,
                identifier=identifier,
                include_dns=include_dns,
                include_ip=include_ip,
            )

        return await _execute(_op)

    @mcp.tool()
    async def check_for_callbacks(
        webhook_token: str,
        ctx: Context[AppContext],
        since_minutes: int = 60,
        identifier: str | None = None,
    ) -> dict[str, Any]:
        """Check whether any out-of-band callbacks were received in the last N minutes."""

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).bounty.check_for_callbacks(
                webhook_token,
                since_minutes=since_minutes,
                identifier=identifier,
            )

        return await _execute(_op)

    @mcp.tool()
    async def generate_xss_callback(
        webhook_token: str,
        ctx: Context[AppContext],
        identifier: str | None = None,
        include_cookies: bool = True,
        include_dom: bool = True,
    ) -> dict[str, Any]:
        """Generate authorized XSS callback payloads that ping this webhook when executed.

        For use only on systems you are authorized to test.
        """

        def _op() -> ToolResult:
            validate_webhook_token(webhook_token)
            return _app(ctx).bounty.generate_xss_callback(
                webhook_token,
                identifier=identifier,
                include_cookies=include_cookies,
                include_dom=include_dom,
            )

        return await _execute(_op)

    @mcp.tool()
    async def generate_canary_token(
        webhook_token: str,
        ctx: Context[AppContext],
        token_type: CanaryType = "url",
        identifier: str | None = None,
    ) -> dict[str, Any]:
        """Generate a canary URL, DNS name, or email that alerts when accessed.

        For authorized monitoring of your own documents and systems only.
        """

        def _op() -> ToolResult:
            validate_webhook_token(webhook_token)
            return _app(ctx).bounty.generate_canary_token(
                webhook_token,
                token_type=token_type,
                identifier=identifier,
            )

        return await _execute(_op)

    @mcp.tool()
    async def extract_links_from_request(
        webhook_token: str,
        ctx: Context[AppContext],
        request_id: str | None = None,
        filter_domain: str | None = None,
    ) -> dict[str, Any]:
        """Extract URLs from a captured request. Defaults to the latest request."""

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).bounty.extract_links_from_request(
                webhook_token,
                request_id=request_id,
                filter_domain=filter_domain,
            )

        return await _execute(_op)

    @mcp.tool()
    async def send_multiple_requests(
        webhook_token: str,
        payloads: list[dict[str, Any]],
        ctx: Context[AppContext],
        delay_ms: int = 0,
    ) -> dict[str, Any]:
        """Send multiple JSON payloads to a webhook, optionally delayed between requests."""

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).requests.send_multiple(
                webhook_token,
                payloads=payloads,
                delay_ms=delay_ms,
            )

        return await _execute(_op)

    @mcp.tool()
    async def export_webhook_data(
        webhook_token: str,
        ctx: Context[AppContext],
        limit: int = 100,
    ) -> dict[str, Any]:
        """Export captured requests from a webhook to JSON."""

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).requests.export_requests(webhook_token, limit=limit)

        return await _execute(_op)
