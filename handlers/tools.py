"""Typed MCP tool registrations for webhook.site operations."""

from __future__ import annotations

import inspect
import json
import sys
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from models.app_context import AppContext
from models.schemas import DeleteFilters, SearchFilters, ToolResult, WebhookConfig
from utils import action_types, recorder, webhookscript
from utils.http_client import WebhookApiError
from utils.logger import setup_logger
from utils.validation import (
    ValidationError,
    validate_alias,
    validate_expiry,
    validate_http_status_code,
    validate_int_id,
    validate_listen,
    validate_note,
    validate_page,
    validate_positive_int,
    validate_request_limit,
    extract_token_reference,
    looks_like_alias,
    looks_like_uuid,
)

logger = setup_logger(__name__)

RequestType = Literal["web", "email", "dns"]
CanaryType = Literal["url", "dns", "email"]
PayloadKind = Literal["ssrf", "xss", "canary"]
ExportFormat = Literal["json", "csv"]
CrudAction = Literal["list", "create", "update", "delete"]
ActionAction = Literal["list", "create", "update", "delete", "test", "execute", "types", "variables", "script_reference"]
ScheduleAction = Literal["list", "get", "create", "update", "delete", "run", "logs"]
DatabaseAction = Literal["list", "create", "update", "delete", "query"]
UserAction = Literal["list", "invite", "update", "delete"]
Token = Annotated[
    str,
    Field(description="Webhook UUID or alias from create_webhook / configure_webhook; a webhook.site URL or {token}@emailhook.site address works too"),
]
# Free text that often carries JSON (a response body, a note, a variable value).
# The MCP SDK pre-parses JSON-looking strings into objects for any field whose
# annotation is not exactly `str`, so accept the object form too and serialise it.
JsonText = str | dict[str, Any] | list[Any] | None


def _text(value: JsonText) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value)

# Tool annotations: hints for MCP clients, never a gate on what a tool can do.
_OPEN = {"open_world_hint": True}
RO = ToolAnnotations(read_only_hint=True, **_OPEN)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, **_OPEN)
WRITE_IDEMPOTENT = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, **_OPEN)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, **_OPEN)
FAMILY = ToolAnnotations(read_only_hint=False, destructive_hint=True, **_OPEN)
FOLLOW = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, **_OPEN)


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


_UNSET: Any = object()


async def _resolve_token(ctx: Context[AppContext], value: str | None) -> str | None:
    """Turn what the caller passed (UUID, alias, URL, email, DNS name) into the token UUID.

    GET /token/{alias} answers with the token (verified live 2026-09-03) even
    though the docs say aliases are not accepted in API URLs; the sub-resource
    paths really do 404 on an alias, so everything downstream uses the UUID.
    """
    if value is None:
        return None
    reference = extract_token_reference(value)
    if looks_like_uuid(reference):
        return reference
    if not looks_like_alias(reference):
        raise ValidationError(
            f"Invalid webhook token: expected a UUID, an alias (3-32 letters, digits, - or _), "
            f"or a webhook.site URL / email address, got: {value[:40]}"
        )
    try:
        data = await _app(ctx).client.get(f"/token/{reference}")
    except WebhookApiError as exc:
        if exc.status_code == 404:
            raise ValidationError(f"No webhook with alias '{reference}' (aliases need the API key of the owning account)") from exc
        raise
    uuid = data.get("uuid") if isinstance(data, dict) else None
    if not uuid:
        raise ValidationError(f"Could not resolve alias '{reference}' to a token")
    return uuid


async def _execute(
    action: Callable[..., Any],
    ctx: Context[AppContext] | None = None,
    webhook_token: str | None = _UNSET,
) -> dict[str, Any]:
    active = recorder.active()
    if active is not None:
        # Called from inside each tool coroutine; its frame name is the tool name.
        active.mark(sys._getframe(1).f_code.co_name)
    try:
        if webhook_token is _UNSET:
            result = action()
        else:
            # The tool's _op receives the resolved UUID (or None when optional).
            result = action(await _resolve_token(ctx, webhook_token))
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, ToolResult):
            return result.to_dict()
        return result
    except Exception as exc:
        return _error_payload(exc)


def _require(value: Any, name: str, action: str) -> Any:
    if value is None:
        raise ValidationError(f"{name} is required for action='{action}'")
    return value


def _require_id(value: Any, name: str, action: str) -> int:
    validate_int_id(_require(value, name, action), name)
    return value


def register_tools(mcp: MCPServer[AppContext]) -> None:
    """Register all webhook.site tools on the MCP server."""

    # --- diagnostics ----------------------------------------------------------

    @mcp.tool(annotations=RO)
    async def server_status(ctx: Context[AppContext], check_socket: bool = True) -> dict[str, Any]:
        """Check this server's setup: API key, account reachability, plan, real-time socket, env config.

        Call first when a tool fails unexpectedly or before relying on account
        features. Lists problems in plain words.
        """

        def _op() -> Awaitable[ToolResult]:
            status = _app(ctx).status
            if status is None:
                raise ValidationError("Status service is not configured")
            return status.report(check_socket=check_socket)

        return await _execute(_op)

    # --- webhooks -----------------------------------------------------------

    @mcp.tool(annotations=WRITE)
    async def create_webhook(ctx: Context[AppContext]) -> dict[str, Any]:
        """Create a disposable inbox to sign up on a website: HTTP URL, temp email, DNS.

        Use this first when the user wants to sign up, receive a verification /
        magic-link / password-reset email, catch a webhook callback, or get a
        one-off URL. Returns token, url, email ({token}@emailhook.site),
        and dns. Next: give the email or URL to the site, then wait_for_email,
        then follow_email_link or use the OTP. With an API key the URL is
        permanent (premium) unless WEBHOOK_SITE_DEFAULT_EXPIRY is set; use
        configure_webhook for custom responses, alias, expiry or request_limit.
        """
        return await _execute(lambda: _app(ctx).webhooks.create())

    @mcp.tool(annotations=WRITE)
    async def configure_webhook(
        ctx: Context[AppContext],
        webhook_token: str | None = None,
        default_status: int | None = None,
        default_content: JsonText = None,
        default_content_type: str | None = None,
        timeout: int | None = None,
        listen: int | None = None,
        cors: bool | None = None,
        alias: str | None = None,
        expiry: int | None = None,
        request_limit: int | None = None,
        actions: bool | None = None,
        clone_from: str | None = None,
        group_id: int | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a webhook with custom settings, or update one (pass webhook_token).

        Use when the endpoint should pretend to be an API (status, body, content
        type, delay up to 30s, CORS), needs an alias, expiry (seconds), a
        request_limit (0 stores nothing), listen (seconds to wait for
        update_request response), actions on/off, clone_from another token, a
        group_id, or a description (label shown in the Control Panel).
        default_content can be a JSON array of DNS records
        ([{"type":"a","value":"..."}]) to answer DNSHook lookups. Updates keep
        every setting you do not mention; alias="" removes the alias. For a
        plain sign-up inbox use create_webhook.
        """

        def _op(webhook_token: str | None) -> Awaitable[ToolResult]:
            if default_status is not None:
                validate_http_status_code(default_status)
            if timeout is not None:
                validate_positive_int(timeout, "timeout", min_val=0, max_val=30)
            if listen is not None:
                validate_listen(listen)
            if alias:  # "" clears the alias (PUT alias=null, verified live)
                validate_alias(alias)
            if expiry is not None:
                validate_expiry(expiry)
            if request_limit is not None:
                validate_request_limit(request_limit)
            if group_id is not None:
                validate_int_id(group_id, "group_id")
            config = WebhookConfig(
                default_status=default_status,
                default_content=_text(default_content),
                default_content_type=default_content_type,
                timeout=timeout,
                listen=listen,
                cors=cors,
                alias=alias,
                expiry=expiry,
                request_limit=request_limit,
                actions=actions,
                clone_from=clone_from,
                group_id=group_id,
                description=description,
            )
            return _app(ctx).webhooks.configure(config, webhook_token=webhook_token)

        return await _execute(_op, ctx, webhook_token)

    @mcp.tool(annotations=RO)
    async def get_webhook_info(
        webhook_token: Token,
        ctx: Context[AppContext],
    ) -> dict[str, Any]:
        """Show a webhook's settings, expiry, request count and every address.

        Returns url, subdomain_url, force_status_url (append a status code to
        make the URL answer with it), api_url, email and dns for the token, plus
        premium / expires_at / alias / request_limit. Use when the user asks if a
        token is still valid, how it is configured, or needs its callback URL or
        DNSHook domain.
        """

        def _op(webhook_token: str) -> Awaitable[ToolResult]:
            return _app(ctx).webhooks.get_info(webhook_token)

        return await _execute(_op, ctx, webhook_token)

    @mcp.tool(annotations=RO)
    async def get_webhook_email(
        webhook_token: Token,
        ctx: Context[AppContext],
        validate: bool = False,
    ) -> dict[str, Any]:
        """Return the temp inbox to sign up, verify, magic-link, or reset a password.

        Address is {token}@emailhook.site. Use when the user already has a
        token. If they do not, call create_webhook first — it also returns
        email. After the site sends mail, call wait_for_email.
        """

        def _op(webhook_token: str) -> Awaitable[ToolResult]:
            return _app(ctx).webhooks.get_email(webhook_token, validate=validate)

        return await _execute(_op, ctx, webhook_token)

    @mcp.tool(annotations=RO)
    async def list_webhooks(
        ctx: Context[AppContext],
        page: int = 1,
        per_page: int = 50,
        order_by: Literal["created_at", "token_id"] = "created_at",
        order_direction: Literal["asc", "desc"] = "desc",
        max_items: int = 200,
    ) -> dict[str, Any]:
        """List the webhooks (URLs / inboxes) in the account. Needs WEBHOOK_SITE_API_KEY.

        Use to find an existing token, alias, request count or latest_request_at
        before creating a new one. Returns pagination.
        """

        def _op() -> Awaitable[ToolResult]:
            validate_page(page, per_page)
            validate_positive_int(max_items, "max_items", min_val=1, max_val=1000)
            return _app(ctx).account.list_tokens(
                page=page,
                per_page=per_page,
                order_by=order_by,
                order_direction=order_direction,
                max_items=max_items,
            )

        return await _execute(_op)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def delete_webhook(
        webhook_token: Token,
        ctx: Context[AppContext],
    ) -> dict[str, Any]:
        """Permanently delete a webhook and every captured request/email.

        Use when the user is done with a temp inbox or wants to clean up.
        """

        def _op(webhook_token: str) -> Awaitable[ToolResult]:
            return _app(ctx).webhooks.delete(webhook_token)

        return await _execute(_op, ctx, webhook_token)

    # --- requests -------------------------------------------------------------

    @mcp.tool(annotations=RO)
    async def get_webhook_requests(
        webhook_token: Token,
        ctx: Context[AppContext],
        limit: int = 10,
        request_type: RequestType | None = None,
        page: int = 1,
        since: int | None = None,
    ) -> dict[str, Any]:
        """List captured HTTP, email, or DNS events for a webhook, one page at a time.

        Use to inspect what already arrived. Bodies are truncated and HTML is
        omitted; use export_webhook_data for the full dump. For the newest item
        use get_request. To wait for something new use wait_for_request or
        wait_for_email. Filter emails with request_type='email'. Returns
        pagination (is_last_page, total) and next_since: pass it back as
        since to get only what arrived after that call (no paging, no
        duplicates).
        """

        def _op(webhook_token: str) -> Awaitable[ToolResult]:
            validate_page(page, limit)
            return _app(ctx).requests.get_all(webhook_token, limit, request_type, page=page, since=since)

        return await _execute(_op, ctx, webhook_token)

    @mcp.tool(annotations=RO)
    async def search_requests(
        webhook_token: Token,
        ctx: Context[AppContext],
        request_type: RequestType | None = None,
        query: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sorting: Literal["newest", "oldest"] = "newest",
        limit: int = 20,
        page: int = 1,
        since: int | None = None,
    ) -> dict[str, Any]:
        """Search captured events by method, body text, headers, type, or date.

        Use when the user asks to find POSTs, a keyword, or only emails/DNS.
        query uses webhook.site search syntax: 'method:POST', 'content:verify',
        'headers.user-agent:curl', 'type:web AND method:POST', '-method:GET'
        (exclude), '_exists_:custom_action_errors', 'note:todo*',
        'country_code:DE', 'created_at:[now-1h TO now]'. Dates are
        'yyyy-MM-dd HH:mm:ss' or expressions like now-7d. Returns pagination
        and next_since (pass back as since for only newer matches).
        """

        def _op(webhook_token: str) -> Awaitable[ToolResult]:
            validate_page(page, limit)
            filters = SearchFilters(
                request_type=request_type,
                query=query,
                date_from=date_from,
                date_to=date_to,
                sorting=sorting,
                limit=limit,
                page=page,
                since=since,
            )
            return _app(ctx).requests.search(webhook_token, filters)

        return await _execute(_op, ctx, webhook_token)

    @mcp.tool(annotations=RO)
    async def get_request(
        webhook_token: Token,
        ctx: Context[AppContext],
        request_id: str | None = None,
        raw: bool = False,
    ) -> dict[str, Any]:
        """Return one captured event: the newest by default, or request_id.

        Set raw=true to also get the untouched body (raw_body). Use for a quick
        peek; prefer wait_for_email after a sign-up, or get_webhook_requests to
        see history.
        """

        def _op(webhook_token: str) -> Awaitable[ToolResult]:
            return _app(ctx).requests.get_request(webhook_token, request_id=request_id, raw=raw)

        return await _execute(_op, ctx, webhook_token)

    @mcp.tool(annotations=WRITE_IDEMPOTENT)
    async def update_request(
        webhook_token: Token,
        request_id: str,
        ctx: Context[AppContext],
        note: JsonText = None,
        response_content: JsonText = None,
        response_status: int | None = None,
        response_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Attach a note to a captured request, or set its dynamic response.

        response_* call the Set Response API; it only reaches the caller while
        the request is still held (token listen > 0 with a socket listener; see
        respond_to_next_request, which does the whole thing). For canned replies
        use configure_webhook or a modify_response custom action instead.
        """

        def _op(webhook_token: str) -> Awaitable[ToolResult]:
            note_text = _text(note)
            body = _text(response_content)
            if note_text is not None:
                validate_note(note_text)
            if response_status is not None:
                validate_http_status_code(response_status)
            if note_text is None and body is None and response_status is None and response_headers is None:
                raise ValidationError("Pass note and/or response_content / response_status / response_headers")
            return _app(ctx).requests.update_request(
                webhook_token,
                request_id,
                note=note_text,
                response_content=body,
                response_status=response_status,
                response_headers=response_headers,
            )

        return await _execute(_op, ctx, webhook_token)

    @mcp.tool(annotations=RO)
    async def download_request_file(
        webhook_token: Token,
        request_id: str,
        file_id: str,
        ctx: Context[AppContext],
        max_bytes: int = 5_000_000,
    ) -> dict[str, Any]:
        """Download an uploaded file or email attachment (base64) by its file_id.

        file_id comes from the attachments list on a request or email.
        """

        def _op(webhook_token: str) -> Awaitable[ToolResult]:
            validate_positive_int(max_bytes, "max_bytes", min_val=1, max_val=50_000_000)
            return _app(ctx).requests.download_file(webhook_token, request_id, file_id, max_bytes=max_bytes)

        return await _execute(_op, ctx, webhook_token)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def delete_request(
        webhook_token: Token,
        request_id: str,
        ctx: Context[AppContext],
    ) -> dict[str, Any]:
        """Delete one captured HTTP, email, or DNS event by request id."""

        def _op(webhook_token: str) -> Awaitable[ToolResult]:
            return _app(ctx).requests.delete_one(webhook_token, request_id)

        return await _execute(_op, ctx, webhook_token)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def delete_all_requests(
        webhook_token: Token,
        ctx: Context[AppContext],
        date_from: str | None = None,
        date_to: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Clear captured events on a webhook, optionally by date or search query.

        Use to reset an inbox before a new sign-up or test run. date_to='now-7d'
        deletes everything older than a week.
        """

        def _op(webhook_token: str) -> Awaitable[ToolResult]:
            filters = None
            if any(value is not None for value in (date_from, date_to, query)):
                filters = DeleteFilters(date_from=date_from, date_to=date_to, query=query)
            return _app(ctx).requests.delete_all(webhook_token, filters)

        return await _execute(_op, ctx, webhook_token)

    @mcp.tool(annotations=RO)
    async def export_webhook_data(
        webhook_token: Token,
        ctx: Context[AppContext],
        format: ExportFormat = "json",
        limit: int = 100,
        query: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sorting: Literal["newest", "oldest"] = "newest",
    ) -> dict[str, Any]:
        """Full dump of captured events with HTML and untruncated bodies, as JSON or CSV.

        Use when list/wait tools omitted HTML or truncated a body. json pages
        through up to limit events; csv returns the account's CSV export
        (paid plans, 3 calls per minute). Filters match search_requests.
        """

        def _op(webhook_token: str) -> Awaitable[ToolResult]:
            validate_positive_int(limit, "limit", min_val=1, max_val=10000)
            return _app(ctx).requests.export_requests(
                webhook_token,
                limit=limit,
                format=format,
                query=query,
                date_from=date_from,
                date_to=date_to,
                sorting=sorting,
            )

        return await _execute(_op, ctx, webhook_token)

    # --- waiting ------------------------------------------------------------

    @mcp.tool(annotations=RO)
    async def wait_for_request(
        webhook_token: Token,
        ctx: Context[AppContext],
        timeout_seconds: int = 60,
        request_type: RequestType | None = None,
        return_existing: bool = False,
    ) -> dict[str, Any]:
        """Wait until a new HTTP (or DNS) callback hits the webhook (1-120s).

        Use after giving a site the webhook URL. Listens on webhook.site's
        socket and falls back to polling. Bodies are truncated and HTML is
        omitted; use export_webhook_data for the full dump. For verification /
        magic-link / password-reset mail, use wait_for_email instead. Set
        return_existing=true if the request may already be there.
        """

        def _op(webhook_token: str) -> Awaitable[ToolResult]:
            return _app(ctx).requests.wait_for_request(
                webhook_token,
                timeout_seconds=timeout_seconds,
                request_type=request_type,
                return_existing=return_existing,
            )

        return await _execute(_op, ctx, webhook_token)

    @mcp.tool(annotations=RO)
    async def wait_for_email(
        webhook_token: Token,
        ctx: Context[AppContext],
        timeout_seconds: int = 60,
        extract_links: bool = True,
        return_existing: bool = False,
    ) -> dict[str, Any]:
        """Wait for a sign-up, verify, magic-link, or password-reset email (1-120s).

        Call this after the user (or you) submitted {token}@emailhook.site
        on a website. Returns subject, sender, spam/DKIM checks, a truncated
        text preview, attachments, extracted confirm / reset / login URLs, and
        verification_codes (OTP). Next: follow_email_link, or type the code.
        HTML is omitted; use export_webhook_data for the full message. Set
        return_existing=true if the email already arrived. If there is no token
        yet, create_webhook first.
        """

        def _op(webhook_token: str) -> Awaitable[ToolResult]:
            return _app(ctx).requests.wait_for_email(
                webhook_token,
                timeout_seconds=timeout_seconds,
                extract_links=extract_links,
                return_existing=return_existing,
            )

        return await _execute(_op, ctx, webhook_token)

    @mcp.tool(annotations=WRITE)
    async def respond_to_next_request(
        webhook_token: Token,
        ctx: Context[AppContext],
        status: int = 200,
        content: JsonText = "",
        headers: dict[str, str] | None = None,
        timeout_seconds: int = 60,
        listen_seconds: int = 10,
    ) -> dict[str, Any]:
        """Hold the next request that hits the webhook and answer it with your own status, headers and body.

        Turns the URL into a live mock for one request: the caller waits (up to
        listen_seconds, max 10) while this tool sets the reply the moment the
        request arrives over the socket. Use to test a client's retry / error
        handling ("answer the next call with 500") or to fake an API response
        on demand; returns the captured request. For a fixed canned reply use
        configure_webhook instead.
        """

        def _op(webhook_token: str) -> Awaitable[ToolResult]:
            validate_http_status_code(status)
            body = _text(content) or ""
            return _app(ctx).requests.respond_to_next_request(
                webhook_token,
                status=status,
                content=body,
                headers=headers,
                timeout_seconds=timeout_seconds,
                listen_seconds=listen_seconds,
            )

        return await _execute(_op, ctx, webhook_token)

    @mcp.tool(annotations=FOLLOW)
    async def follow_email_link(
        webhook_token: Token,
        ctx: Context[AppContext],
        request_id: str | None = None,
        url: str | None = None,
    ) -> dict[str, Any]:
        """Open the verify / magic-link / reset URL from a captured sign-up email.

        Use after wait_for_email. Opens the best-ranked auth link; pass
        request_id (the email's uuid) to pick a specific email, or url to open
        another link from that email. Only follows http(s) links already in the
        inbox, to public hosts unless the server's FOLLOW_EMAIL_LINK_ALLOW_HOSTS
        allows more. Returns status, final URL, page preview, the ranked
        auth_links, and blocked_redirect if a redirect was refused after the
        link itself answered. For OTP codes, read verification_codes from
        wait_for_email.
        """

        def _op(webhook_token: str) -> Awaitable[ToolResult]:
            return _app(ctx).requests.follow_email_link(
                webhook_token,
                request_id=request_id,
                url=url,
            )

        return await _execute(_op, ctx, webhook_token)

    # --- account resources --------------------------------------------------

    @mcp.tool(annotations=FAMILY)
    async def manage_custom_actions(
        action: ActionAction,
        ctx: Context[AppContext],
        webhook_token: str | None = None,
        action_id: str | None = None,
        request_id: str | None = None,
        type: str | None = None,
        parameters: dict[str, Any] | None = None,
        order: int | None = None,
        disabled: bool | None = None,
        queue: bool | None = None,
        delay: int | None = None,
        condition: str | None = None,
        queue_id: int | None = None,
        name: str | None = None,
        search: str | None = None,
        error_notifications: bool = False,
    ) -> dict[str, Any]:
        """Manage the Custom Actions webhook.site runs on every request or email a token receives.

        action: types (reference of all 63 action types; pass type= for one
        type's parameters, live-verified status and example) | variables
        ($request.*$ variables and modifiers) | script_reference (every
        WebhookScript function with its signature, for type=script) | list |
        create | update | delete | test | execute. create/update take type
        (modify_response, http, script, javascript, send_email,
        extract_jsonpath, conditions, rate_limit, log, set_variable, mock,
        ...) with parameters, order, and optionally name (label), queue/delay/
        condition (id of a conditions action) and queue_id (a Queue Profile
        from manage_queues). test dry-runs the given action against request_id
        without changing saved actions; execute re-runs all saved actions on
        request_id. Actions also fire on incoming emails, so guard
        email-sending actions with a condition on $request.type$. Never point
        http/send_request at a webhook.site URL (recursion is disabled).
        """

        def _op(webhook_token: str | None) -> Awaitable[ToolResult] | ToolResult:
            if action == "types":
                if type:
                    return ToolResult(success=True, message=f"Reference for '{type}'", data=action_types.describe(type))
                catalogue = [action_types.summarise(name, entry) for name, entry in action_types.all_types().items()]
                return ToolResult(
                    success=True,
                    message=f"{len(catalogue)} action types (verified {action_types.load().get('verified_at')})",
                    data={"types": catalogue},
                )
            if action == "script_reference":
                reference = webhookscript.reference(search=search)
                return ToolResult(
                    success=True,
                    message=f"{reference['count']} WebhookScript functions (names verified live {reference['verified_at']})",
                    data=reference,
                )
            if action == "variables":

                async def _variables() -> ToolResult:
                    reference = action_types.variables_reference()
                    reference["live_base_variable_names"] = await _app(ctx).account.live_variables()
                    return ToolResult(success=True, message="Variable reference", data=reference)

                return _variables()
            _require(webhook_token, "webhook_token", action)
            svc = _app(ctx).actions
            if action == "list":
                return svc.list(webhook_token)
            if action in ("create", "test"):
                action_types.validate_action(_require(type, "type", action), parameters)
            elif action == "update" and type is not None:
                action_types.validate_action(type, parameters, partial=True)
            if action == "create":
                return svc.create(
                    webhook_token,
                    type=_require(type, "type", action),
                    parameters=parameters,
                    order=order,
                    disabled=disabled,
                    queue=queue,
                    delay=delay,
                    condition=condition,
                    queue_id=queue_id,
                    name=name,
                )
            if action == "update":
                return svc.update(
                    webhook_token,
                    _require(action_id, "action_id", action),
                    type=type,
                    parameters=parameters,
                    order=order,
                    disabled=disabled,
                    queue=queue,
                    delay=delay,
                    condition=condition,
                    queue_id=queue_id,
                    name=name,
                )
            if action == "delete":
                return svc.delete(webhook_token, _require(action_id, "action_id", action))
            if action == "test":
                return svc.test(
                    webhook_token,
                    type=_require(type, "type", action),
                    parameters=parameters,
                    order=order,
                    request_id=request_id,
                    action_id=action_id,
                )
            return svc.execute(
                webhook_token,
                _require(request_id, "request_id", action),
                error_notifications=error_notifications,
            )

        return await _execute(_op, ctx, webhook_token)

    @mcp.tool(annotations=FAMILY)
    async def manage_schedules(
        action: ScheduleAction,
        ctx: Context[AppContext],
        schedule_id: int | None = None,
        name: str | None = None,
        interval: str | None = None,
        cron: str | None = None,
        request_url: str | None = None,
        request_method: str | None = None,
        request_body: JsonText = None,
        request_headers: str | None = None,
        timeout: int | None = None,
        require_body: str | None = None,
        require_status_min: int | None = None,
        require_status_max: int | None = None,
        require_cert_expiry: int | None = None,
        sorting: Literal["newest", "oldest"] = "newest",
        page: int = 1,
    ) -> dict[str, Any]:
        """Manage Schedules: webhook.site calls request_url on an interval (needs API key).

        action: list | get | create | update | delete | run | logs. interval is
        monthly, weekly, daily, hourly, 10-minute, 5-minute, 1-minute or cron
        (then set cron, e.g. '*/5 * * * *'). request_headers are newline
        separated. require_* raise an error notification when the response does
        not match; require_cert_expiry alerts when the HTTPS certificate expires
        in fewer than that many days. Use for uptime checks or periodic cleanup
        calls (e.g. DELETE .../token/{id}/request?date_to=now-7d with Api-Key).
        """

        def _op() -> Awaitable[ToolResult]:
            svc = _app(ctx).schedules
            fields = {
                "name": name,
                "interval": interval,
                "cron": cron,
                "request_url": request_url,
                "request_method": request_method,
                "request_body": _text(request_body),
                "request_headers": request_headers,
                "timeout": timeout,
                "require_body": require_body,
                "require_status_min": require_status_min,
                "require_status_max": require_status_max,
                "require_cert_expiry": require_cert_expiry,
            }
            if timeout is not None:
                validate_positive_int(timeout, "timeout", min_val=1, max_val=30)
            if action == "list":
                validate_page(page)
                return svc.list(page=page)
            if action == "create":
                _require(name, "name", action)
                _require(interval, "interval", action)
                _require(request_url, "request_url", action)
                return svc.create(**fields)
            sid = _require_id(schedule_id, "schedule_id", action)
            if action == "get":
                return svc.get(sid)
            if action == "update":
                return svc.update(sid, **fields)
            if action == "delete":
                return svc.delete(sid)
            if action == "run":
                return svc.run_now(sid)
            validate_page(page)
            return svc.logs(sid, sorting=sorting, page=page)

        return await _execute(_op)

    @mcp.tool(annotations=FAMILY)
    async def manage_global_variables(
        action: CrudAction,
        ctx: Context[AppContext],
        variable_id: int | None = None,
        name: str | None = None,
        value: JsonText = None,
        search: str | None = None,
        page: int = 1,
    ) -> dict[str, Any]:
        """Manage Global Variables shared by all URLs, usable as $name$ in Custom Actions and Schedules.

        action: list | create | update | delete. Needs API key.
        """

        def _op() -> Awaitable[ToolResult]:
            svc = _app(ctx).account
            text = _text(value)
            if action == "list":
                validate_page(page)
                return svc.list_variables(search=search, page=page)
            if action == "create":
                return svc.create_variable(_require(name, "name", action), _require(text, "value", action))
            vid = _require_id(variable_id, "variable_id", action)
            if action == "update":
                return svc.update_variable(vid, name=name, value=text)
            return svc.delete_variable(vid)

        return await _execute(_op)

    @mcp.tool(annotations=FAMILY)
    async def manage_groups(
        action: CrudAction,
        ctx: Context[AppContext],
        group_id: int | None = None,
        name: str | None = None,
        page: int = 1,
    ) -> dict[str, Any]:
        """Manage Groups that organise the account's webhooks (needs API key).

        action: list | create | update | delete. Assign a token to a group with
        configure_webhook(group_id=...).
        """

        def _op() -> Awaitable[ToolResult]:
            svc = _app(ctx).account
            if action == "list":
                validate_page(page)
                return svc.list_groups(page=page)
            if action == "create":
                return svc.create_group(_require(name, "name", action))
            gid = _require_id(group_id, "group_id", action)
            if action == "update":
                return svc.update_group(gid, _require(name, "name", action))
            return svc.delete_group(gid)

        return await _execute(_op)

    @mcp.tool(annotations=FAMILY)
    async def manage_queues(
        action: CrudAction,
        ctx: Context[AppContext],
        queue_id: int | None = None,
        name: str | None = None,
        amount: int | None = None,
        duration: int | None = None,
        expiry: int | None = None,
        delay: int | None = None,
        group_id: int | None = None,
        page: int = 1,
    ) -> dict[str, Any]:
        """Manage Queue Profiles that throttle queued Custom Actions (needs API key).

        action: list | create | update | delete. A profile allows `amount` jobs
        every `duration` seconds, drops jobs not run within `expiry` seconds,
        and waits `delay` seconds before the first run. Attach it to an action
        with manage_custom_actions(queue=true, queue_id=...).
        """

        def _op() -> Awaitable[ToolResult]:
            svc = _app(ctx).account
            for value, label in ((amount, "amount"), (duration, "duration"), (expiry, "expiry")):
                if value is not None:
                    validate_positive_int(value, label, min_val=1)
            if delay is not None:
                validate_positive_int(delay, "delay", min_val=0)
            if action == "list":
                validate_page(page)
                return svc.list_queues(page=page)
            if action == "create":
                return svc.create_queue(
                    _require(name, "name", action),
                    _require(amount, "amount", action),
                    _require(duration, "duration", action),
                    _require(expiry, "expiry", action),
                    delay=delay or 0,
                    group_id=group_id,
                )
            qid = _require_id(queue_id, "queue_id", action)
            if action == "update":
                return svc.update_queue(qid, name=name, amount=amount, duration=duration, expiry=expiry, delay=delay, group_id=group_id)
            return svc.delete_queue(qid)

        return await _execute(_op)

    @mcp.tool(annotations=FAMILY)
    async def manage_templates(
        action: CrudAction,
        ctx: Context[AppContext],
        template_id: int | None = None,
        name: str | None = None,
        actions: list[dict[str, Any]] | None = None,
        variables: list[dict[str, Any]] | None = None,
        page: int = 1,
    ) -> dict[str, Any]:
        """Manage Templates: reusable sets of Custom Actions plus predefined variables (needs API key).

        action: list | create | update | delete. actions is a list of action
        objects (type, order, parameters...); variables is a list of
        {name, value}. Include a template in a token with a 'template' action.
        """

        def _op() -> Awaitable[ToolResult]:
            svc = _app(ctx).account
            if action == "list":
                validate_page(page)
                return svc.list_templates(page=page)
            if action == "create":
                return svc.create_template(_require(name, "name", action), actions=actions, variables=variables)
            tid = _require_id(template_id, "template_id", action)
            if action == "update":
                return svc.update_template(tid, name=name, actions=actions, variables=variables)
            return svc.delete_template(tid)

        return await _execute(_op)

    @mcp.tool(annotations=FAMILY)
    async def manage_databases(
        action: DatabaseAction,
        ctx: Context[AppContext],
        database_id: str | None = None,
        name: str | None = None,
        plan: Literal["db-s", "db-m", "db-l"] | None = None,
        group_id: int | None = None,
        query: str | None = None,
        params: list[Any] | dict[str, Any] | None = None,
        page: int = 1,
    ) -> dict[str, Any]:
        """Manage webhook.site Databases and run SQL against them (needs API key).

        action: list | create | update | delete | query. create needs name and
        plan. query runs SQL with optional positional (?) or named (:name)
        params and returns up to 1000 rows.
        """

        def _op() -> Awaitable[ToolResult]:
            svc = _app(ctx).databases
            if action == "list":
                validate_page(page)
                return svc.list(page=page)
            if action == "create":
                return svc.create(_require(name, "name", action), _require(plan, "plan", action), group_id=group_id)
            did = str(_require(database_id, "database_id", action))
            if action == "update":
                return svc.update(did, name=name, group_id=group_id)
            if action == "delete":
                return svc.delete(did)
            return svc.query(did, _require(query, "query", action), params=params)

        return await _execute(_op)

    @mcp.tool(annotations=FAMILY)
    async def manage_users(
        action: UserAction,
        ctx: Context[AppContext],
        user_id: int | None = None,
        name: str | None = None,
        email: str | None = None,
        user_type_id: int | None = None,
        role_id: int | None = None,
        page: int = 1,
    ) -> dict[str, Any]:
        """Manage team users on an Enterprise account (needs an administrator API key).

        action: list | invite | update | delete. user_type_id: 100 admin, 200
        member, 300 viewer.
        """

        def _op() -> Awaitable[ToolResult]:
            svc = _app(ctx).account
            if action == "list":
                validate_page(page)
                return svc.list_users(page=page)
            if action == "invite":
                return svc.invite_user(
                    _require(name, "name", action),
                    _require(email, "email", action),
                    _require(user_type_id, "user_type_id", action),
                    role_id=role_id,
                )
            uid = _require_id(user_id, "user_id", action)
            if action == "update":
                return svc.update_user(uid, name=name, email=email, user_type_id=user_type_id, role_id=role_id)
            return svc.delete_user(uid)

        return await _execute(_op)

    # --- security -------------------------------------------------------------

    @mcp.tool(annotations=RO)
    async def generate_oob_payloads(
        webhook_token: Token,
        kind: PayloadKind,
        ctx: Context[AppContext],
        identifier: str | None = None,
        include_dns: bool = True,
        include_ip: bool = True,
        include_cookies: bool = True,
        include_dom: bool = True,
        canary_type: CanaryType = "url",
    ) -> dict[str, Any]:
        """Build authorized out-of-band payloads that ping this webhook: SSRF URLs, XSS callbacks, or canary tokens.

        Use only on systems you are allowed to test — not for sign-up email.
        kind='ssrf' (include_dns/include_ip), 'xss' (include_cookies/include_dom),
        'canary' (canary_type url|dns|email: a tripwire, not an inbox). Confirm
        hits with check_for_callbacks.
        """

        def _op(webhook_token: str) -> ToolResult:
            return _app(ctx).bounty.generate_oob_payloads(
                webhook_token,
                kind,
                identifier=identifier,
                include_dns=include_dns,
                include_ip=include_ip,
                include_cookies=include_cookies,
                include_dom=include_dom,
                canary_type=canary_type,
            )

        return await _execute(_op, ctx, webhook_token)

    @mcp.tool(annotations=RO)
    async def check_for_callbacks(
        webhook_token: Token,
        ctx: Context[AppContext],
        since_minutes: int = 60,
        identifier: str | None = None,
    ) -> dict[str, Any]:
        """See if SSRF, XSS, or canary callbacks arrived in the last N minutes.

        Use after generate_oob_payloads. For a website verification email, use
        wait_for_email.
        """

        def _op(webhook_token: str) -> Awaitable[ToolResult]:
            return _app(ctx).bounty.check_for_callbacks(
                webhook_token,
                since_minutes=since_minutes,
                identifier=identifier,
            )

        return await _execute(_op, ctx, webhook_token)

    @mcp.tool(annotations=RO)
    async def extract_links_from_request(
        webhook_token: Token,
        ctx: Context[AppContext],
        request_id: str | None = None,
        filter_domain: str | None = None,
    ) -> dict[str, Any]:
        """Pull confirm, reset, magic-link, and other URLs from a captured email or HTTP body.

        Use after wait_for_email or get_webhook_requests when the user needs
        the verification / login / password-reset link or OTP. Defaults to the
        latest event. wait_for_email already extracts links and codes.
        """

        def _op(webhook_token: str) -> Awaitable[ToolResult]:
            return _app(ctx).bounty.extract_links_from_request(
                webhook_token,
                request_id=request_id,
                filter_domain=filter_domain,
            )

        return await _execute(_op, ctx, webhook_token)

    # --- send -----------------------------------------------------------------

    @mcp.tool(annotations=WRITE)
    async def send_requests(
        webhook_token: Token,
        ctx: Context[AppContext],
        data: dict[str, Any] | None = None,
        payloads: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
        method: str = "POST",
        delay_ms: int = 0,
    ) -> dict[str, Any]:
        """Send one JSON body (data) or several (payloads) to the webhook URL to test capture.

        Use when the user wants to send sample payloads or load-test, not when
        they are waiting for a real site or email. Any HTTP method; delay_ms
        spaces out multiple payloads.
        """

        def _op(webhook_token: str) -> Awaitable[ToolResult]:
            bodies = list(payloads or [])
            if data is not None:
                bodies.insert(0, data)
            if not bodies:
                raise ValidationError("Pass data (one body) or payloads (a list of bodies)")
            validate_positive_int(delay_ms, "delay_ms", min_val=0, max_val=60000)
            if not method.isalpha():
                raise ValidationError("method must be an HTTP method name such as POST")
            return _app(ctx).requests.send_multiple(
                webhook_token,
                payloads=bodies,
                delay_ms=delay_ms,
                headers=headers,
                method=method,
            )

        return await _execute(_op, ctx, webhook_token)
