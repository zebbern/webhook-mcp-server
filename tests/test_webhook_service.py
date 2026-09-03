"""
Tests for WebhookService.

Tests webhook creation, configuration, update, and deletion.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.schemas import WebhookConfig
from services.webhook_service import WebhookService
from utils.http_client import WebhookHttpClient


@pytest.mark.live
@pytest.mark.asyncio
async def test_create_webhook():
    """Test basic webhook creation."""
    async with WebhookHttpClient() as client:
        service = WebhookService(client)
        result = await service.create()
        
        assert result.success is True
        assert "token" in result.data
        assert "url" in result.data
        assert result.data["token"] is not None
        assert "webhook.site" in result.data["url"]


@pytest.mark.live
@pytest.mark.asyncio
async def test_create_webhook_with_config():
    """Test webhook creation with custom configuration."""
    async with WebhookHttpClient() as client:
        service = WebhookService(client)
        
        config = WebhookConfig(
            default_status=201,
            default_content='{"status": "created"}',
            default_content_type="application/json",
            cors=True,
        )
        
        result = await service.configure(config)

        assert result.success is True
        assert result.data["default_status"] == 201
        assert result.data["cors"] is True
        await service.delete(result.data["token"])


@pytest.mark.live
@pytest.mark.asyncio
async def test_get_webhook_info():
    """Test retrieving webhook information."""
    async with WebhookHttpClient() as client:
        service = WebhookService(client)
        
        # Create a webhook first
        create_result = await service.create()
        token = create_result.data["token"]
        
        # Get info
        result = await service.get_info(token)
        
        assert result.success is True
        assert result.data["token"] == token
        assert "created_at" in result.data
        assert "expires_at" in result.data


@pytest.mark.live
@pytest.mark.asyncio
async def test_update_webhook():
    """Test updating webhook settings."""
    async with WebhookHttpClient() as client:
        service = WebhookService(client)
        
        # Create a webhook first
        create_result = await service.create()
        token = create_result.data["token"]
        
        # Update it
        config = WebhookConfig(
            default_status=202,
            default_content="Updated!",
        )
        result = await service.configure(config, webhook_token=token)

        assert result.success is True
        assert result.data["default_status"] == 202
        assert result.data["default_content"] == "Updated!"
        await service.delete(token)


@pytest.mark.live
@pytest.mark.asyncio
async def test_send_data():
    """Test sending data to a webhook."""
    async with WebhookHttpClient() as client:
        service = WebhookService(client)
        
        # Create a webhook first
        create_result = await service.create()
        token = create_result.data["token"]
        
        # Send data
        result = await service.send_data(
            webhook_token=token,
            data={"event": "test", "value": 42},
        )
        
        assert result.success is True
        assert result.data["status_code"] == 200
        assert result.data["data_sent"]["event"] == "test"


def test_build_webhook_urls():
    """Every address variant derives from the token (alias only changes url)."""
    from services.webhook_service import build_webhook_urls

    urls = build_webhook_urls("test-token-123")
    assert urls["url"] == "https://webhook.site/test-token-123"
    assert urls["subdomain_url"] == "https://test-token-123.webhook.site"
    assert urls["api_url"] == "https://webhook.site/token/test-token-123"
    assert urls["email"] == "test-token-123@emailhook.site"
    assert urls["dns"] == "test-token-123.dnshook.site"
    assert build_webhook_urls("test-token-123", alias="my-alias")["url"] == "https://webhook.site/my-alias"


@pytest.mark.asyncio
async def test_get_email():
    """Test email address generation."""
    async with WebhookHttpClient() as client:
        service = WebhookService(client)
        
        result = await service.get_email("test-token-123")
        
        assert result.success is True
        assert result.data["token"] == "test-token-123"
        assert result.data["email"] == "test-token-123@emailhook.site"
        assert result.data["url"] == "https://webhook.site/test-token-123"


@pytest.mark.live
@pytest.mark.asyncio
async def test_delete_webhook():
    """Test webhook deletion."""
    async with WebhookHttpClient() as client:
        service = WebhookService(client)
        
        # Create a webhook first
        create_result = await service.create()
        token = create_result.data["token"]
        
        # Delete it
        result = await service.delete(token)
        
        assert result.success is True
        assert result.data["status_code"] in [200, 204]
