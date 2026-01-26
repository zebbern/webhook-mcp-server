"""
Webhook service for managing webhook.site tokens (URLs).

Handles creation, configuration, retrieval, update, and deletion
of webhook endpoints.
"""

from __future__ import annotations

from typing import Any

from models.schemas import WebhookConfig, ToolResult
from utils.http_client import WebhookHttpClient, WebhookApiError, WEBHOOK_SITE_API


class WebhookService:
    """Service for webhook token operations.
    
    Provides business logic for:
    - Creating webhooks (basic and configured)
    - Retrieving webhook information
    - Updating webhook settings
    - Deleting webhooks
    - Generating webhook URLs
    """
    
    def __init__(self, client: WebhookHttpClient) -> None:
        """Initialize service with HTTP client.
        
        Args:
            client: Configured WebhookHttpClient instance
        """
        self._client = client
    
    def _build_webhook_urls(self, token: str, alias: str | None = None) -> dict[str, str]:
        """Build all URL variants for a webhook token.
        
        Args:
            token: The webhook UUID
            alias: Optional custom alias
            
        Returns:
            Dict with url, subdomain_url, api_url, email, and dns keys
        """
        identifier = alias if alias else token
        return {
            "url": f"{WEBHOOK_SITE_API}/{identifier}",
            "subdomain_url": f"https://{token}.webhook.site",
            "api_url": f"{WEBHOOK_SITE_API}/token/{token}",
            "email": f"{token}@email.webhook.site",
            "dns": f"{token}.dnshook.site",
        }
    
    async def _validate_token_exists(self, webhook_token: str) -> ToolResult | None:
        """Validate that a webhook token exists.
        
        Args:
            webhook_token: The webhook UUID to validate
            
        Returns:
            None if token is valid, ToolResult with error if invalid
        """
        try:
            await self._client.get(f"/token/{webhook_token}")
            return None  # Token is valid
        except WebhookApiError as e:
            if e.status_code == 404:
                return ToolResult(
                    success=False,
                    message=f"Token '{webhook_token}' not found or expired",
                    data=None
                )
            return ToolResult(
                success=False,
                message=f"Failed to validate token: {str(e)}",
                data=None
            )
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Failed to validate token: {str(e)}",
                data=None
            )
    
    async def create(self) -> ToolResult:
        """Create a new webhook with default settings.
        
        Returns:
            ToolResult with token, URL, subdomain URL, email, and expiry information
        """
        response = await self._client.post("/token")
        response.raise_for_status()
        data = response.json()
        
        token = data.get("uuid")
        alias = data.get("alias")
        urls = self._build_webhook_urls(token, alias)
        
        return ToolResult(
            success=True,
            message=f"Webhook created! Send requests to: {urls['url']}",
            data={
                "token": token,
                "alias": alias,
                **urls,
                "expires_at": data.get("expires_at"),
                "default_status": data.get("default_status"),
                "default_content": data.get("default_content"),
                "default_content_type": data.get("default_content_type"),
                "timeout": data.get("timeout"),
                "cors": data.get("cors"),
            }
        )
    
    async def create_with_config(self, config: WebhookConfig) -> ToolResult:
        """Create a new webhook with custom configuration.
        
        Args:
            config: WebhookConfig with desired settings
            
        Returns:
            ToolResult with token, URL, subdomain URL, email, and applied settings
        """
        payload = config.to_payload()
        
        response = await self._client.post("/token", json_data=payload)
        response.raise_for_status()
        data = response.json()
        
        token = data.get("uuid")
        alias = data.get("alias")
        urls = self._build_webhook_urls(token, alias)
        
        return ToolResult(
            success=True,
            message=f"Webhook created with custom config! URL: {urls['url']}",
            data={
                "token": token,
                "alias": alias,
                **urls,
                "default_status": data.get("default_status"),
                "default_content": data.get("default_content"),
                "default_content_type": data.get("default_content_type"),
                "timeout": data.get("timeout"),
                "cors": data.get("cors"),
                "expires_at": data.get("expires_at"),
            }
        )
    
    async def get_info(self, webhook_token: str) -> ToolResult:
        """Get detailed information about a webhook.
        
        Args:
            webhook_token: The webhook UUID
            
        Returns:
            ToolResult with complete webhook details
        """
        data = await self._client.get(f"/token/{webhook_token}")
        
        return ToolResult(
            success=True,
            message="Webhook information retrieved",
            data={
                "token": data.get("uuid"),
                "alias": data.get("alias"),
                "url": f"{WEBHOOK_SITE_API}/{data.get('uuid')}",
                "default_status": data.get("default_status"),
                "default_content": data.get("default_content"),
                "default_content_type": data.get("default_content_type"),
                "timeout": data.get("timeout"),
                "cors": data.get("cors"),
                "premium": data.get("premium"),
                "actions": data.get("actions"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "expires_at": data.get("expires_at"),
                "premium_expires_at": data.get("premium_expires_at"),
                "latest_request_at": data.get("latest_request_at"),
                "requests_count": data.get("requests"),
            }
        )
    
    async def update(
        self,
        webhook_token: str,
        config: WebhookConfig,
    ) -> ToolResult:
        """Update webhook settings.
        
        Args:
            webhook_token: The webhook UUID
            config: WebhookConfig with settings to update
            
        Returns:
            ToolResult with updated settings
        """
        payload = config.to_payload()
        
        data = await self._client.put(
            f"/token/{webhook_token}",
            json_data=payload,
        )
        
        return ToolResult(
            success=True,
            message="Webhook settings updated successfully",
            data={
                "token": data.get("uuid"),
                "updated_settings": payload,
                "default_status": data.get("default_status"),
                "default_content": data.get("default_content"),
                "default_content_type": data.get("default_content_type"),
                "timeout": data.get("timeout"),
                "cors": data.get("cors"),
            }
        )
    
    async def delete(self, webhook_token: str) -> ToolResult:
        """Delete a webhook and all its data.
        
        Args:
            webhook_token: The webhook UUID
            
        Returns:
            ToolResult indicating success/failure
        """
        status_code = await self._client.delete(f"/token/{webhook_token}")
        success = status_code in [200, 204]
        
        return ToolResult(
            success=success,
            message="Webhook deleted successfully" if success else "Failed to delete webhook",
            data={"status_code": status_code}
        )
    
    async def send_data(
        self,
        webhook_token: str,
        data: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> ToolResult:
        """Send data to a webhook endpoint.
        
        Args:
            webhook_token: The webhook UUID
            data: JSON data to send
            headers: Optional custom headers
            
        Returns:
            ToolResult with send confirmation
        """
        url = f"/{webhook_token}"
        
        response = await self._client.post(url, json_data=data, headers=headers)
        
        return ToolResult(
            success=True,
            message="Data sent successfully to webhook",
            data={
                "status_code": response.status_code,
                "url": f"{WEBHOOK_SITE_API}/{webhook_token}",
                "data_sent": data,
            }
        )
    
    async def get_url(self, webhook_token: str, validate: bool = False) -> ToolResult:
        """Get the full URL for a webhook token.
        
        Args:
            webhook_token: The webhook UUID
            validate: If True, verify token exists via API call
            
        Returns:
            ToolResult with token and full URL
        """
        if validate:
            validation_error = await self._validate_token_exists(webhook_token)
            if validation_error:
                return validation_error
        
        url = f"{WEBHOOK_SITE_API}/{webhook_token}"
        
        return ToolResult(
            success=True,
            message=f"Webhook URL: {url}",
            data={
                "token": webhook_token,
                "url": url,
            }
        )
    
    async def get_email(self, webhook_token: str, validate: bool = False) -> ToolResult:
        """Get the email address for a webhook token.
        
        Emails sent to this address will be captured as webhook requests.
        
        Args:
            webhook_token: The webhook UUID
            validate: If True, verify token exists via API call
            
        Returns:
            ToolResult with token, email address, and URL
        """
        if validate:
            validation_error = await self._validate_token_exists(webhook_token)
            if validation_error:
                return validation_error
        
        email = f"{webhook_token}@email.webhook.site"
        url = f"{WEBHOOK_SITE_API}/{webhook_token}"
        
        return ToolResult(
            success=True,
            message=f"Webhook email: {email}",
            data={
                "token": webhook_token,
                "email": email,
                "url": url,
            }
        )
    
    async def get_dns(self, webhook_token: str, validate: bool = False) -> ToolResult:
        """Get the DNSHook domain for a webhook token.
        
        DNS lookups to this domain (and subdomains) will be captured.
        Useful for bypassing firewalls or as canary tokens.
        
        Args:
            webhook_token: The webhook UUID
            validate: If True, verify token exists via API call
            
        Returns:
            ToolResult with token, DNS domain, example subdomain usage, and URL
        """
        if validate:
            validation_error = await self._validate_token_exists(webhook_token)
            if validation_error:
                return validation_error
        
        dns_domain = f"{webhook_token}.dnshook.site"
        url = f"{WEBHOOK_SITE_API}/{webhook_token}"
        
        return ToolResult(
            success=True,
            message=f"DNSHook domain: {dns_domain}",
            data={
                "token": webhook_token,
                "dns_domain": dns_domain,
                "example_subdomain": f"mydata.{dns_domain}",
                "url": url,
            }
        )
