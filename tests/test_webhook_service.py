"""
Tests for WebhookService.

Tests webhook creation, configuration, update, and deletion.
"""

from __future__ import annotations

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.webhook_service import WebhookService
from models.schemas import WebhookConfig
from utils.http_client import WebhookHttpClient


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
        
        result = await service.create_with_config(config)
        
        assert result.success is True
        assert result.data["default_status"] == 201
        assert result.data["cors"] is True


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
        result = await service.update(token, config)
        
        assert result.success is True
        assert result.data["default_status"] == 202
        assert result.data["default_content"] == "Updated!"


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


@pytest.mark.asyncio
async def test_get_url():
    """Test URL generation."""
    async with WebhookHttpClient() as client:
        service = WebhookService(client)
        
        result = service.get_url("test-token-123")
        
        assert result.success is True
        assert result.data["token"] == "test-token-123"
        assert result.data["url"] == "https://webhook.site/test-token-123"


@pytest.mark.asyncio
async def test_get_email():
    """Test email address generation."""
    async with WebhookHttpClient() as client:
        service = WebhookService(client)
        
        result = service.get_email("test-token-123")
        
        assert result.success is True
        assert result.data["token"] == "test-token-123"
        assert result.data["email"] == "test-token-123@email.webhook.site"
        assert result.data["url"] == "https://webhook.site/test-token-123"


@pytest.mark.asyncio
async def test_get_dns():
    """Test DNSHook domain generation."""
    async with WebhookHttpClient() as client:
        service = WebhookService(client)
        
        result = service.get_dns("test-token-123")
        
        assert result.success is True
        assert result.data["token"] == "test-token-123"
        assert result.data["dns_domain"] == "test-token-123.dnshook.site"
        assert result.data["example_subdomain"] == "mydata.test-token-123.dnshook.site"
        assert result.data["url"] == "https://webhook.site/test-token-123"


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
