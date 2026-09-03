"""
Webhook service for managing webhook.site tokens (URLs).

Handles creation, configuration, retrieval, update, and deletion
of webhook endpoints.
"""

from __future__ import annotations

from typing import Any

from models.schemas import ToolResult, WebhookConfig
from utils.http_client import WEBHOOK_SITE_API, WebhookApiError, WebhookHttpClient


def build_webhook_urls(token: str, alias: str | None = None) -> dict[str, str]:
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


def format_token(data: dict[str, Any]) -> dict[str, Any]:
    """Flatten a token object from the API into the fields tools return."""
    token = data.get("uuid")
    alias = data.get("alias")
    return {
        "token": token,
        "alias": alias,
        **build_webhook_urls(token or "", alias),
        "premium": data.get("premium"),
        "expires_at": data.get("expires_at"),
        "default_status": data.get("default_status"),
        "default_content": data.get("default_content"),
        "default_content_type": data.get("default_content_type"),
        "timeout": data.get("timeout"),
        "listen": data.get("listen"),
        "cors": data.get("cors"),
        "actions": data.get("actions"),
        "request_limit": data.get("request_limit"),
        "group_id": data.get("group_id"),
        "description": data.get("description"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "latest_request_at": data.get("latest_request_at"),
        "requests_count": data.get("requests"),
    }


class WebhookService:
    """Service for webhook token operations.

    Provides business logic for:
    - Creating webhooks (basic and configured)
    - Retrieving webhook information
    - Updating webhook settings
    - Deleting webhooks
    - Generating webhook URLs
    """

    def __init__(self, client: WebhookHttpClient, default_expiry: int | None = None) -> None:
        """Initialize service with HTTP client.

        Args:
            client: Configured WebhookHttpClient instance
            default_expiry: Expiry (seconds) applied to new tokens when the
                caller does not pass one (WEBHOOK_SITE_DEFAULT_EXPIRY). None
                keeps whatever the account default is: permanent on paid
                plans, 7 days for anonymous tokens.
        """
        self._client = client
        self._default_expiry = default_expiry

    def _build_webhook_urls(self, token: str, alias: str | None = None) -> dict[str, str]:
        return build_webhook_urls(token, alias)

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
                )
            return ToolResult(
                success=False,
                message=f"Failed to validate token: {str(e)}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Failed to validate token: {str(e)}",
            )

    def _create_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "expiry" not in payload and self._default_expiry:
            payload = {**payload, "expiry": self._default_expiry}
        return payload

    async def create(self) -> ToolResult:
        """Create a new webhook with default settings.

        Returns:
            ToolResult with token, URL, subdomain URL, email, and expiry information
        """
        payload = self._create_payload({})
        response = await self._client.post("/token", json_data=payload or None)
        data = response.json()
        info = format_token(data)
        return ToolResult(
            success=True,
            message=f"Webhook created! Send requests to: {info['url']}",
            data=info,
        )

    async def configure(
        self,
        config: WebhookConfig,
        webhook_token: str | None = None,
    ) -> ToolResult:
        """Create a webhook with custom settings, or update an existing one.

        Args:
            config: WebhookConfig with the settings to apply
            webhook_token: Update this token; None creates a new one

        Returns:
            ToolResult with the token's settings and URLs
        """
        payload = config.to_payload()
        if webhook_token is None:
            payload = self._create_payload(payload)
            response = await self._client.post("/token", json_data=payload or None)
            data = response.json()
            info = format_token(data)
            return ToolResult(
                success=True,
                message=f"Webhook created with custom config! URL: {info['url']}",
                data={**info, "applied_settings": payload},
            )

        data = await self._client.put(f"/token/{webhook_token}", json_data=payload)
        info = format_token(data) if data.get("uuid") else {"token": webhook_token}
        return ToolResult(
            success=True,
            message="Webhook settings updated successfully",
            data={**info, "updated_settings": payload},
        )

    async def get_info(self, webhook_token: str) -> ToolResult:
        """Get detailed information about a webhook, including every URL variant.

        Args:
            webhook_token: The webhook UUID

        Returns:
            ToolResult with complete webhook details
        """
        data = await self._client.get(f"/token/{webhook_token}")
        info = format_token(data)
        info["premium_expires_at"] = data.get("premium_expires_at")
        return ToolResult(
            success=True,
            message="Webhook information retrieved",
            data=info,
        )

    async def delete(self, webhook_token: str) -> ToolResult:
        """Delete a webhook and all its data.

        Args:
            webhook_token: The webhook UUID

        Returns:
            ToolResult indicating success/failure
        """
        status_code = await self._client.delete(f"/token/{webhook_token}")
        success = status_code in (200, 204)
        return ToolResult(
            success=success,
            message="Webhook deleted successfully" if success else "Failed to delete webhook",
            data={"token": webhook_token, "status_code": status_code},
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
            },
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
            },
        )
