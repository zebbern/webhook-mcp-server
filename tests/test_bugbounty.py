"""Live tests for bug bounty helper tools."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.bugbounty_service import BugBountyService
from services.webhook_service import WebhookService
from utils.http_client import WebhookHttpClient

pytestmark = pytest.mark.live


@pytest.fixture
async def bounty_and_token():
    """Create a webhook and bounty service, then clean up."""
    async with WebhookHttpClient() as client:
        webhooks = WebhookService(client)
        bounty = BugBountyService(client)
        created = await webhooks.create()
        assert created.success is True, created.message
        token = created.data["token"]
        try:
            yield bounty, token, created.data["url"]
        finally:
            await webhooks.delete(token)


class TestBugBountyTools:
    @pytest.mark.asyncio
    async def test_generate_ssrf_payload_basic(self, bounty_and_token):
        bounty, token, _url = bounty_and_token
        result = bounty.generate_ssrf_payload(token)
        assert result.success is True
        assert "http_url" in result.data["callback_payloads"]
        assert "https_url" in result.data["callback_payloads"]
        assert "dns_payload" in result.data["callback_payloads"]

    @pytest.mark.asyncio
    async def test_generate_ssrf_payload_with_identifier(self, bounty_and_token):
        bounty, token, _url = bounty_and_token
        result = bounty.generate_ssrf_payload(
            token,
            identifier="test-injection-1",
            include_dns=True,
            include_ip=True,
        )
        assert result.success is True
        assert result.data["identifier"] == "test-injection-1"

    @pytest.mark.asyncio
    async def test_check_for_callbacks(self, bounty_and_token):
        bounty, token, _url = bounty_and_token
        result = await bounty.check_for_callbacks(token, since_minutes=5)
        assert result.success is True
        assert result.data["total_callbacks"] == 0

    @pytest.mark.asyncio
    async def test_generate_xss_callback(self, bounty_and_token):
        bounty, token, _url = bounty_and_token
        result = bounty.generate_xss_callback(token)
        assert result.success is True
        assert "basic_img" in result.data["payloads"]
        assert "cookie_steal" in result.data["payloads"]

    @pytest.mark.asyncio
    async def test_generate_canary_token_url(self, bounty_and_token):
        bounty, token, _url = bounty_and_token
        result = bounty.generate_canary_token(token, token_type="url", identifier="test-canary")
        assert result.success is True
        assert result.data["type"] == "url"
        assert "token" in result.data["canary"]

    @pytest.mark.asyncio
    async def test_generate_canary_token_dns(self, bounty_and_token):
        bounty, token, _url = bounty_and_token
        result = bounty.generate_canary_token(token, token_type="dns")
        assert result.success is True
        assert "dnshook.site" in result.data["canary"]["token"]

    @pytest.mark.asyncio
    async def test_generate_canary_token_email(self, bounty_and_token):
        bounty, token, _url = bounty_and_token
        result = bounty.generate_canary_token(token, token_type="email")
        assert result.success is True
        assert "@emailhook.site" in result.data["canary"]["token"]


class TestExtractLinksFromRequest:
    @pytest.mark.asyncio
    async def test_extract_links_from_request(self, bounty_and_token):
        bounty, token, webhook_url = bounty_and_token
        html_body = """
        Click here: https://example.com/page1
        Auth link: https://auth.example.com/verify?code=abc
        """
        async with httpx.AsyncClient() as session:
            resp = await session.post(
                webhook_url,
                content=html_body,
                headers={"Content-Type": "text/plain"},
            )
            assert resp.status_code == 200
        await asyncio.sleep(1)
        result = await bounty.extract_links_from_request(token)
        assert result.success is True
        assert result.data["total_links"] >= 1

    @pytest.mark.asyncio
    async def test_extract_links_no_content(self, bounty_and_token):
        bounty, token, webhook_url = bounty_and_token
        async with httpx.AsyncClient() as session:
            resp = await session.post(
                webhook_url,
                content="just plain text with no links whatsoever",
                headers={"Content-Type": "text/plain"},
            )
            assert resp.status_code == 200
        await asyncio.sleep(1)
        result = await bounty.extract_links_from_request(token)
        assert result.success is True
        assert result.data["total_links"] == 0


class TestBugBountyIntegration:
    @pytest.mark.asyncio
    async def test_ssrf_detection_workflow(self, bounty_and_token):
        bounty, token, _url = bounty_and_token
        ssrf = bounty.generate_ssrf_payload(token, identifier="ssrf-test")
        assert ssrf.success is True
        webhook_url = ssrf.data["callback_payloads"]["https_url"]
        async with httpx.AsyncClient() as session:
            resp = await session.get(f"{webhook_url}&ssrf=success")
            assert resp.status_code == 200
        await asyncio.sleep(1)
        check = await bounty.check_for_callbacks(token, since_minutes=5)
        assert check.success is True
        assert check.data["detected"] is True
        assert check.data["total_callbacks"] >= 1

    @pytest.mark.asyncio
    async def test_canary_detection_workflow(self, bounty_and_token):
        bounty, token, _url = bounty_and_token
        canary = bounty.generate_canary_token(token, token_type="url", identifier="secret-doc")
        assert canary.success is True
        async with httpx.AsyncClient() as session:
            resp = await session.get(canary.data["canary"]["token"])
            assert resp.status_code == 200
        await asyncio.sleep(1)
        check = await bounty.check_for_callbacks(token, since_minutes=5)
        assert check.success is True
        assert check.data["detected"] is True
