"""
Request service for managing webhook requests.

Handles retrieval, search, and deletion of requests
captured by webhook.site endpoints.
"""

from __future__ import annotations

import asyncio
import base64
import time
from contextlib import AsyncExitStack
from typing import Any, Callable

import httpx

from models.schemas import DeleteFilters, SearchFilters, ToolResult
from utils.email_extract import (
    combined_request_text,
    extract_auth_links,
    extract_html_title,
    extract_urls,
    extract_verification_codes,
    normalize_url,
    rank_auth_links,
)
from utils.http_client import (
    PAGE_SIZE_MAX,
    WEBHOOK_SITE_API,
    WebhookApiError,
    WebhookHttpClient,
    pagination_summary,
)
from utils.safe_url import (
    HostAllowList,
    PublicOnlyTransport,
    default_ssl_context,
    ensure_public_http_url,
    ensure_public_resolution,
    proxy_for_url,
)
from utils.realtime import SocketFactory, SocketWaiter
from utils.validation import ValidationError, validate_positive_int

# Constants for request handling
DEFAULT_REQUEST_LIMIT = 10
DEFAULT_TIMEOUT_SECONDS = 60
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 120
POLL_INTERVAL_SECONDS = 2.0
SOCKET_POLL_INTERVAL_SECONDS = 10.0
SOCKET_CONNECT_TIMEOUT_SECONDS = 5.0
BODY_PREVIEW_CHARS = 2000
_TRUNCATION_NOTE = "\n...[truncated; use export_webhook_data for the full body]"
FOLLOW_TIMEOUT_SECONDS = 15.0
FOLLOW_MAX_REDIRECTS = 5
FOLLOW_MAX_BYTES = 65536
# rank_auth_links score at which a link is a verify / confirm / magic step, not just a login page.
STRONG_AUTH_LINK_SCORE = 3
RAW_BODY_MAX_BYTES = 262144
EXPORT_MAX_ITEMS = 10000
LATEST_RETRY_SECONDS = 1.5
MAX_LISTEN_SECONDS = 10  # the API's cap on how long a request is held for Set Response
# Token settings a PUT resets when omitted (same list WebhookService merges).
TOKEN_SETTINGS_FOR_PUT = (
    "default_status", "default_content", "default_content_type", "timeout", "cors", "alias",
    "request_limit", "actions", "group_id", "description",
)


def _pagination(data: dict[str, Any], returned: int) -> dict[str, Any]:
    """Pagination summary for a single page of the requests list."""
    return pagination_summary(data, pages_fetched=1, returned=returned, truncated=False)


def _proxy_transport(proxy: str) -> httpx.AsyncHTTPTransport:
    """Transport for hops that an operator-configured HTTP(S)_PROXY carries."""
    return httpx.AsyncHTTPTransport(proxy=proxy, verify=default_ssl_context(), trust_env=False)


def preview_body(value: str | None, limit: int = BODY_PREVIEW_CHARS) -> str | None:
    """Return a short preview so list/wait tools do not dump huge bodies."""
    if value is None:
        return None
    if len(value) <= limit:
        return value
    return value[:limit] + _TRUNCATION_NOTE


class RequestService:
    """Service for webhook request operations.
    
    Provides business logic for:
    - Listing all requests
    - Searching requests with filters
    - Getting latest request
    - Deleting individual requests
    - Bulk deleting requests
    """
    
    def __init__(
        self,
        client: WebhookHttpClient,
        follow_allowlist: HostAllowList | None = None,
        socket_factory: SocketFactory | None = None,
    ) -> None:
        """Initialize service with HTTP client.

        Args:
            client: Configured WebhookHttpClient instance
            follow_allowlist: Operator-configured local / internal hosts that
                follow_email_link may open (FOLLOW_EMAIL_LINK_ALLOW_HOSTS)
            socket_factory: Builds the socket.io client used by the wait tools
                (test seam); None uses python-socketio when installed
        """
        self._client = client
        self._follow_allowlist = follow_allowlist or HostAllowList()
        self._socket_factory = socket_factory
    
    async def get_all(
        self,
        webhook_token: str,
        limit: int = DEFAULT_REQUEST_LIMIT,
        request_type: str | None = None,
        page: int = 1,
    ) -> ToolResult:
        """Get requests sent to a webhook, one page at a time.

        Args:
            webhook_token: The webhook UUID
            limit: Page size (max 100)
            request_type: Filter by type ('web', 'email', 'dns')
            page: Page number, 1-based

        Returns:
            ToolResult with the requests and a pagination summary
        """
        params: dict[str, Any] = {"per_page": limit, "page": page}
        if request_type:
            params["query"] = f"type:{request_type}"

        data = await self._client.get(
            f"/token/{webhook_token}/requests",
            params=params,
        )

        requests = [self._format_request(req) for req in data.get("data", [])]

        return ToolResult(
            success=True,
            message=f"Retrieved {len(requests)} requests",
            data={
                "total_requests": len(requests),
                "requests": requests,
                "pagination": _pagination(data, len(requests)),
            },
        )
    
    async def search(
        self,
        webhook_token: str,
        filters: SearchFilters,
    ) -> ToolResult:
        """Search requests with query filters.
        
        Args:
            webhook_token: The webhook UUID
            filters: SearchFilters with query, date range, etc.
            
        Returns:
            ToolResult with matching requests
        """
        data = await self._client.get(
            f"/token/{webhook_token}/requests",
            params=filters.to_params(),
        )
        
        requests = [self._format_request(req) for req in data.get("data", [])]

        return ToolResult(
            success=True,
            message=f"Found {len(requests)} matching requests",
            data={
                "query": filters.query,
                "total_found": len(requests),
                "requests": requests,
                "pagination": _pagination(data, len(requests)),
            },
        )

    async def get_request(
        self,
        webhook_token: str,
        request_id: str | None = None,
        raw: bool = False,
    ) -> ToolResult:
        """Get one captured request, the newest one by default.

        Args:
            webhook_token: The webhook UUID
            request_id: A request UUID; None means the latest request
            raw: Also return the untouched body (text, capped) from the /raw endpoint

        Returns:
            ToolResult with the request, or request=None when the token is empty
        """
        path = f"/token/{webhook_token}/request/{request_id or 'latest'}"
        try:
            data = await self._get_with_latest_retry(path, retry=request_id is None)
        except WebhookApiError as exc:
            if exc.status_code == 404 and request_id is None:
                return ToolResult(
                    success=True,
                    message="No requests found for this webhook",
                    data={"request": None},
                )
            raise

        payload: dict[str, Any] = {"request": self._format_request(data)}
        if raw:
            body = await self._client.get_raw(f"{path}/raw", accept="*/*", max_bytes=RAW_BODY_MAX_BYTES)
            payload["raw_body"] = body.text
            payload["raw_content_type"] = body.content_type
            payload["raw_truncated"] = body.truncated
        return ToolResult(
            success=True,
            message="Latest request retrieved" if request_id is None else "Request retrieved",
            data=payload,
        )

    async def _get_with_latest_retry(self, path: str, retry: bool) -> dict[str, Any]:
        """GET a request; /request/latest can 404 for a moment right after capture."""
        try:
            return await self._client.get(path)
        except WebhookApiError as exc:
            if not retry or exc.status_code != 404:
                raise
            await asyncio.sleep(LATEST_RETRY_SECONDS)
            return await self._client.get(path)

    async def update_request(
        self,
        webhook_token: str,
        request_id: str,
        note: str | None = None,
        response_content: str | None = None,
        response_status: int | None = None,
        response_headers: dict[str, str] | None = None,
    ) -> ToolResult:
        """Set a note on a request and/or answer it dynamically (tokens with listen > 0).

        The docs list these under /requests/{id}, but the live API only answers on
        the singular /request/{id} path; the documented path is kept as a fallback.
        """
        outcome: dict[str, Any] = {"request_id": request_id}
        if note is not None:
            note_paths = (
                f"/token/{webhook_token}/request/{request_id}",
                f"/token/{webhook_token}/requests/{request_id}",
            )
            last_error: WebhookApiError | None = None
            for path in note_paths:
                try:
                    await self._client.put(path, json_data={"note": note})
                    outcome["note"] = note
                    outcome["note_path"] = path
                    last_error = None
                    break
                except WebhookApiError as exc:
                    last_error = exc
                    if exc.status_code != 404:
                        break
            if last_error is not None:
                outcome["note_error"] = str(last_error)

        if response_content is not None or response_status is not None or response_headers is not None:
            payload: dict[str, Any] = {}
            if response_content is not None:
                payload["content"] = base64.b64encode(response_content.encode("utf-8")).decode("ascii")
            if response_status is not None:
                payload["status"] = response_status
            if response_headers is not None:
                payload["headers"] = response_headers
            result = await self._client.put(
                f"/token/{webhook_token}/request/{request_id}/response",
                json_data=payload,
            )
            # The API answers {"status": 3} when the reply reached a waiting caller and
            # {"status": 2} when nothing was waiting (verified live).
            outcome["response_api_status"] = result.get("status")
            outcome["response_delivered"] = result.get("status") == 3
            outcome["response_note"] = (
                "Delivered to the waiting caller."
                if result.get("status") == 3
                else "Nothing was waiting: a request is only held while the token has listen > 0 and a socket "
                "listener is subscribed. Use respond_to_next_request for that flow."
            )

        failed = "note_error" in outcome
        return ToolResult(
            success=not failed,
            message="Request updated" if not failed else f"Could not set note: {outcome['note_error']}",
            data=outcome,
        )

    async def download_file(
        self,
        webhook_token: str,
        request_id: str,
        file_id: str,
        max_bytes: int = 5_000_000,
    ) -> ToolResult:
        """Download an uploaded file or email attachment as base64."""
        body = await self._client.get_raw(
            f"/token/{webhook_token}/request/{request_id}/download/{file_id}",
            accept="*/*",
            follow_redirects=True,
            max_bytes=max_bytes,
        )
        return ToolResult(
            success=True,
            message=f"Downloaded {len(body.content)} bytes" + (" (truncated)" if body.truncated else ""),
            data={
                "request_id": request_id,
                "file_id": file_id,
                "content_type": body.content_type,
                "size": len(body.content),
                "truncated": body.truncated,
                "content_base64": base64.b64encode(body.content).decode("ascii"),
            },
        )
    
    async def delete_one(
        self,
        webhook_token: str,
        request_id: str,
    ) -> ToolResult:
        """Delete a specific request.
        
        Args:
            webhook_token: The webhook UUID
            request_id: The request UUID to delete
            
        Returns:
            ToolResult indicating success/failure
        """
        status_code = await self._client.delete(
            f"/token/{webhook_token}/request/{request_id}"
        )
        success = status_code in [200, 204]
        
        return ToolResult(
            success=success,
            message="Request deleted successfully" if success else "Failed to delete request",
            data={
                "request_id": request_id,
                "status_code": status_code,
            }
        )
    
    async def delete_all(
        self,
        webhook_token: str,
        filters: DeleteFilters | None = None,
    ) -> ToolResult:
        """Delete all requests, optionally filtered.
        
        Args:
            webhook_token: The webhook UUID
            filters: Optional DeleteFilters for date range/query
            
        Returns:
            ToolResult indicating success/failure
        """
        params = filters.to_params() if filters else {}
        
        status_code = await self._client.delete(
            f"/token/{webhook_token}/request",
            params=params if params else None,
        )
        success = status_code in [200, 204]
        
        filter_desc = ""
        if params:
            filter_desc = f" matching filters: {params}"
        
        return ToolResult(
            success=success,
            message=f"Requests deleted successfully{filter_desc}" if success else "Failed to delete requests",
            data={
                "filters_applied": params if params else "none (all requests)",
                "status_code": status_code,
            }
        )
    
    @staticmethod
    def _format_request(req: dict[str, Any]) -> dict[str, Any]:
        """Format a raw API request into clean output.
        
        Handles missing or None values gracefully to prevent crashes.
        
        Args:
            req: Raw request data from API
            
        Returns:
            Formatted request dictionary with safe defaults
        """
        content = req.get("content") if req.get("content") is not None else ""
        formatted = {
            "uuid": req.get("uuid", "unknown"),
            "type": req.get("type", "unknown"),
            "method": req.get("method", "UNKNOWN"),
            "content": preview_body(content) or "",
            "text_content": preview_body(req.get("text_content")),
            "headers": req.get("headers", {}),
            "query": req.get("query", {}),
            "url": req.get("url", ""),
            "ip": req.get("ip", "unknown"),
            "created_at": req.get("created_at", "unknown"),
        }
        if req.get("html_content"):
            formatted["html_omitted"] = True
        attachments = RequestService._attachments(req)
        if attachments:
            formatted["attachments"] = attachments
        return formatted

    @staticmethod
    def _attachments(req: dict[str, Any]) -> list[dict[str, Any]]:
        """Summarise uploaded files / email attachments; download with download_request_file."""
        files = req.get("files") or {}
        entries = files.items() if isinstance(files, dict) else enumerate(files)
        attachments: list[dict[str, Any]] = []
        for field, meta in entries:
            if not isinstance(meta, dict):
                continue
            attachments.append(
                {
                    "field": field,
                    "file_id": meta.get("id"),
                    "filename": meta.get("filename"),
                    "size": meta.get("size"),
                    "content_type": meta.get("content_type"),
                }
            )
        return attachments

    async def wait_for_request(
        self,
        webhook_token: str,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        request_type: str | None = None,
        return_existing: bool = False,
    ) -> ToolResult:
        """Wait for a new request, or optionally return one that already exists.

        Listens on webhook.site's socket when available and polls as a backstop.

        Args:
            webhook_token: The webhook UUID
            timeout_seconds: Maximum time to wait (1-120, default: 60)
            request_type: Filter by type ('web', 'email', 'dns'). None for any.
            return_existing: If True, return a matching existing request immediately.

        Returns:
            ToolResult with the received request or timeout message
        """
        validate_positive_int(
            timeout_seconds,
            "timeout_seconds",
            min_val=MIN_TIMEOUT_SECONDS,
            max_val=MAX_TIMEOUT_SECONDS,
        )

        def matches(req: dict[str, Any]) -> bool:
            return not request_type or req.get("type") == request_type

        def found(req: dict[str, Any], waited: bool, source: str) -> ToolResult:
            kind = req.get("type", "unknown")
            message = (
                f"Request received (type: {kind})"
                if waited
                else f"Request found (already received, type: {kind})"
            )
            return ToolResult(
                success=True,
                message=message,
                data={"request": self._format_request(req), "waited": waited, "source": source},
            )

        type_desc = f" of type '{request_type}'" if request_type else ""
        return await self._wait_for_new(
            webhook_token,
            timeout_seconds,
            matches,
            found,
            return_existing=return_existing,
            per_page=5,
            init_error="Failed to initialize polling",
            timeout_message=f"Timeout: No request{type_desc} received within {timeout_seconds} seconds",
            timeout_data={"timeout": True, "request": None},
        )

    async def _wait_for_new(
        self,
        webhook_token: str,
        timeout_seconds: int,
        matches: Callable[[dict[str, Any]], bool],
        found: Callable[[dict[str, Any], bool, str], ToolResult],
        *,
        return_existing: bool,
        per_page: int,
        init_error: str,
        timeout_message: str,
        timeout_data: dict[str, Any],
    ) -> ToolResult:
        """Shared wait loop: snapshot, socket events when connected, polling backstop."""
        list_path = f"/token/{webhook_token}/requests"
        list_params = {"per_page": per_page, "sorting": "newest"}
        try:
            initial = await self._client.get(list_path, params=list_params)
        except WebhookApiError as exc:
            return ToolResult(success=False, message=f"{init_error}: {exc}", data={"error": str(exc)})
        initial_requests = initial.get("data", [])
        if return_existing:
            for req in initial_requests:
                if matches(req):
                    return found(req, False, "existing")
        seen = {req.get("uuid") for req in initial_requests if req.get("uuid")}

        deadline = time.monotonic() + timeout_seconds
        waiter = SocketWaiter(webhook_token, self._client.api_key, factory=self._socket_factory)
        connected = await waiter.start(timeout=min(SOCKET_CONNECT_TIMEOUT_SECONDS, timeout_seconds))
        interval = SOCKET_POLL_INTERVAL_SECONDS if connected else POLL_INTERVAL_SECONDS
        last_poll = time.monotonic()
        retries = 0
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                if connected and not waiter.connected:
                    # The server closed the socket mid-wait: poll at the fast cadence instead.
                    connected = False
                    interval = POLL_INTERVAL_SECONDS
                if connected:
                    event = await waiter.next(timeout=min(interval, remaining))
                    if event is not None:
                        req = await self._resolve_socket_event(
                            webhook_token, event, seen, matches, list_path, list_params
                        )
                        if req is not None:
                            return found(req, True, "socket")
                        if time.monotonic() - last_poll < interval:
                            continue
                else:
                    await asyncio.sleep(min(interval, remaining))

                try:
                    data = await self._client.get(list_path, params=list_params)
                    retries = 0
                except WebhookApiError as exc:
                    retries += 1
                    if retries >= 3:
                        return ToolResult(
                            success=False,
                            message=f"API error during polling (after 3 retries): {exc}",
                            data={"error": str(exc)},
                        )
                    await asyncio.sleep(2**retries)
                    continue
                last_poll = time.monotonic()
                for req in data.get("data", []):
                    if req.get("uuid") in seen:
                        break
                    if matches(req):
                        return found(req, True, "poll")
        finally:
            await waiter.close()

        return ToolResult(success=False, message=timeout_message, data=timeout_data)

    async def _resolve_socket_event(
        self,
        webhook_token: str,
        event: dict[str, Any],
        seen: set[str],
        matches: Callable[[dict[str, Any]], bool],
        list_path: str,
        list_params: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Turn a socket payload into the full captured request, or None if it is not ours."""
        uuid = event.get("uuid") or (event.get("request") or {}).get("uuid")
        if uuid:
            if uuid in seen:
                return None
            seen.add(uuid)
            try:
                req = await self._get_with_latest_retry(f"/token/{webhook_token}/request/{uuid}", retry=True)
            except WebhookApiError:
                req = event if event.get("uuid") else None
            return req if req is not None and matches(req) else None
        try:
            data = await self._client.get(list_path, params=list_params)
        except WebhookApiError:
            return None
        for req in data.get("data", []):
            if req.get("uuid") in seen:
                break
            if matches(req):
                seen.add(req.get("uuid"))
                return req
        return None

    def _format_email(self, req: dict[str, Any], extract_links: bool) -> dict[str, Any]:
        """Format a captured email request."""
        email_data: dict[str, Any] = {
            "uuid": req.get("uuid"),
            "from": self._extract_header(req, "from"),
            "sender": req.get("sender"),
            "subject": self._extract_header(req, "subject"),
            "text_content": preview_body(req.get("text_content")),
            "created_at": req.get("created_at"),
        }
        if req.get("checks") is not None:
            email_data["checks"] = req.get("checks")
        if req.get("email_truncated"):
            email_data["email_truncated"] = True
        if req.get("html_content"):
            email_data["html_omitted"] = True
        attachments = self._attachments(req)
        if attachments:
            email_data["attachments"] = attachments
        body = combined_request_text(req)
        email_data["verification_codes"] = extract_verification_codes(body)
        links: list[str] = []
        if extract_links:
            links = extract_urls(body)
            email_data["auth_links"] = extract_auth_links(links, body)
        email_data["all_links"] = links
        return email_data

    async def wait_for_email(
        self,
        webhook_token: str,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        extract_links: bool = True,
        return_existing: bool = False,
    ) -> ToolResult:
        """Wait for a new email, or optionally return one that already exists.

        The email address format is: {token}@emailhook.site

        Args:
            webhook_token: The webhook UUID
            timeout_seconds: Maximum time to wait (1-120, default: 60)
            extract_links: If True, extract all URLs from the email body
            return_existing: If True, return an existing email immediately.

        Returns:
            ToolResult with the email content and extracted links
        """
        validate_positive_int(
            timeout_seconds,
            "timeout_seconds",
            min_val=MIN_TIMEOUT_SECONDS,
            max_val=MAX_TIMEOUT_SECONDS,
        )

        def matches(req: dict[str, Any]) -> bool:
            return req.get("type") == "email"

        def found(req: dict[str, Any], waited: bool, source: str) -> ToolResult:
            email_data = self._format_email(req, extract_links)
            message = (
                f"Email received: {email_data['subject']}"
                if waited
                else f"Email found (already received): {email_data['subject']}"
            )
            return ToolResult(
                success=True,
                message=message,
                data={"email": email_data, "waited": waited, "source": source},
            )

        return await self._wait_for_new(
            webhook_token,
            timeout_seconds,
            matches,
            found,
            return_existing=return_existing,
            per_page=10,
            init_error="Failed to initialize email polling",
            timeout_message=f"Timeout: No email received within {timeout_seconds} seconds",
            timeout_data={
                "timeout": True,
                "email": None,
                "email_address": f"{webhook_token}@emailhook.site",
            },
        )

    async def follow_email_link(
        self,
        webhook_token: str,
        request_id: str | None = None,
        url: str | None = None,
    ) -> ToolResult:
        """GET a verify / magic / reset link that already arrived in this inbox.

        Args:
            webhook_token: The webhook UUID
            request_id: Open a link from this specific email (the uuid from wait_for_email)
            url: Open this captured link instead of the best-ranked auth link
        """
        wanted = url.strip() if url else None
        request = await self._load_follow_request(webhook_token, request_id, wanted)
        if request is None:
            return ToolResult(
                success=False,
                message="No captured email found. Wait with wait_for_email first.",
            )

        body = combined_request_text(request)
        allowed = extract_urls(body)
        auth_links = extract_auth_links(allowed, body)
        if wanted:
            target = self._match_captured_url(wanted, allowed)
            if target is None:
                raise ValidationError(
                    "That URL was not found in the captured email. Only inbox links can be opened."
                )
        else:
            target = auth_links[0] if auth_links else None
            if not target:
                return ToolResult(
                    success=False,
                    message="No verify / magic / reset link in that email. Pass url= from all_links if you intend to open another captured link.",
                    data={"all_links": allowed, "request_id": request.get("uuid")},
                )

        context = {
            "request_id": request.get("uuid"),
            "opened_url": target,
            "auth_links": auth_links,
        }
        try:
            page = await self._fetch_captured_link(target)
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            return ToolResult(
                success=False,
                message=f"Failed to open email link: {exc}",
                data=context,
            )
        message = f"Opened email link ({page['status_code']})"
        blocked = page.get("blocked_redirect")
        if blocked:
            message += f"; did not follow the redirect to {blocked['url']}: {blocked['reason']}"
        return ToolResult(
            success=200 <= page["status_code"] < 400,
            message=message,
            data={**context, **page},
        )

    async def respond_to_next_request(
        self,
        webhook_token: str,
        status: int = 200,
        content: str = "",
        headers: dict[str, str] | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        listen_seconds: int = MAX_LISTEN_SECONDS,
    ) -> ToolResult:
        """Hold the next request and answer it with a chosen response, the way whcli forward does.

        Verified live: the API holds an incoming request for the token's `listen`
        seconds while a socket listener is subscribed, and PUT
        /request/{id}/response delivers the reply to the waiting caller
        (Set Response answers {"status": 3} when delivered, 2 when nothing was
        waiting). `listen` is only honoured through PUT, never on POST.
        """
        validate_positive_int(timeout_seconds, "timeout_seconds", min_val=MIN_TIMEOUT_SECONDS, max_val=MAX_TIMEOUT_SECONDS)
        validate_positive_int(listen_seconds, "listen_seconds", min_val=1, max_val=MAX_LISTEN_SECONDS)
        list_path = f"/token/{webhook_token}/requests"
        current = await self._client.get(f"/token/{webhook_token}")
        previous_listen = int(current.get("listen") or 0)
        seen = {req.get("uuid") for req in (await self._client.get(list_path, params={"per_page": 5, "sorting": "newest"})).get("data", [])}

        async def set_listen(value: int) -> None:
            merged = {key: current.get(key) for key in TOKEN_SETTINGS_FOR_PUT if current.get(key) is not None}
            await self._client.put(f"/token/{webhook_token}", json_data={**merged, "listen": value})

        if previous_listen < listen_seconds:
            await set_listen(listen_seconds)
        waiter = SocketWaiter(webhook_token, self._client.api_key, factory=self._socket_factory)
        connected = await waiter.start(timeout=min(SOCKET_CONNECT_TIMEOUT_SECONDS, timeout_seconds))
        deadline = time.monotonic() + timeout_seconds
        payload: dict[str, Any] = {
            "status": status,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "headers": headers or {},
        }
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return ToolResult(
                        success=False,
                        message=f"Timeout: no request arrived within {timeout_seconds} seconds",
                        data={"timeout": True, "request": None, "listened_via": "socket" if connected else "poll"},
                    )
                request_id: str | None = None
                if connected and waiter.connected:
                    event = await waiter.next(timeout=remaining)
                    if event is None:
                        continue
                    request_id = event.get("uuid") or (event.get("request") or {}).get("uuid")
                    if not request_id or request_id in seen:
                        continue
                else:
                    await asyncio.sleep(min(1.0, remaining))
                    data = await self._client.get(list_path, params={"per_page": 5, "sorting": "newest"})
                    for req in data.get("data", []):
                        if req.get("uuid") not in seen:
                            request_id = req.get("uuid")
                            break
                    if not request_id:
                        continue
                seen.add(request_id)
                answer = await self._client.put(f"/token/{webhook_token}/request/{request_id}/response", json_data=payload)
                delivered = answer.get("status") == 3
                try:
                    req = await self._get_with_latest_retry(f"/token/{webhook_token}/request/{request_id}", retry=True)
                except WebhookApiError:
                    req = {"uuid": request_id}
                return ToolResult(
                    success=delivered,
                    message=(
                        f"Answered the request with {status}"
                        if delivered
                        else "The request arrived but was no longer waiting when the response was set; use a longer listen_seconds"
                    ),
                    data={
                        "request": self._format_request(req),
                        "answered": delivered,
                        "set_response_status": answer.get("status"),
                        "responded_with": {"status": status, "headers": headers or {}, "content": content},
                        "listened_via": "socket" if connected else "poll",
                    },
                )
        finally:
            await waiter.close()
            if previous_listen < listen_seconds:
                try:
                    await set_listen(previous_listen)
                except WebhookApiError:
                    pass

    async def _load_follow_request(
        self,
        webhook_token: str,
        request_id: str | None,
        url: str | None = None,
    ) -> dict[str, Any] | None:
        """Pick the email to open a link from.

        Priority: an explicit request_id; else the newest email containing the
        requested url; else the newest email with a strong verify / confirm /
        magic link; else the newest email with any auth link; else the newest
        email.
        """
        if request_id:
            return await self._client.get(f"/token/{webhook_token}/request/{request_id}")

        data = await self._client.get(
            f"/token/{webhook_token}/requests",
            params={"per_page": 20, "sorting": "newest"},
        )
        emails = [req for req in data.get("data", []) if req.get("type") == "email"]
        if not emails:
            return None

        if url:
            for req in emails:
                if self._match_captured_url(url, extract_urls(combined_request_text(req))):
                    return req
            return emails[0]

        scored: list[tuple[int, dict[str, Any]]] = []
        for req in emails:
            body = combined_request_text(req)
            ranked = rank_auth_links(extract_urls(body), body)
            scored.append((ranked[0][0] if ranked else 0, req))
        for threshold in (STRONG_AUTH_LINK_SCORE, 1):
            for score, req in scored:
                if score >= threshold:
                    return req
        return emails[0]

    @staticmethod
    def _match_captured_url(wanted: str, allowed: list[str]) -> str | None:
        """Return the captured form of ``wanted`` (as given, or HTML-unescaped)."""
        for candidate in (wanted, normalize_url(wanted)):
            if candidate in allowed:
                return candidate
        return None

    async def _fetch_captured_link(self, url: str) -> dict[str, Any]:
        """GET a captured link, following at most FOLLOW_MAX_REDIRECTS redirects.

        Direct hops go through PublicOnlyTransport, which resolves each host
        once, rejects private addresses and connects to the vetted IP. When
        HTTP(S)_PROXY applies, the proxy makes the connection, so the target
        is vetted before the request instead. A redirect to a blocked address
        after a successful public hop is reported in ``blocked_redirect``
        rather than failing the call: the request that consumed the token
        already went through.
        """
        current = url
        history: list[dict[str, Any]] = []
        last: dict[str, Any] | None = None
        allowlist = self._follow_allowlist
        headers = {
            "User-Agent": "webhook-mcp-server follow_email_link",
            "Accept": "text/html,text/plain,*/*",
            # No compression: FOLLOW_MAX_BYTES then caps what is read off the wire.
            "Accept-Encoding": "identity",
        }
        clients: dict[str | None, httpx.AsyncClient] = {}

        async with AsyncExitStack() as stack:

            async def client_for(proxy: str | None) -> httpx.AsyncClient:
                if proxy not in clients:
                    transport = (
                        _proxy_transport(proxy) if proxy else PublicOnlyTransport(allowlist=allowlist)
                    )
                    clients[proxy] = await stack.enter_async_context(
                        httpx.AsyncClient(
                            transport=transport,
                            timeout=FOLLOW_TIMEOUT_SECONDS,
                            follow_redirects=False,
                            headers=headers,
                        )
                    )
                return clients[proxy]

            for _ in range(FOLLOW_MAX_REDIRECTS + 1):
                try:
                    ensure_public_http_url(current, allowlist)
                    proxy = proxy_for_url(current)
                    if proxy:
                        await ensure_public_resolution(current, allowlist, timeout=FOLLOW_TIMEOUT_SECONDS)
                    client = await client_for(proxy)
                    async with client.stream("GET", current) as response:
                        location = response.headers.get("location") if response.is_redirect else None
                        if location:
                            last = {"status_code": response.status_code, "final_url": str(response.url)}
                            history.append({"url": current, "status_code": response.status_code})
                            current = str(response.url.join(location))
                            continue
                        raw = await self._read_capped(response)
                        text = raw.decode(response.encoding or "utf-8", errors="replace")
                        return {
                            "status_code": response.status_code,
                            "final_url": str(response.url),
                            "title": extract_html_title(text),
                            "preview": preview_body(text) or "",
                            "redirects": history,
                        }
                except (ValidationError, httpx.InvalidURL) as exc:
                    # httpx raises InvalidURL while preparing the next hop of a
                    # redirect (for example Location: javascript:...).
                    reason = (
                        str(exc)
                        if isinstance(exc, ValidationError)
                        else f"The email link or its redirect target is not a valid http(s) URL: {exc}"
                    )
                    if last is None:
                        if isinstance(exc, ValidationError):
                            raise
                        raise ValidationError(reason) from exc
                    return {
                        **last,
                        "title": None,
                        "preview": "",
                        "redirects": history[:-1],
                        "blocked_redirect": {"url": current, "reason": reason},
                    }

        raise ValidationError(
            f"Too many redirects while opening the email link (gave up after {FOLLOW_MAX_REDIRECTS} at {current})"
        )

    @staticmethod
    async def _read_capped(response: httpx.Response, limit: int = FOLLOW_MAX_BYTES) -> bytes:
        """Read at most ``limit`` bytes of a streamed response body."""
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            chunks.append(chunk)
            size += len(chunk)
            if size >= limit:
                break
        return b"".join(chunks)[:limit]
    
    async def send_multiple(
        self,
        webhook_token: str,
        payloads: list[dict[str, Any]],
        delay_ms: int = 0,
        headers: dict[str, str] | None = None,
        method: str = "POST",
    ) -> ToolResult:
        """Send one or more requests to a webhook's capture URL.

        Useful for load testing or sending test payloads.

        Args:
            webhook_token: The webhook UUID
            payloads: List of JSON payloads to send
            delay_ms: Delay between requests in milliseconds (default: 0)
            headers: Extra headers for every request
            method: HTTP method (default POST)

        Returns:
            ToolResult with success/failure counts
        """
        results = []
        success_count = 0
        fail_count = 0
        
        for i, payload in enumerate(payloads):
            try:
                response = await self._client.request_raw(
                    method,
                    f"{WEBHOOK_SITE_API}/{webhook_token}",
                    json=payload,
                    headers=headers,
                )
                results.append({
                    "index": i,
                    "success": True,
                    "status_code": response.status_code
                })
                success_count += 1
            except Exception as e:
                results.append({
                    "index": i,
                    "success": False,
                    "error": str(e)
                })
                fail_count += 1
            
            # Add delay between requests if specified
            if delay_ms > 0 and i < len(payloads) - 1:
                await asyncio.sleep(delay_ms / 1000.0)
        
        return ToolResult(
            success=fail_count == 0,
            message=f"Sent {success_count}/{len(payloads)} requests successfully",
            data={
                "total": len(payloads),
                "success_count": success_count,
                "fail_count": fail_count,
                "results": results
            }
        )
    
    async def export_requests(
        self,
        webhook_token: str,
        limit: int = 100,
        format: str = "json",
        query: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sorting: str = "newest",
    ) -> ToolResult:
        """Export requests with full bodies as JSON (paged) or as the API's CSV file.

        Args:
            webhook_token: The webhook UUID
            limit: Maximum number of requests to export (up to 10000)
            format: 'json' walks the requests list; 'csv' uses /requests/export (paid plans)
            query, date_from, date_to: Same filters as search_requests
            sorting: 'newest' or 'oldest'

        Returns:
            ToolResult with exported data
        """
        filters: dict[str, Any] = {"sorting": sorting}
        if query:
            filters["query"] = query
        if date_from:
            filters["date_from"] = date_from
        if date_to:
            filters["date_to"] = date_to

        if format == "csv":
            body = await self._client.get_raw(
                f"/token/{webhook_token}/requests/export",
                params={**filters, "per_page": limit},
                accept="text/csv",
            )
            csv_text = body.text
            rows = max(csv_text.count("\n") - 1, 0) if csv_text.strip() else 0
            return ToolResult(
                success=True,
                message=f"Exported {rows} requests as CSV" + (" (truncated)" if body.truncated else ""),
                data={
                    "webhook_token": webhook_token,
                    "export_format": "csv",
                    "request_count": rows,
                    "truncated": body.truncated,
                    "csv": csv_text,
                },
            )

        items, pagination = await self._client.paginate(
            f"/token/{webhook_token}/requests",
            {**filters, "per_page": min(limit, PAGE_SIZE_MAX)},
            max_items=limit,
            max_pages=max(1, -(-limit // PAGE_SIZE_MAX)),
        )
        export_data = [
            {
                "uuid": req.get("uuid"),
                "type": req.get("type"),
                "method": req.get("method"),
                "url": req.get("url"),
                "ip": req.get("ip"),
                "hostname": req.get("hostname"),
                "headers": req.get("headers", {}),
                "query": req.get("query", {}),
                "content": req.get("content"),
                "text_content": req.get("text_content"),
                "html_content": req.get("html_content"),
                "sender": req.get("sender"),
                "checks": req.get("checks"),
                "files": req.get("files"),
                "created_at": req.get("created_at"),
                "user_agent": self._extract_header(req, "User-Agent"),
                "content_type": self._extract_header(req, "Content-Type"),
            }
            for req in items
        ]

        return ToolResult(
            success=True,
            message=f"Exported {len(export_data)} requests",
            data={
                "webhook_token": webhook_token,
                "export_format": "json",
                "request_count": len(export_data),
                "requests": export_data,
                "pagination": pagination,
            },
        )
    
    @staticmethod
    def _extract_header(req: dict[str, Any], header_name: str) -> str:
        """Extract a header value from a request."""
        headers = req.get("headers", {})
        if not headers:
            return "Unknown"
        value = headers.get(header_name, headers.get(header_name.title(), ["Unknown"]))
        if isinstance(value, list):
            return value[0] if value else "Unknown"
        return value or "Unknown"
