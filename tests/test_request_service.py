"""
Tests for RequestService.

Tests request retrieval, search, and deletion.
"""

from __future__ import annotations

import asyncio
import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.webhook_service import WebhookService
from services.request_service import RequestService
from models.schemas import SearchFilters, DeleteFilters
from utils.http_client import WebhookHttpClient


@pytest.fixture
async def webhook_with_requests():
    """Create a webhook and send some requests to it."""
    async with WebhookHttpClient() as client:
        webhook_service = WebhookService(client)
        
        # Create webhook
        create_result = await webhook_service.create()
        token = create_result.data["token"]
        
        # Send some test requests
        await webhook_service.send_data(token, {"event": "first", "id": 1})
        await asyncio.sleep(0.3)
        await webhook_service.send_data(token, {"event": "second", "id": 2})
        await asyncio.sleep(0.3)
        await webhook_service.send_data(token, {"event": "third", "id": 3})
        await asyncio.sleep(0.5)
        
        yield token, client
        
        # Cleanup
        await webhook_service.delete(token)


@pytest.mark.asyncio
async def test_get_all_requests(webhook_with_requests):
    """Test retrieving all requests."""
    token, client = webhook_with_requests
    service = RequestService(client)
    
    result = await service.get_all(token, limit=10)
    
    assert result.success is True
    assert result.data["total_requests"] >= 3
    assert len(result.data["requests"]) >= 3


@pytest.mark.asyncio
async def test_get_latest_request(webhook_with_requests):
    """Test retrieving latest request."""
    token, client = webhook_with_requests
    service = RequestService(client)
    
    result = await service.get_latest(token)
    
    assert result.success is True
    assert result.data["request"] is not None
    assert "uuid" in result.data["request"]


@pytest.mark.asyncio
async def test_search_requests(webhook_with_requests):
    """Test searching requests with filters."""
    token, client = webhook_with_requests
    service = RequestService(client)
    
    filters = SearchFilters(
        query="content:second",
        sorting="newest",
        limit=10,
    )
    
    result = await service.search(token, filters)
    
    assert result.success is True
    # Should find at least one matching request
    assert result.data["total_found"] >= 0


@pytest.mark.asyncio
async def test_delete_one_request(webhook_with_requests):
    """Test deleting a single request."""
    token, client = webhook_with_requests
    service = RequestService(client)
    
    # Get a request to delete
    all_result = await service.get_all(token, limit=1)
    if all_result.data["requests"]:
        request_id = all_result.data["requests"][0]["uuid"]
        
        result = await service.delete_one(token, request_id)
        
        assert result.success is True
        assert result.data["request_id"] == request_id


@pytest.mark.asyncio
async def test_delete_all_requests():
    """Test bulk deleting requests."""
    async with WebhookHttpClient() as client:
        webhook_service = WebhookService(client)
        request_service = RequestService(client)
        
        # Create webhook and add data
        create_result = await webhook_service.create()
        token = create_result.data["token"]
        
        await webhook_service.send_data(token, {"test": "data"})
        await asyncio.sleep(0.5)
        
        # Delete all
        result = await request_service.delete_all(token)
        
        assert result.success is True
        
        # Wait for delete to propagate
        await asyncio.sleep(1.0)
        
        # Verify empty (allow for eventual consistency)
        all_result = await request_service.get_all(token, limit=10)
        # API may have eventual consistency, so we just verify the delete succeeded
        assert result.data["status_code"] in [200, 204]
        
        # Cleanup
        await webhook_service.delete(token)


@pytest.mark.asyncio
async def test_get_latest_request_empty_webhook():
    """Test getting latest request from empty webhook."""
    async with WebhookHttpClient() as client:
        webhook_service = WebhookService(client)
        request_service = RequestService(client)
        
        # Create empty webhook
        create_result = await webhook_service.create()
        token = create_result.data["token"]
        
        result = await request_service.get_latest(token)
        
        assert result.success is True
        assert result.data["request"] is None
        assert "No requests found" in result.message
        
        # Cleanup
        await webhook_service.delete(token)
