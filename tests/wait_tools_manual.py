"""Manual script for wait_for_request and wait_for_email. Not collected by pytest."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

from services.request_service import RequestService
from services.webhook_service import WebhookService
from utils.http_client import WebhookHttpClient


async def run_wait_tools() -> None:
    """Exercise wait_for_request and wait_for_email against webhook.site."""
    print("=" * 60)
    print("Testing wait_for_request and wait_for_email tools")
    print("=" * 60)

    async with WebhookHttpClient() as client:
        webhook_service = WebhookService(client)
        request_service = RequestService(client)

        print("\n[1] Creating webhook...")
        result = await webhook_service.create()
        if not result.success:
            print(f"Failed to create webhook: {result.message}")
            return

        token = result.data["token"]
        url = result.data["url"]
        email = f"{token}@email.webhook.site"
        print(f"    Token: {token}")
        print(f"    URL: {url}")
        print(f"    Email: {email}")

        print("\n[2] Testing wait_for_request (5 second timeout - should timeout)...")
        result = await request_service.wait_for_request(
            webhook_token=token,
            timeout_seconds=5,
        )
        print(f"    Success: {result.success}")
        print(f"    Message: {result.message}")

        print("\n[3] Testing wait_for_email (5 second timeout - should timeout)...")
        result = await request_service.wait_for_email(
            webhook_token=token,
            timeout_seconds=5,
            extract_links=True,
        )
        print(f"    Success: {result.success}")
        print(f"    Message: {result.message}")

        print("\n[4] Testing wait_for_request with an actual request...")

        async def wait_for_it():
            return await request_service.wait_for_request(
                webhook_token=token,
                timeout_seconds=30,
            )

        async def send_request():
            await asyncio.sleep(2)
            async with httpx.AsyncClient() as session:
                resp = await session.post(url, data={"test": "hello"})
                print(f"    Sent test request, status: {resp.status_code}")

        wait_task = asyncio.create_task(wait_for_it())
        send_task = asyncio.create_task(send_request())
        result = await wait_task
        await send_task

        print(f"\n    Wait result - Success: {result.success}")
        print(f"    Message: {result.message}")

        print("\n[5] Cleaning up...")
        await webhook_service.delete(token)
        print("    Webhook deleted")


if __name__ == "__main__":
    asyncio.run(run_wait_tools())
