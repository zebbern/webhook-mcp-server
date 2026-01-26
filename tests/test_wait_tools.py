"""
Test the new wait_for_request and wait_for_email tools.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.http_client import WebhookHttpClient
from services.webhook_service import WebhookService
from services.request_service import RequestService


async def test_wait_tools():
    """Test the wait_for_request and wait_for_email tools."""
    print("=" * 60)
    print("Testing wait_for_request and wait_for_email tools")
    print("=" * 60)
    
    async with WebhookHttpClient() as client:
        webhook_service = WebhookService(client)
        request_service = RequestService(client)
        
        # Create a webhook for testing
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
        
        # Test 1: wait_for_request with short timeout (should timeout)
        print("\n[2] Testing wait_for_request (5 second timeout - should timeout)...")
        result = await request_service.wait_for_request(
            webhook_token=token,
            timeout_seconds=5,
        )
        print(f"    Success: {result.success}")
        print(f"    Message: {result.message}")
        if result.success:
            print("    UNEXPECTED: Got a request when none was sent!")
        else:
            if "timeout" in result.message.lower() or "timed out" in result.message.lower():
                print("    [PASS] Correctly timed out as expected")
            else:
                print(f"    [INFO] Error: {result.message}")
        
        # Test 2: wait_for_email with short timeout (should timeout)
        print("\n[3] Testing wait_for_email (5 second timeout - should timeout)...")
        result = await request_service.wait_for_email(
            webhook_token=token,
            timeout_seconds=5,
            extract_links=True,
        )
        print(f"    Success: {result.success}")
        print(f"    Message: {result.message}")
        if result.success:
            print("    UNEXPECTED: Got an email when none was sent!")
        else:
            if "timeout" in result.message.lower() or "timed out" in result.message.lower():
                print("    [PASS] Correctly timed out as expected")
            else:
                print(f"    [INFO] Error: {result.message}")
        
        # Now let's send an actual request and try to receive it
        print("\n[4] Testing wait_for_request with actual request...")
        print(f"    In another terminal, run: curl -X POST {url} -d 'test=data'")
        print("    Waiting 30 seconds for a request...")
        
        # Start the wait in background
        async def wait_for_it():
            return await request_service.wait_for_request(
                webhook_token=token,
                timeout_seconds=30,
            )
        
        # Also send a request after 2 seconds
        async def send_request():
            await asyncio.sleep(2)
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data={"test": "hello"}) as resp:
                    print(f"    Sent test request, status: {resp.status}")
        
        # Run both concurrently
        wait_task = asyncio.create_task(wait_for_it())
        send_task = asyncio.create_task(send_request())
        
        result = await wait_task
        await send_task
        
        print(f"\n    Wait result - Success: {result.success}")
        print(f"    Message: {result.message}")
        if result.success and result.data:
            print(f"    Request received!")
            req = result.data.get("request", {})
            print(f"    --- Full Request Details ---")
            print(f"    UUID: {req.get('uuid', 'N/A')}")
            print(f"    Type: {req.get('type', 'N/A')}")
            print(f"    Method: {req.get('method', 'N/A')}")
            print(f"    URL: {req.get('url', 'N/A')}")
            print(f"    IP: {req.get('ip', 'N/A')}")
            print(f"    Created At: {req.get('created_at', 'N/A')}")
            print(f"    Content: {req.get('content', 'N/A')}")
            print(f"    Query: {req.get('query', 'N/A')}")
            print(f"    --- Headers ---")
            headers = req.get('headers', {})
            if headers:
                for key, value in headers.items():
                    print(f"    {key}: {value}")
        
        # Cleanup
        print("\n[5] Cleaning up...")
        await webhook_service.delete(token)
        print("    Webhook deleted")
        
        print("\n" + "=" * 60)
        print("Test complete!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_wait_tools())
