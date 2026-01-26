"""
Test suite for Bug Bounty tools.

Tests the 5 new security testing tools:
- generate_ssrf_payload
- check_for_callbacks  
- generate_xss_callback
- generate_canary_token
- extract_links_from_request
"""

import pytest
import json
import aiohttp
import asyncio
from contextlib import asynccontextmanager

from handlers.tool_handlers import ToolHandler
from utils.http_client import WebhookHttpClient


@asynccontextmanager
async def create_handler():
    """Create a tool handler with initialized client."""
    async with WebhookHttpClient() as client:
        yield ToolHandler(client)


@pytest.fixture
async def handler_and_token():
    """Create a handler and test webhook, yield both, then cleanup."""
    async with create_handler() as handler:
        # Create webhook
        result = await handler.handle("create_webhook", {})
        data = json.loads(result[0].text)
        assert data["success"] is True, f"Failed to create webhook: {data}"
        token = data["token"]  # Token is at top level
        
        yield handler, token
        
        # Cleanup
        await handler.handle("delete_webhook", {"webhook_token": token})


class TestBugBountyTools:
    """Test suite for bug bounty security tools."""
    
    @pytest.mark.asyncio
    async def test_generate_ssrf_payload_basic(self, handler_and_token):
        """Test generating basic SSRF payloads."""
        handler, webhook_token = handler_and_token
        result = await handler.handle(
            "generate_ssrf_payload",
            {"webhook_token": webhook_token}
        )
        data = json.loads(result[0].text)
        
        assert data["success"] is True, f"Failed: {data}"
        assert "payloads" in data
        assert "token" in data
        
        payloads = data["payloads"]
        assert len(payloads) > 0, "Should generate at least one payload"
        
        # Check expected payload types
        assert "http_url" in payloads
        assert "https_url" in payloads
        assert "dns_payload" in payloads
    
    @pytest.mark.asyncio
    async def test_generate_ssrf_payload_with_identifier(self, handler_and_token):
        """Test generating SSRF payloads with custom identifier."""
        handler, webhook_token = handler_and_token
        result = await handler.handle(
            "generate_ssrf_payload",
            {
                "webhook_token": webhook_token,
                "identifier": "test-injection-1",
                "include_dns": True,
                "include_ip": True
            }
        )
        data = json.loads(result[0].text)
        
        assert data["success"] is True, f"Failed: {data}"
        assert "payloads" in data
        assert data["identifier"] == "test-injection-1"
    
    @pytest.mark.asyncio
    async def test_check_for_callbacks(self, handler_and_token):
        """Test checking for OOB callbacks."""
        handler, webhook_token = handler_and_token
        result = await handler.handle(
            "check_for_callbacks",
            {
                "webhook_token": webhook_token,
                "since_minutes": 5
            }
        )
        data = json.loads(result[0].text)
        
        assert data["success"] is True, f"Failed: {data}"
        assert "detected" in data
        assert "total_callbacks" in data
        # Fresh webhook should have no callbacks
        assert data["total_callbacks"] == 0
    
    @pytest.mark.asyncio
    async def test_check_for_callbacks_with_identifier(self, handler_and_token):
        """Test checking for callbacks with identifier filter."""
        handler, webhook_token = handler_and_token
        result = await handler.handle(
            "check_for_callbacks",
            {
                "webhook_token": webhook_token,
                "since_minutes": 5,
                "identifier": "ssrf-test-123"
            }
        )
        data = json.loads(result[0].text)
        
        assert data["success"] is True, f"Failed: {data}"
        assert "identifier_filter" in data
        assert data["identifier_filter"] == "ssrf-test-123"
    
    @pytest.mark.asyncio
    async def test_generate_xss_callback(self, handler_and_token):
        """Test generating XSS callback payloads."""
        handler, webhook_token = handler_and_token
        result = await handler.handle(
            "generate_xss_callback",
            {
                "webhook_token": webhook_token
            }
        )
        data = json.loads(result[0].text)
        
        assert data["success"] is True, f"Failed: {data}"
        assert "payloads" in data
        
        payloads = data["payloads"]
        # Check expected payload types
        assert "basic_img" in payloads
        assert "basic_script" in payloads
        assert "cookie_steal" in payloads
    
    @pytest.mark.asyncio
    async def test_generate_xss_callback_with_options(self, handler_and_token):
        """Test generating XSS callbacks with custom options."""
        handler, webhook_token = handler_and_token
        result = await handler.handle(
            "generate_xss_callback",
            {
                "webhook_token": webhook_token,
                "identifier": "comment-field",
                "include_cookies": True,
                "include_dom": True
            }
        )
        data = json.loads(result[0].text)
        
        assert data["success"] is True, f"Failed: {data}"
        assert data["identifier"] == "comment-field"
    
    @pytest.mark.asyncio
    async def test_generate_canary_token_url(self, handler_and_token):
        """Test generating URL canary token."""
        handler, webhook_token = handler_and_token
        result = await handler.handle(
            "generate_canary_token",
            {
                "webhook_token": webhook_token,
                "token_type": "url",
                "identifier": "test-canary"
            }
        )
        data = json.loads(result[0].text)
        
        assert data["success"] is True, f"Failed: {data}"
        assert "canary" in data
        assert data["type"] == "url"
        assert data["identifier"] == "test-canary"
        assert "token" in data["canary"]
    
    @pytest.mark.asyncio
    async def test_generate_canary_token_dns(self, handler_and_token):
        """Test generating DNS canary token."""
        handler, webhook_token = handler_and_token
        result = await handler.handle(
            "generate_canary_token",
            {
                "webhook_token": webhook_token,
                "token_type": "dns"
            }
        )
        data = json.loads(result[0].text)
        
        assert data["success"] is True, f"Failed: {data}"
        assert data["type"] == "dns"
        assert "dnshook.site" in data["canary"]["token"]
    
    @pytest.mark.asyncio
    async def test_generate_canary_token_email(self, handler_and_token):
        """Test generating email canary token."""
        handler, webhook_token = handler_and_token
        result = await handler.handle(
            "generate_canary_token",
            {
                "webhook_token": webhook_token,
                "token_type": "email"
            }
        )
        data = json.loads(result[0].text)
        
        assert data["success"] is True, f"Failed: {data}"
        assert data["type"] == "email"
        assert "@email.webhook.site" in data["canary"]["token"]


class TestExtractLinksFromRequest:
    """Tests for extract_links_from_request tool."""
    
    @pytest.mark.asyncio
    async def test_extract_links_from_request(self, handler_and_token):
        """Test extracting links from a request body."""
        handler, webhook_token = handler_and_token
        
        # Get the webhook URL
        url_result = await handler.handle(
            "get_webhook_url",
            {"webhook_token": webhook_token}
        )
        url_data = json.loads(url_result[0].text)
        webhook_url = url_data["url"]
        
        # Send a request with links in the body
        html_body = """
        Click here: https://example.com/page1
        Or visit https://test.com/page2?token=secret123
        API: https://api.example.com/v1/users
        Auth link: https://auth.example.com/verify?code=abc
        """
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                data=html_body,
                headers={"Content-Type": "text/plain"}
            ) as resp:
                assert resp.status == 200
        
        # Wait a moment for the request to be captured
        await asyncio.sleep(1)
        
        # Extract links (no request_id means latest)
        result = await handler.handle(
            "extract_links_from_request",
            {
                "webhook_token": webhook_token
            }
        )
        data = json.loads(result[0].text)
        
        assert data["success"] is True, f"Failed: {data}"
        assert "links" in data
        assert data["total_links"] >= 1, f"Should find links, got: {data}"
    
    @pytest.mark.asyncio
    async def test_extract_links_no_content(self, handler_and_token):
        """Test extract links when request has no links."""
        handler, webhook_token = handler_and_token
        
        # Get webhook URL
        url_result = await handler.handle(
            "get_webhook_url",
            {"webhook_token": webhook_token}
        )
        url_data = json.loads(url_result[0].text)
        webhook_url = url_data["url"]
        
        # Send request with no links
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                data="just plain text with no links whatsoever",
                headers={"Content-Type": "text/plain"}
            ) as resp:
                assert resp.status == 200
        
        # Wait a moment
        await asyncio.sleep(1)
        
        # Extract links (should be empty)
        result = await handler.handle(
            "extract_links_from_request",
            {
                "webhook_token": webhook_token
            }
        )
        data = json.loads(result[0].text)
        
        assert data["success"] is True, f"Failed: {data}"
        assert data["total_links"] == 0


class TestBugBountyIntegration:
    """Integration tests for bug bounty workflow."""
    
    @pytest.mark.asyncio
    async def test_ssrf_detection_workflow(self, handler_and_token):
        """Test full SSRF detection workflow."""
        handler, webhook_token = handler_and_token
        
        # Step 1: Generate SSRF payloads
        ssrf_result = await handler.handle(
            "generate_ssrf_payload",
            {"webhook_token": webhook_token, "identifier": "ssrf-test"}
        )
        ssrf_data = json.loads(ssrf_result[0].text)
        assert ssrf_data["success"] is True
        
        # Get one of the payload URLs
        webhook_url = ssrf_data["payloads"]["https_url"]
        
        # Step 2: Simulate a callback (as if SSRF succeeded)
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{webhook_url}?ssrf=success",
                headers={"X-SSRF-Test": "callback"}
            ) as resp:
                assert resp.status == 200
        
        # Wait for request to be captured
        await asyncio.sleep(1)
        
        # Step 3: Check for callbacks
        check_result = await handler.handle(
            "check_for_callbacks",
            {"webhook_token": webhook_token, "since_minutes": 5}
        )
        check_data = json.loads(check_result[0].text)
        
        assert check_data["success"] is True
        assert check_data["detected"] is True, "Should detect the callback"
        assert check_data["total_callbacks"] >= 1
    
    @pytest.mark.asyncio
    async def test_canary_detection_workflow(self, handler_and_token):
        """Test canary token detection workflow."""
        handler, webhook_token = handler_and_token
        
        # Step 1: Generate canary token
        canary_result = await handler.handle(
            "generate_canary_token",
            {
                "webhook_token": webhook_token,
                "token_type": "url",
                "identifier": "secret-doc"
            }
        )
        canary_data = json.loads(canary_result[0].text)
        assert canary_data["success"] is True
        
        canary_url = canary_data["canary"]["token"]
        
        # Step 2: Simulate someone accessing the canary
        async with aiohttp.ClientSession() as session:
            async with session.get(canary_url) as resp:
                assert resp.status == 200
        
        # Wait for request to be captured
        await asyncio.sleep(1)
        
        # Step 3: Check for access
        check_result = await handler.handle(
            "check_for_callbacks",
            {"webhook_token": webhook_token, "since_minutes": 5}
        )
        check_data = json.loads(check_result[0].text)
        
        assert check_data["success"] is True
        assert check_data["detected"] is True
