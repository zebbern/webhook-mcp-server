"""
HTTP client utilities for webhook.site API interactions.

Provides a centralized, async HTTP client with proper error handling,
timeout configuration, and consistent header management.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import httpx

# API Configuration
WEBHOOK_SITE_API = "https://webhook.site"
DEFAULT_TIMEOUT = 30.0
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}


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
        
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers=headers,
        )
        return self
    
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
    
    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform GET request.
        
        Args:
            path: API path (e.g., "/token/abc123")
            params: Query parameters
            
        Returns:
            Parsed JSON response
            
        Raises:
            WebhookApiError: On HTTP or API errors
        """
        try:
            response = await self.client.get(
                self._build_url(path),
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise WebhookApiError(
                f"GET {path} failed: {e.response.status_code}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e
        except httpx.RequestError as e:
            raise WebhookApiError(f"Request failed: {str(e)}") from e
    
    async def post(
        self,
        path: str,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Perform POST request.
        
        Args:
            path: API path
            json_data: JSON body data
            headers: Additional headers
            
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
            )
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            raise WebhookApiError(
                f"POST {path} failed: {e.response.status_code}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e
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
            Parsed JSON response
            
        Raises:
            WebhookApiError: On HTTP or API errors
        """
        try:
            response = await self.client.put(
                self._build_url(path),
                json=json_data,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise WebhookApiError(
                f"PUT {path} failed: {e.response.status_code}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e
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
            return response.status_code
        except httpx.RequestError as e:
            raise WebhookApiError(f"DELETE request failed: {str(e)}") from e


@asynccontextmanager
async def get_http_client(
    api_key: str | None = None,
) -> AsyncGenerator[WebhookHttpClient, None]:
    """Context manager factory for HTTP client.
    
    Usage:
        async with get_http_client() as client:
            data = await client.get("/token/abc123")
    
    Args:
        api_key: Optional API key for authenticated requests
        
    Yields:
        Configured WebhookHttpClient instance
    """
    async with WebhookHttpClient(api_key=api_key) as client:
        yield client
