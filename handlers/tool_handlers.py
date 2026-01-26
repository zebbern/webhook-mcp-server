"""
Tool handler for routing MCP tool calls to appropriate services.

This module acts as the bridge between the MCP protocol and the
service layer, handling argument parsing and response formatting.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.types import TextContent

from models.schemas import WebhookConfig, SearchFilters, DeleteFilters
from services.webhook_service import WebhookService
from services.request_service import RequestService
from services.bugbounty_service import BugBountyService
from utils.http_client import WebhookHttpClient, WebhookApiError
from utils.logger import setup_logger
from utils.validation import ValidationError


class ToolHandler:
    """Routes MCP tool calls to service methods.
    
    Responsible for:
    - Parsing tool arguments into domain models
    - Delegating to appropriate service
    - Formatting responses as MCP TextContent
    - Handling errors consistently
    """
    
    def __init__(self, client: WebhookHttpClient) -> None:
        """Initialize handler with services.
        
        Args:
            client: Configured WebhookHttpClient instance
        """
        self._client = client
        self._webhook_service = WebhookService(client)
        self._request_service = RequestService(client)
        self._bugbounty_service = BugBountyService(client)
        self._logger = setup_logger(__name__)
    
    async def handle(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> list[TextContent]:
        """Route a tool call to the appropriate handler.
        
        Args:
            name: Tool name
            arguments: Tool arguments
            
        Returns:
            List of TextContent responses
        """
        try:
            handler = self._get_handler(name)
            if handler is None:
                return self._error_response(f"Unknown tool: {name}")
            
            result = await handler(arguments)
            return [TextContent(type="text", text=result.to_json())]
            
        except ValidationError as e:
            # Input validation errors - user's fault
            self._logger.warning(f"Validation error in {name}: {e}")
            return self._error_response(f"Validation Error: {e}")
        except WebhookApiError as e:
            # API errors - external service issue
            self._logger.error(f"API error in {name}: {e}", exc_info=False)
            return self._error_response(f"API Error: {e}")
        except (ValueError, KeyError, TypeError) as e:
            # Expected errors - bad input or missing data
            self._logger.warning(f"Expected error in {name}: {e}")
            return self._error_response(f"Error: {e}")
        except Exception as e:
            # Unexpected errors - bug in our code
            self._logger.exception(f"Unexpected error in tool {name}")
            return self._error_response(
                "An unexpected error occurred. Please report this issue."
            )
    
    def _get_handler(self, name: str):
        """Get the handler method for a tool name.
        
        Args:
            name: Tool name
            
        Returns:
            Handler coroutine or None if not found
        """
        handlers = {
            "create_webhook": self._handle_create_webhook,
            "create_webhook_with_config": self._handle_create_webhook_with_config,
            "send_to_webhook": self._handle_send_to_webhook,
            "get_webhook_requests": self._handle_get_webhook_requests,
            "search_requests": self._handle_search_requests,
            "get_latest_request": self._handle_get_latest_request,
            "get_webhook_info": self._handle_get_webhook_info,
            "update_webhook": self._handle_update_webhook,
            "delete_webhook": self._handle_delete_webhook,
            "delete_request": self._handle_delete_request,
            "delete_all_requests": self._handle_delete_all_requests,
            "get_webhook_url": self._handle_get_webhook_url,
            "get_webhook_email": self._handle_get_webhook_email,
            "get_webhook_dns": self._handle_get_webhook_dns,
            "wait_for_request": self._handle_wait_for_request,
            "wait_for_email": self._handle_wait_for_email,
            # Bug bounty tools
            "generate_ssrf_payload": self._handle_generate_ssrf_payload,
            "check_for_callbacks": self._handle_check_for_callbacks,
            "generate_xss_callback": self._handle_generate_xss_callback,
            "generate_canary_token": self._handle_generate_canary_token,
            "extract_links_from_request": self._handle_extract_links_from_request,
        }
        return handlers.get(name)
    
    def _validate_webhook_token(self, token: str) -> None:
        """Validate webhook token format.
        
        Args:
            token: Webhook UUID token
            
        Raises:
            ValidationError: If token is invalid
        """
        from utils.validation import validate_webhook_token
        validate_webhook_token(token)
    
    @staticmethod
    def _error_response(message: str) -> list[TextContent]:
        """Create an error response.
        
        Args:
            message: Error message
            
        Returns:
            List with single error TextContent
        """
        import json
        error = {"success": False, "message": message}
        return [TextContent(type="text", text=json.dumps(error, indent=2))]
    
    # =========================================================================
    # WEBHOOK HANDLERS
    # =========================================================================
    
    async def _handle_create_webhook(self, arguments: dict[str, Any]):
        """Handle create_webhook tool.
        
        Note: arguments parameter required by interface but intentionally unused.
        """
        _ = arguments  # Explicitly mark as intentionally unused
        return await self._webhook_service.create()
    
    async def _handle_create_webhook_with_config(self, arguments: dict[str, Any]):
        """Handle create_webhook_with_config tool."""
        from utils.validation import validate_http_status_code, validate_alias, validate_expiry, validate_positive_int
        
        # Validate configuration values
        if "default_status" in arguments and arguments["default_status"] is not None:
            validate_http_status_code(arguments["default_status"])
        
        if "timeout" in arguments and arguments["timeout"] is not None:
            validate_positive_int(arguments["timeout"], "timeout", min_val=0, max_val=30)
        
        if "alias" in arguments and arguments["alias"] is not None:
            validate_alias(arguments["alias"])
        
        if "expiry" in arguments and arguments["expiry"] is not None:
            validate_expiry(arguments["expiry"])
        
        config = WebhookConfig(
            default_status=arguments.get("default_status"),
            default_content=arguments.get("default_content"),
            default_content_type=arguments.get("default_content_type"),
            timeout=arguments.get("timeout"),
            cors=arguments.get("cors"),
            alias=arguments.get("alias"),
            expiry=arguments.get("expiry"),
        )
        return await self._webhook_service.create_with_config(config)
    
    async def _handle_send_to_webhook(self, arguments: dict[str, Any]):
        """Handle send_to_webhook tool."""
        self._validate_webhook_token(arguments["webhook_token"])
        return await self._webhook_service.send_data(
            webhook_token=arguments["webhook_token"],
            data=arguments["data"],
            headers=arguments.get("headers"),
        )
    
    async def _handle_get_webhook_info(self, arguments: dict[str, Any]):
        """Handle get_webhook_info tool."""
        self._validate_webhook_token(arguments["webhook_token"])
        return await self._webhook_service.get_info(arguments["webhook_token"])
    
    async def _handle_update_webhook(self, arguments: dict[str, Any]):
        """Handle update_webhook tool."""
        from utils.validation import validate_http_status_code, validate_positive_int
        
        self._validate_webhook_token(arguments["webhook_token"])
        
        # Validate configuration values
        if "default_status" in arguments and arguments["default_status"] is not None:
            validate_http_status_code(arguments["default_status"])
        
        if "timeout" in arguments and arguments["timeout"] is not None:
            validate_positive_int(arguments["timeout"], "timeout", min_val=0, max_val=30)
        
        config = WebhookConfig(
            default_status=arguments.get("default_status"),
            default_content=arguments.get("default_content"),
            default_content_type=arguments.get("default_content_type"),
            timeout=arguments.get("timeout"),
            cors=arguments.get("cors"),
        )
        return await self._webhook_service.update(
            webhook_token=arguments["webhook_token"],
            config=config,
        )
    
    async def _handle_delete_webhook(self, arguments: dict[str, Any]):
        """Handle delete_webhook tool."""
        self._validate_webhook_token(arguments["webhook_token"])
        return await self._webhook_service.delete(arguments["webhook_token"])
    
    async def _handle_get_webhook_url(self, arguments: dict[str, Any]):
        """Handle get_webhook_url tool."""
        self._validate_webhook_token(arguments["webhook_token"])
        return await self._webhook_service.get_url(
            arguments["webhook_token"],
            validate=arguments.get("validate", False)
        )
    
    async def _handle_get_webhook_email(self, arguments: dict[str, Any]):
        """Handle get_webhook_email tool."""
        self._validate_webhook_token(arguments["webhook_token"])
        return await self._webhook_service.get_email(
            arguments["webhook_token"],
            validate=arguments.get("validate", False)
        )
    
    async def _handle_get_webhook_dns(self, arguments: dict[str, Any]):
        """Handle get_webhook_dns tool."""
        return await self._webhook_service.get_dns(
            arguments["webhook_token"],
            validate=arguments.get("validate", False)
        )
    
    # =========================================================================
    # REQUEST HANDLERS
    # =========================================================================
    
    async def _handle_get_webhook_requests(self, arguments: dict[str, Any]):
        """Handle get_webhook_requests tool."""
        return await self._request_service.get_all(
            webhook_token=arguments["webhook_token"],
            limit=arguments.get("limit", 10),
            request_type=arguments.get("request_type"),
        )
    
    async def _handle_search_requests(self, arguments: dict[str, Any]):
        """Handle search_requests tool."""
        filters = SearchFilters(
            request_type=arguments.get("request_type"),
            query=arguments.get("query"),
            date_from=arguments.get("date_from"),
            date_to=arguments.get("date_to"),
            sorting=arguments.get("sorting", "newest"),
            limit=arguments.get("limit", 20),
        )
        return await self._request_service.search(
            webhook_token=arguments["webhook_token"],
            filters=filters,
        )
    
    async def _handle_get_latest_request(self, arguments: dict[str, Any]):
        """Handle get_latest_request tool."""
        return await self._request_service.get_latest(arguments["webhook_token"])
    
    async def _handle_delete_request(self, arguments: dict[str, Any]):
        """Handle delete_request tool."""
        return await self._request_service.delete_one(
            webhook_token=arguments["webhook_token"],
            request_id=arguments["request_id"],
        )
    
    async def _handle_delete_all_requests(self, arguments: dict[str, Any]):
        """Handle delete_all_requests tool."""
        filters = None
        if any(k in arguments for k in ["date_from", "date_to", "query"]):
            filters = DeleteFilters(
                date_from=arguments.get("date_from"),
                date_to=arguments.get("date_to"),
                query=arguments.get("query"),
            )
        return await self._request_service.delete_all(
            webhook_token=arguments["webhook_token"],
            filters=filters,
        )

    async def _handle_wait_for_request(self, arguments: dict[str, Any]):
        """Handle wait_for_request tool."""
        return await self._request_service.wait_for_request(
            webhook_token=arguments["webhook_token"],
            timeout_seconds=arguments.get("timeout_seconds", 60),
            request_type=arguments.get("request_type"),
        )
    
    async def _handle_wait_for_email(self, arguments: dict[str, Any]):
        """Handle wait_for_email tool."""
        return await self._request_service.wait_for_email(
            webhook_token=arguments["webhook_token"],
            timeout_seconds=arguments.get("timeout_seconds", 60),
            extract_links=arguments.get("extract_links", True),
        )

    # =========================================================================
    # BUG BOUNTY HANDLERS
    # =========================================================================
    
    async def _handle_generate_ssrf_payload(self, arguments: dict[str, Any]):
        """Handle generate_ssrf_payload tool."""
        # This is a sync method, no await needed
        return self._bugbounty_service.generate_ssrf_payload(
            webhook_token=arguments["webhook_token"],
            identifier=arguments.get("identifier"),
            include_dns=arguments.get("include_dns", True),
            include_ip=arguments.get("include_ip", True),
        )
    
    async def _handle_check_for_callbacks(self, arguments: dict[str, Any]):
        """Handle check_for_callbacks tool."""
        return await self._bugbounty_service.check_for_callbacks(
            webhook_token=arguments["webhook_token"],
            since_minutes=arguments.get("since_minutes", 60),
            identifier=arguments.get("identifier"),
        )
    
    async def _handle_generate_xss_callback(self, arguments: dict[str, Any]):
        """Handle generate_xss_callback tool."""
        # This is a sync method, no await needed
        return self._bugbounty_service.generate_xss_callback(
            webhook_token=arguments["webhook_token"],
            identifier=arguments.get("identifier"),
            include_cookies=arguments.get("include_cookies", True),
            include_dom=arguments.get("include_dom", True),
        )
    
    async def _handle_generate_canary_token(self, arguments: dict[str, Any]):
        """Handle generate_canary_token tool."""
        # This is a sync method, no await needed
        return self._bugbounty_service.generate_canary_token(
            webhook_token=arguments["webhook_token"],
            token_type=arguments.get("token_type", "url"),
            identifier=arguments.get("identifier"),
        )
    
    async def _handle_extract_links_from_request(self, arguments: dict[str, Any]):
        """Handle extract_links_from_request tool."""
        return await self._bugbounty_service.extract_links_from_request(
            webhook_token=arguments["webhook_token"],
            request_id=arguments.get("request_id"),
            filter_domain=arguments.get("filter_domain"),
        )
