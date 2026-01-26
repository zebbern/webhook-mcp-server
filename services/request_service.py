"""
Request service for managing webhook requests.

Handles retrieval, search, and deletion of requests
captured by webhook.site endpoints.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from models.schemas import WebhookRequest, SearchFilters, DeleteFilters, ToolResult
from utils.http_client import WebhookHttpClient


class RequestService:
    """Service for webhook request operations.
    
    Provides business logic for:
    - Listing all requests
    - Searching requests with filters
    - Getting latest request
    - Deleting individual requests
    - Bulk deleting requests
    """
    
    def __init__(self, client: WebhookHttpClient) -> None:
        """Initialize service with HTTP client.
        
        Args:
            client: Configured WebhookHttpClient instance
        """
        self._client = client
    
    async def get_all(
        self,
        webhook_token: str,
        limit: int = 10,
        request_type: str | None = None,
    ) -> ToolResult:
        """Get all requests sent to a webhook.
        
        Args:
            webhook_token: The webhook UUID
            limit: Maximum number of requests to retrieve
            request_type: Filter by type ('web', 'email', 'dns')
            
        Returns:
            ToolResult with list of requests
        """
        params = {"per_page": limit}
        if request_type:
            params["query"] = f"type:{request_type}"
        
        data = await self._client.get(
            f"/token/{webhook_token}/requests",
            params=params,
        )
        
        requests_data = data.get("data", [])
        requests = [
            self._format_request(req)
            for req in requests_data
        ]
        
        return ToolResult(
            success=True,
            message=f"Retrieved {len(requests)} requests",
            data={
                "total_requests": len(requests),
                "requests": requests,
            }
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
        
        requests_data = data.get("data", [])
        requests = [
            self._format_request(req)
            for req in requests_data
        ]
        
        return ToolResult(
            success=True,
            message=f"Found {len(requests)} matching requests",
            data={
                "query": filters.query,
                "total_found": len(requests),
                "requests": requests,
            }
        )
    
    async def get_latest(self, webhook_token: str) -> ToolResult:
        """Get the most recent request to a webhook.
        
        Args:
            webhook_token: The webhook UUID
            
        Returns:
            ToolResult with latest request or None
        """
        data = await self._client.get(
            f"/token/{webhook_token}/requests",
            params={"per_page": 1},
        )
        
        requests_data = data.get("data", [])
        
        if not requests_data:
            return ToolResult(
                success=True,
                message="No requests found for this webhook",
                data={"request": None}
            )
        
        request = self._format_request(requests_data[0])
        
        return ToolResult(
            success=True,
            message="Latest request retrieved",
            data={"request": request}
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
        return {
            "uuid": req.get("uuid", "unknown"),
            "type": req.get("type", "unknown"),
            "method": req.get("method", "UNKNOWN"),
            "content": req.get("content") if req.get("content") is not None else "",
            "text_content": req.get("text_content"),
            "html_content": req.get("html_content"),
            "headers": req.get("headers", {}),
            "query": req.get("query", {}),
            "url": req.get("url", ""),
            "ip": req.get("ip", "unknown"),
            "created_at": req.get("created_at", "unknown"),
        }
    
    async def wait_for_request(
        self,
        webhook_token: str,
        timeout_seconds: int = 60,
        request_type: str | None = None,
    ) -> ToolResult:
        """Wait for a new HTTP request to be received by the webhook.
        
        Polls the webhook.site API until a new request is received.
        
        Args:
            webhook_token: The webhook UUID
            timeout_seconds: Maximum time to wait (default: 60)
            request_type: Filter by type ('web', 'email', 'dns'). None for any.
            
        Returns:
            ToolResult with the received request or timeout message
        """
        import time
        from utils.http_client import WebhookApiError
        
        start_time = time.time()
        poll_interval = 2.0  # Poll every 2 seconds
        max_retries = 3
        retry_count = 0
        
        # Get initial count of requests to detect new ones
        try:
            initial_data = await self._client.get(
                f"/token/{webhook_token}/requests",
                params={"per_page": 1, "sorting": "newest"},
            )
            initial_requests = initial_data.get("data", [])
            initial_newest_id = initial_requests[0].get("uuid") if initial_requests else None
        except WebhookApiError as e:
            return ToolResult(
                success=False,
                message=f"Failed to initialize polling: {e}",
                data={"error": str(e)}
            )
        
        while time.time() - start_time < timeout_seconds:
            await asyncio.sleep(poll_interval)
            
            try:
                # Check for new requests
                data = await self._client.get(
                    f"/token/{webhook_token}/requests",
                    params={"per_page": 5, "sorting": "newest"},
                )
                retry_count = 0  # Reset retry count on success
                
                requests = data.get("data", [])
                
                # Find new requests (after initial_newest_id)
                for req in requests:
                    if req.get("uuid") == initial_newest_id:
                        break  # Reached old requests
                    
                    # Check type filter
                    if request_type and req.get("type") != request_type:
                        continue
                    
                    formatted = self._format_request(req)
                    return ToolResult(
                        success=True,
                        message=f"Request received (type: {req.get('type', 'unknown')})",
                        data={"request": formatted}
                    )
                    
            except WebhookApiError as e:
                retry_count += 1
                if retry_count >= max_retries:
                    return ToolResult(
                        success=False,
                        message=f"API error during polling (after {max_retries} retries): {e}",
                        data={"error": str(e)}
                    )
                # Exponential backoff
                await asyncio.sleep(2 ** retry_count)
                continue
        
        type_desc = f" of type '{request_type}'" if request_type else ""
        return ToolResult(
            success=False,
            message=f"Timeout: No request{type_desc} received within {timeout_seconds} seconds",
            data={"timeout": True, "request": None}
        )
    
    async def wait_for_email(
        self,
        webhook_token: str,
        timeout_seconds: int = 60,
        extract_links: bool = True,
    ) -> ToolResult:
        """Wait for an email to be received at the webhook's email address.
        
        The email address format is: {token}@email.webhook.site
        
        Polls the webhook.site API until an email is received.
        
        Args:
            webhook_token: The webhook UUID
            timeout_seconds: Maximum time to wait (default: 60)
            extract_links: If True, extract all URLs from the email body
            
        Returns:
            ToolResult with the email content and extracted links
        """
        import time
        from utils.http_client import WebhookApiError
        
        start_time = time.time()
        poll_interval = 2.0  # Poll every 2 seconds
        max_retries = 3
        retry_count = 0
        
        # Get initial count of emails to detect new ones
        try:
            initial_data = await self._client.get(
                f"/token/{webhook_token}/requests",
                params={"per_page": 10, "sorting": "newest"},
            )
            initial_requests = initial_data.get("data", [])
            # Get IDs of existing emails
            initial_email_ids = {
                req.get("uuid") for req in initial_requests
                if req.get("type") == "email"
            }
        except WebhookApiError as e:
            return ToolResult(
                success=False,
                message=f"Failed to initialize email polling: {e}",
                data={"error": str(e)}
            )
        
        while time.time() - start_time < timeout_seconds:
            await asyncio.sleep(poll_interval)
            
            try:
                # Check for new emails
                data = await self._client.get(
                    f"/token/{webhook_token}/requests",
                    params={"per_page": 10, "sorting": "newest"},
                )
                retry_count = 0  # Reset on success
                
                requests = data.get("data", [])
                
                # Find new emails
                for req in requests:
                    if req.get("type") != "email":
                        continue
                    if req.get("uuid") in initial_email_ids:
                        continue  # Already seen this email
                    
                    # Found a new email!
                    email_data = {
                        "uuid": req.get("uuid"),
                        "from": self._extract_header(req, "from"),
                        "subject": self._extract_header(req, "subject"),
                        "text_content": req.get("text_content"),
                        "html_content": req.get("html_content"),
                        "created_at": req.get("created_at"),
                    }
                    
                    # Extract links if requested
                    links = []
                    if extract_links:
                        content = req.get("text_content") or req.get("html_content") or ""
                        url_pattern = r'https?://[^\s<>"\']+(?:[?&][^\s<>"\']+)*'
                        links = list(set(re.findall(url_pattern, content)))
                        
                        # Identify auth/magic links
                        auth_links = [l for l in links if any(kw in l.lower() for kw in ['magic', 'auth', 'token', 'verify', 'confirm'])]
                        email_data["auth_links"] = auth_links
                    
                    email_data["all_links"] = links
                    
                    return ToolResult(
                        success=True,
                        message=f"Email received: {email_data['subject']}",
                        data={"email": email_data}
                    )
                    
            except WebhookApiError as e:
                retry_count += 1
                if retry_count >= max_retries:
                    return ToolResult(
                        success=False,
                        message=f"API error during email polling (after {max_retries} retries): {e}",
                        data={"error": str(e)}
                    )
                # Exponential backoff
                await asyncio.sleep(2 ** retry_count)
                continue
        
        return ToolResult(
            success=False,
            message=f"Timeout: No email received within {timeout_seconds} seconds",
            data={
                "timeout": True,
                "email": None,
                "email_address": f"{webhook_token}@email.webhook.site"
            }
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
