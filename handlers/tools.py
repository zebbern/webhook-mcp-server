"""Typed MCP tool registrations for webhook.site operations."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from pydantic import Field

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
Token = Annotated[
    str,
    Field(description="Webhook UUID returned by create_webhook"),
]


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
        """Create a disposable inbox to sign up on a website: HTTP URL, temp email, DNS.

        Use this first when the user wants to sign up, receive a verification /
        magic-link / password-reset email, catch a webhook callback, or get a
        one-off URL. Returns token, url, email ({token}@email.webhook.site),
        and dns. Next: give the email or URL to the site, then wait_for_email
        or wait_for_request.
        """
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
        """Create a webhook that returns a custom status, body, timeout, CORS, or alias.

        Use when the user wants the endpoint to pretend to be an API (404, delay,
        JSON body) instead of a default 200. For a normal sign-up inbox, use
        create_webhook.
        """

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
        webhook_token: Token,
        data: dict[str, Any],
        ctx: Context[AppContext],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """POST JSON to the webhook URL to test that capture works.

        Use when the user wants to send a sample payload, not when they are
        waiting for a real site or email.
        """

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).webhooks.send_data(webhook_token, data, headers)

        return await _execute(_op)

    @mcp.tool()
    async def get_webhook_requests(
        webhook_token: Token,
        ctx: Context[AppContext],
        limit: int = 10,
        request_type: RequestType | None = None,
    ) -> dict[str, Any]:
        """List captured HTTP, email, or DNS events for a webhook.

        Use to inspect what already arrived. Bodies are truncated and HTML is
        omitted; use export_webhook_data for the full dump. For the newest item
        use get_latest_request. To wait for something new use wait_for_request
        or wait_for_email. Filter emails with request_type='email'.
        """

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).requests.get_all(webhook_token, limit, request_type)

        return await _execute(_op)

    @mcp.tool()
    async def search_requests(
        webhook_token: Token,
        ctx: Context[AppContext],
        request_type: RequestType | None = None,
        query: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sorting: str = "newest",
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search captured events by method, body text, headers, type, or date.

        Use when the user asks to find POSTs, a keyword, or only emails/DNS.
        Examples: query='method:POST', query='content:verify', request_type='email'.
        """

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
        webhook_token: Token,
        ctx: Context[AppContext],
    ) -> dict[str, Any]:
        """Return only the newest captured event (HTTP, email, or DNS).

        Use for a quick peek. Prefer wait_for_email after a sign-up, or
        get_webhook_requests to see history.
        """

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).requests.get_latest(webhook_token)

        return await _execute(_op)

    @mcp.tool()
    async def get_webhook_info(
        webhook_token: Token,
        ctx: Context[AppContext],
    ) -> dict[str, Any]:
        """Show webhook settings, expiry, and how many requests it has received.

        Use when the user asks if a token is still valid or how it is configured.
        """

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).webhooks.get_info(webhook_token)

        return await _execute(_op)

    @mcp.tool()
    async def update_webhook(
        webhook_token: Token,
        ctx: Context[AppContext],
        default_status: int | None = None,
        default_content: str | None = None,
        default_content_type: str | None = None,
        timeout: int | None = None,
        cors: bool | None = None,
    ) -> dict[str, Any]:
        """Change how an existing webhook responds (status, body, timeout, CORS).

        Use after create_webhook when the user wants a different canned reply.
        """

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
        webhook_token: Token,
        ctx: Context[AppContext],
    ) -> dict[str, Any]:
        """Permanently delete a webhook and every captured request/email.

        Use when the user is done with a temp inbox or wants to clean up.
        """

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).webhooks.delete(webhook_token)

        return await _execute(_op)

    @mcp.tool()
    async def delete_request(
        webhook_token: Token,
        request_id: str,
        ctx: Context[AppContext],
    ) -> dict[str, Any]:
        """Delete one captured HTTP, email, or DNS event by request id."""

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).requests.delete_one(webhook_token, request_id)

        return await _execute(_op)

    @mcp.tool()
    async def delete_all_requests(
        webhook_token: Token,
        ctx: Context[AppContext],
        date_from: str | None = None,
        date_to: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Clear captured events on a webhook, optionally by date or search query.

        Use to reset an inbox before a new sign-up or test run.
        """

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            filters = None
            if any(value is not None for value in (date_from, date_to, query)):
                filters = DeleteFilters(date_from=date_from, date_to=date_to, query=query)
            return _app(ctx).requests.delete_all(webhook_token, filters)

        return await _execute(_op)

    @mcp.tool()
    async def get_webhook_url(
        webhook_token: Token,
        ctx: Context[AppContext],
        validate: bool = False,
    ) -> dict[str, Any]:
        """Return https://webhook.site/{token} for an existing webhook.

        Use when the user already has a token and needs the HTTP callback URL.
        For a new inbox, create_webhook already returns url.
        """

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).webhooks.get_url(webhook_token, validate=validate)

        return await _execute(_op)

    @mcp.tool()
    async def get_webhook_email(
        webhook_token: Token,
        ctx: Context[AppContext],
        validate: bool = False,
    ) -> dict[str, Any]:
        """Return the temp inbox to sign up, verify, magic-link, or reset a password.

        Address is {token}@email.webhook.site. Use when the user already has a
        token. If they do not, call create_webhook first — it also returns
        email. After the site sends mail, call wait_for_email.
        """

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).webhooks.get_email(webhook_token, validate=validate)

        return await _execute(_op)

    @mcp.tool()
    async def get_webhook_dns(
        webhook_token: Token,
        ctx: Context[AppContext],
        validate: bool = False,
    ) -> dict[str, Any]:
        """Return the DNSHook domain for an existing webhook.

        Use for out-of-band DNS callbacks, not for sign-up email. create_webhook
        already returns dns.
        """

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).webhooks.get_dns(webhook_token, validate=validate)

        return await _execute(_op)

    @mcp.tool()
    async def wait_for_request(
        webhook_token: Token,
        ctx: Context[AppContext],
        timeout_seconds: int = 60,
        request_type: RequestType | None = None,
        return_existing: bool = False,
    ) -> dict[str, Any]:
        """Poll until a new HTTP (or DNS) callback hits the webhook (1-120s).

        Use after giving a site the webhook URL. Bodies are truncated and HTML
        is omitted; use export_webhook_data for the full dump. For verification
        / magic-link / password-reset mail, use wait_for_email instead. Set
        return_existing=true if the request may already be there.
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
        webhook_token: Token,
        ctx: Context[AppContext],
        timeout_seconds: int = 60,
        extract_links: bool = True,
        return_existing: bool = False,
    ) -> dict[str, Any]:
        """Wait for a sign-up, verify, magic-link, or password-reset email (1-120s).

        Call this after the user (or you) submitted {token}@email.webhook.site
        on a website. Returns subject, a truncated text preview, and extracted
        confirm / reset / login URLs. HTML is omitted; use export_webhook_data
        for the full message. Set return_existing=true if the email already
        arrived. If there is no token yet, create_webhook first.
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
        webhook_token: Token,
        ctx: Context[AppContext],
        identifier: str | None = None,
        include_dns: bool = True,
        include_ip: bool = True,
    ) -> dict[str, Any]:
        """Build authorized SSRF callback URLs that ping this webhook.

        Use only on systems you are allowed to test — not for sign-up email.
        Confirm hits with check_for_callbacks. local_bypass_examples cannot
        be confirmed here.
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
        webhook_token: Token,
        ctx: Context[AppContext],
        since_minutes: int = 60,
        identifier: str | None = None,
    ) -> dict[str, Any]:
        """See if SSRF, XSS, or canary callbacks arrived in the last N minutes.

        Use after generate_ssrf_payload / generate_xss_callback / generate_canary_token.
        For a website verification email, use wait_for_email.
        """

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
        webhook_token: Token,
        ctx: Context[AppContext],
        identifier: str | None = None,
        include_cookies: bool = True,
        include_dom: bool = True,
    ) -> dict[str, Any]:
        """Build authorized XSS payloads that ping this webhook when they run.

        Use only on systems you are allowed to test. Confirm with check_for_callbacks.
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
        webhook_token: Token,
        ctx: Context[AppContext],
        token_type: CanaryType = "url",
        identifier: str | None = None,
    ) -> dict[str, Any]:
        """Make a canary URL, DNS name, or email that alerts when someone opens it.

        Use to mark your own files or systems. token_type='email' is a tripwire,
        not a sign-up inbox — use create_webhook + wait_for_email for that.
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
        webhook_token: Token,
        ctx: Context[AppContext],
        request_id: str | None = None,
        filter_domain: str | None = None,
    ) -> dict[str, Any]:
        """Pull confirm, reset, magic-link, and other URLs from a captured email or HTTP body.

        Use after wait_for_email or get_webhook_requests when the user needs
        the verification / login / password-reset link. Defaults to the latest
        event. wait_for_email already extracts links when extract_links=true.
        """

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
        webhook_token: Token,
        payloads: list[dict[str, Any]],
        ctx: Context[AppContext],
        delay_ms: int = 0,
    ) -> dict[str, Any]:
        """POST several sample JSON payloads to the webhook, optionally spaced out.

        Use to load-test capture, not to wait for a real site or email.
        """

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
        webhook_token: Token,
        ctx: Context[AppContext],
        limit: int = 100,
    ) -> dict[str, Any]:
        """Full dump of captured HTTP/email/DNS events, including HTML and untruncated bodies.

        Use this when list/wait tools omitted HTML or truncated a body.
        """

        def _op() -> Awaitable[ToolResult]:
            validate_webhook_token(webhook_token)
            return _app(ctx).requests.export_requests(webhook_token, limit=limit)

        return await _execute(_op)
