"""
HTTP client utilities for webhook.site API interactions.

Provides a centralized, async HTTP client with proper error handling,
timeout configuration, consistent header management, capped raw downloads
and a pagination helper for the Laravel-style list endpoints.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import httpx

from utils import recorder

# API Configuration
WEBHOOK_SITE_API = "https://webhook.site"
DEFAULT_TIMEOUT = 30.0
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}
PAGE_SIZE_MAX = 100
DEFAULT_MAX_PAGES = 20
DEFAULT_MAX_ITEMS = 1000
PAGE_DELAY_SECONDS = 0.3
RAW_MAX_BYTES = 5_000_000


class WebhookApiError(Exception):
    """Custom exception for webhook.site API errors.

    Args:
        message: Error description
        status_code: HTTP status code (if applicable)
        response_body: Raw response body (if available)
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


@dataclass
class RawResponse:
    """A capped, non-JSON response body (CSV export, raw request body, file download)."""

    content: bytes
    content_type: str
    status_code: int
    url: str
    truncated: bool = False

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


def api_error(verb: str, path: str, response: httpx.Response) -> WebhookApiError:
    """Build a WebhookApiError that carries webhook.site's own error text.

    The API answers validation failures with {"error": {"message", "validation": {...}}}
    or {field: [messages]}; surfacing that lets a caller fix the call.
    """
    detail = ""
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            detail = str(error.get("message") or "")
            validation = error.get("validation")
            if isinstance(validation, dict):
                detail += " " + "; ".join(f"{field}: {' '.join(map(str, msgs))}" for field, msgs in validation.items())
        elif isinstance(error, str):
            detail = error
        elif all(isinstance(value, list) for value in body.values()) and body:
            detail = "; ".join(f"{field}: {' '.join(map(str, msgs))}" for field, msgs in body.items())
        elif body.get("message"):
            detail = str(body["message"])
    if not detail and response.text:
        detail = response.text[:200].replace("\n", " ")
    message = f"{verb} {path} failed: {response.status_code}"
    if detail:
        message += f" ({detail.strip()})"
    return WebhookApiError(message, status_code=response.status_code, response_body=response.text)


def pagination_summary(page: dict[str, Any], *, pages_fetched: int, returned: int, truncated: bool) -> dict[str, Any]:
    """Normalise the paginator fields webhook.site returns (they differ per endpoint)."""
    last_page = page.get("last_page")
    current_page = page.get("current_page")
    is_last_page = page.get("is_last_page")
    if is_last_page is None:
        if page.get("next_page_url") is not None:
            is_last_page = False
        elif last_page is not None and current_page is not None:
            is_last_page = current_page >= last_page
        elif "next_page_url" in page:
            is_last_page = True
    return {
        "total": page.get("total"),
        "per_page": page.get("per_page"),
        "current_page": current_page,
        "last_page": last_page,
        "is_last_page": is_last_page,
        "pages_fetched": pages_fetched,
        "returned": returned,
        "truncated": truncated,
    }


class WebhookHttpClient:
    """Async HTTP client for webhook.site API.

    Provides methods for common HTTP operations with consistent
    error handling and configuration.

    Usage:
        async with WebhookHttpClient() as client:
            response = await client.get("/token/abc123")
    """

    def __init__(
        self,
        base_url: str = WEBHOOK_SITE_API,
        timeout: float = DEFAULT_TIMEOUT,
        api_key: str | None = None,
    ) -> None:
        """Initialize the HTTP client.

        Args:
            base_url: Base URL for API requests
            timeout: Request timeout in seconds
            api_key: Optional API key for authenticated requests
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> WebhookHttpClient:
        """Enter async context manager."""
        headers = DEFAULT_HEADERS.copy()
        if self.api_key:
            headers["Api-Key"] = self.api_key

        hooks: dict[str, list[Any]] = {}
        if recorder.active() is not None:
            hooks["response"] = [self._record_response]
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers=headers,
            event_hooks=hooks,
        )
        return self

    @staticmethod
    async def _record_response(response: httpx.Response) -> None:
        """Log the exchange for tests/recordings when WEBHOOK_MCP_RECORD is set."""
        active = recorder.active()
        if active is None:
            return
        await response.aread()
        request = response.request
        content_type = response.headers.get("content-type", "")
        try:
            body: Any = response.json()
            is_text = False
        except ValueError:
            body = response.text
            is_text = True
        try:
            await request.aread()  # streamed requests have not buffered their body yet
            raw = request.content
        except Exception:
            raw = b""
        try:
            sent: Any = json.loads(raw) if raw else None
        except ValueError:
            sent = raw.decode("utf-8", errors="replace")
        active.http(
            request.method,
            str(request.url.copy_with(query=None)),
            params=dict(request.url.params) or None,
            json_body=sent,
            status=response.status_code,
            content_type=content_type,
            response=body,
            response_is_text=is_text,
            location=response.headers.get("location"),
        )

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get the underlying httpx client."""
        if self._client is None:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")
        return self._client

    def _build_url(self, path: str) -> str:
        """Build full URL from path."""
        path = path.lstrip("/")
        return f"{self.base_url}/{path}"

    @staticmethod
    def _accept(accept: str | None) -> dict[str, str] | None:
        return {"Accept": accept} if accept else None

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        accept: str | None = None,
    ) -> dict[str, Any]:
        """Perform GET request.

        Args:
            path: API path (e.g., "/token/abc123")
            params: Query parameters
            accept: Override the Accept header for this call

        Returns:
            Parsed JSON response

        Raises:
            WebhookApiError: On HTTP or API errors
        """
        try:
            response = await self.client.get(
                self._build_url(path),
                params=params,
                headers=self._accept(accept),
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise api_error("GET", path, e.response) from e
        except httpx.RequestError as e:
            raise WebhookApiError(f"Request failed: {str(e)}") from e

    async def get_raw(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        accept: str | None = None,
        follow_redirects: bool = False,
        max_bytes: int = RAW_MAX_BYTES,
    ) -> RawResponse:
        """GET a non-JSON body (CSV, raw request content, file download), capped at max_bytes."""
        try:
            async with self.client.stream(
                "GET",
                self._build_url(path),
                params=params,
                headers=self._accept(accept),
                follow_redirects=follow_redirects,
            ) as response:
                response.raise_for_status()
                chunks: list[bytes] = []
                size = 0
                truncated = False
                async for chunk in response.aiter_bytes():
                    chunks.append(chunk)
                    size += len(chunk)
                    if size >= max_bytes:
                        truncated = size > max_bytes
                        break
                content = b"".join(chunks)
                if len(content) > max_bytes:
                    content = content[:max_bytes]
                    truncated = True
                return RawResponse(
                    content=content,
                    content_type=response.headers.get("content-type", ""),
                    status_code=response.status_code,
                    url=str(response.url),
                    truncated=truncated,
                )
        except httpx.HTTPStatusError as e:
            await e.response.aread()
            raise api_error("GET", path, e.response) from e
        except httpx.RequestError as e:
            raise WebhookApiError(f"Request failed: {str(e)}") from e

    async def paginate(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_items: int = DEFAULT_MAX_ITEMS,
        delay: float = PAGE_DELAY_SECONDS,
        accept: str | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Walk a paginated list endpoint and return (items, pagination summary).

        Stops on the endpoint's own last-page signal, or when max_items / max_pages
        is reached (then ``truncated`` is True). Sleeps ``delay`` between pages to
        stay inside webhook.site rate limits.
        """
        query = dict(params or {})
        query.setdefault("page", 1)
        items: list[dict[str, Any]] = []
        page: dict[str, Any] = {}
        pages_fetched = 0
        truncated = False
        while True:
            page = await self.get(path, params=query, accept=accept)
            pages_fetched += 1
            data = page.get("data") or []
            items.extend(data)
            summary = pagination_summary(page, pages_fetched=pages_fetched, returned=len(items), truncated=False)
            if not data or summary["is_last_page"] is not False:
                break
            if len(items) >= max_items or pages_fetched >= max_pages:
                truncated = True
                break
            query["page"] = int(query["page"]) + 1
            if delay:
                await asyncio.sleep(delay)
        if len(items) > max_items:
            items = items[:max_items]
            truncated = True
        return items, pagination_summary(page, pages_fetched=pages_fetched, returned=len(items), truncated=truncated)

    async def post(
        self,
        path: str,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        allow_redirect: bool = False,
    ) -> httpx.Response:
        """Perform POST request.

        Args:
            path: API path
            json_data: JSON body data
            headers: Additional headers
            params: Query parameters
            allow_redirect: Treat a 3xx answer as success (some web routes redirect)

        Returns:
            Full httpx Response object

        Raises:
            WebhookApiError: On HTTP or API errors
        """
        try:
            response = await self.client.post(
                self._build_url(path),
                json=json_data,
                headers=headers,
                params=params,
            )
            if allow_redirect and response.is_redirect:
                return response
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            raise api_error("POST", path, e.response) from e
        except httpx.RequestError as e:
            raise WebhookApiError(f"POST request failed: {str(e)}") from e

    async def put(
        self,
        path: str,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform PUT request.

        Args:
            path: API path
            json_data: JSON body data

        Returns:
            Parsed JSON response (empty dict when the body is not JSON)

        Raises:
            WebhookApiError: On HTTP or API errors
        """
        try:
            response = await self.client.put(
                self._build_url(path),
                json=json_data,
            )
            response.raise_for_status()
            try:
                return response.json()
            except ValueError:
                return {}
        except httpx.HTTPStatusError as e:
            raise api_error("PUT", path, e.response) from e
        except httpx.RequestError as e:
            raise WebhookApiError(f"PUT request failed: {str(e)}") from e

    async def delete(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> int:
        """Perform DELETE request.

        Args:
            path: API path
            params: Query parameters

        Returns:
            HTTP status code

        Raises:
            WebhookApiError: On HTTP or API errors
        """
        try:
            response = await self.client.delete(
                self._build_url(path),
                params=params,
            )
            response.raise_for_status()
            return response.status_code
        except httpx.HTTPStatusError as e:
            raise api_error("DELETE", path, e.response) from e
        except httpx.RequestError as e:
            raise WebhookApiError(f"DELETE request failed: {str(e)}") from e

    async def post_raw(
        self,
        url: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Perform POST request to an absolute URL (not using base_url)."""
        return await self.request_raw("POST", url, json=json, headers=headers)

    async def request_raw(
        self,
        method: str,
        url: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Send any HTTP method to an absolute URL, such as the capture URL of a token.

        The response is returned as-is (no raise_for_status): the token's configured
        status code is part of what the caller wants to see.

        Raises:
            WebhookApiError: On connection errors
        """
        try:
            return await self.client.request(
                method.upper(),
                url,
                json=json,
                headers=headers,
            )
        except httpx.RequestError as e:
            raise WebhookApiError(f"{method.upper()} request failed: {str(e)}") from e
