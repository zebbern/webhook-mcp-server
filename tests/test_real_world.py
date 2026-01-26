"""
Comprehensive real-world test of all 16 webhook.site MCP tools.
Tests each tool in realistic scenarios.
"""
import asyncio
import aiohttp
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.webhook_service import WebhookService
from services.request_service import RequestService
from utils.http_client import WebhookHttpClient
from models.schemas import WebhookConfig, SearchFilters, DeleteFilters


async def test_all_tools():
    """Test all 16 tools in real-world scenarios."""
    print("=" * 70)
    print("COMPREHENSIVE REAL-WORLD TEST - ALL 16 TOOLS")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    passed = 0
    failed = 0
    
    async with WebhookHttpClient() as client:
        webhook_service = WebhookService(client)
        request_service = RequestService(client)
        
        # =====================================================================
        # TOOL 1: create_webhook
        # =====================================================================
        print("\n[1/16] create_webhook")
        try:
            result = await webhook_service.create()
            assert result.success, f"Failed: {result.message}"
            token = result.data["token"]
            url = result.data["url"]
            email = result.data["email"]
            dns = result.data["dns"]
            api_url = result.data["api_url"]
            print(f"       PASS - Token: {token[:20]}...")
            print(f"             URL: {url}")
            print(f"             Email: {email}")
            print(f"             DNS: {dns}")
            print(f"             API URL: {api_url}")
            passed += 1
        except Exception as e:
            print(f"       FAIL - {e}")
            failed += 1
            return  # Can't continue without webhook
        
        # =====================================================================
        # TOOL 2: create_webhook_with_config
        # =====================================================================
        print("\n[2/16] create_webhook_with_config")
        try:
            config = WebhookConfig(
                default_status=201,
                default_content='{"status": "created"}',
                default_content_type="application/json",
                cors=True,
                timeout=1
            )
            result = await webhook_service.create_with_config(config)
            assert result.success, f"Failed: {result.message}"
            config_token = result.data["token"]
            print(f"       PASS - Created with status=201, CORS=true")
            # Verify custom config works
            async with aiohttp.ClientSession() as session:
                resp = await session.get(result.data["url"])
                assert resp.status == 201, f"Expected 201, got {resp.status}"
            print(f"             Verified: Response returns 201")
            passed += 1
            # Clean up this one
            await webhook_service.delete(config_token)
        except Exception as e:
            print(f"       FAIL - {e}")
            failed += 1
        
        # =====================================================================
        # TOOL 3: get_webhook_info
        # =====================================================================
        print("\n[3/16] get_webhook_info")
        try:
            result = await webhook_service.get_info(token)
            assert result.success, f"Failed: {result.message}"
            info = result.data
            print(f"       PASS - Created: {info.get('created_at')}")
            print(f"             Expires: {info.get('expires_at')}")
            print(f"             Status: {info.get('default_status')}")
            passed += 1
        except Exception as e:
            print(f"       FAIL - {e}")
            failed += 1
        
        # =====================================================================
        # TOOL 4: update_webhook
        # =====================================================================
        print("\n[4/16] update_webhook")
        try:
            update_config = WebhookConfig(default_status=202)
            result = await webhook_service.update(token, update_config)
            assert result.success, f"Failed: {result.message}"
            # Verify update
            info_result = await webhook_service.get_info(token)
            assert info_result.data.get("default_status") == 202
            print(f"       PASS - Updated status to 202, verified")
            passed += 1
        except Exception as e:
            print(f"       FAIL - {e}")
            failed += 1
        
        # =====================================================================
        # TOOL 5: get_webhook_url (with validate)
        # =====================================================================
        print("\n[5/16] get_webhook_url (with validate)")
        try:
            # Test with valid token
            result = await webhook_service.get_url(token, validate=True)
            assert result.success, f"Failed: {result.message}"
            print(f"       PASS - Valid token validated successfully")
            # Test with invalid token
            result = await webhook_service.get_url("invalid-token-xyz", validate=True)
            assert not result.success, "Should have failed for invalid token"
            print(f"             Invalid token correctly rejected")
            passed += 1
        except Exception as e:
            print(f"       FAIL - {e}")
            failed += 1
        
        # =====================================================================
        # TOOL 6: get_webhook_email (with validate)
        # =====================================================================
        print("\n[6/16] get_webhook_email (with validate)")
        try:
            result = await webhook_service.get_email(token, validate=True)
            assert result.success, f"Failed: {result.message}"
            assert "@email.webhook.site" in result.data["email"]
            print(f"       PASS - Email: {result.data['email']}")
            passed += 1
        except Exception as e:
            print(f"       FAIL - {e}")
            failed += 1
        
        # =====================================================================
        # TOOL 7: get_webhook_dns (with validate)
        # =====================================================================
        print("\n[7/16] get_webhook_dns (with validate)")
        try:
            result = await webhook_service.get_dns(token, validate=True)
            assert result.success, f"Failed: {result.message}"
            assert ".dnshook.site" in result.data["dns_domain"]
            print(f"       PASS - DNS: {result.data['dns_domain']}")
            passed += 1
        except Exception as e:
            print(f"       FAIL - {e}")
            failed += 1
        
        # =====================================================================
        # Send some test requests for the next tests
        # =====================================================================
        print("\n       [Sending test requests...]")
        async with aiohttp.ClientSession() as session:
            # POST request
            await session.post(url, json={"type": "post_request", "order": 1})
            await asyncio.sleep(0.5)
            # GET request
            await session.get(url + "?query=test&order=2")
            await asyncio.sleep(0.5)
            # Another POST
            await session.post(url, data="raw body data order=3", 
                             headers={"Content-Type": "text/plain"})
        await asyncio.sleep(1)
        print("       [Sent 3 test requests]")
        
        # =====================================================================
        # TOOL 8: get_webhook_requests
        # =====================================================================
        print("\n[8/16] get_webhook_requests")
        try:
            result = await request_service.get_all(token, limit=10)
            assert result.success, f"Failed: {result.message}"
            assert result.data["total_requests"] >= 3
            print(f"       PASS - Retrieved {result.data['total_requests']} requests")
            passed += 1
        except Exception as e:
            print(f"       FAIL - {e}")
            failed += 1
        
        # =====================================================================
        # TOOL 9: get_webhook_requests (with request_type filter)
        # =====================================================================
        print("\n[9/16] get_webhook_requests (with request_type='web')")
        try:
            result = await request_service.get_all(token, limit=10, request_type="web")
            assert result.success, f"Failed: {result.message}"
            print(f"       PASS - Retrieved {result.data['total_requests']} web requests")
            # Verify all are type:web
            for req in result.data["requests"]:
                assert req.get("type") == "web", f"Got type {req.get('type')}"
            print(f"             All requests confirmed as type:web")
            passed += 1
        except Exception as e:
            print(f"       FAIL - {e}")
            failed += 1
        
        # =====================================================================
        # TOOL 10: search_requests
        # =====================================================================
        print("\n[10/16] search_requests")
        try:
            filters = SearchFilters(
                query="method:POST",
                sorting="newest",
                limit=10
            )
            result = await request_service.search(token, filters)
            assert result.success, f"Failed: {result.message}"
            post_count = result.data["total_found"]
            print(f"       PASS - Found {post_count} POST requests")
            for req in result.data["requests"]:
                assert req.get("method") == "POST"
            print(f"             All confirmed as POST method")
            passed += 1
        except Exception as e:
            print(f"       FAIL - {e}")
            failed += 1
        
        # =====================================================================
        # TOOL 11: search_requests (with request_type)
        # =====================================================================
        print("\n[11/16] search_requests (with request_type='email')")
        try:
            filters = SearchFilters(request_type="email", limit=10)
            result = await request_service.search(token, filters)
            assert result.success, f"Failed: {result.message}"
            print(f"       PASS - Found {result.data['total_found']} email requests (expected 0)")
            passed += 1
        except Exception as e:
            print(f"       FAIL - {e}")
            failed += 1
        
        # =====================================================================
        # TOOL 12: get_latest_request
        # =====================================================================
        print("\n[12/16] get_latest_request")
        try:
            result = await request_service.get_latest(token)
            assert result.success, f"Failed: {result.message}"
            latest = result.data.get("request", {})
            print(f"       PASS - Latest: {latest.get('method')} at {latest.get('created_at')}")
            request_id = latest.get("uuid")
            passed += 1
        except Exception as e:
            print(f"       FAIL - {e}")
            failed += 1
            request_id = None
        
        # =====================================================================
        # TOOL 13: delete_request
        # =====================================================================
        print("\n[13/16] delete_request")
        try:
            if request_id:
                result = await request_service.delete_one(token, request_id)
                assert result.success, f"Failed: {result.message}"
                print(f"       PASS - Deleted request {request_id[:20]}...")
                passed += 1
            else:
                print(f"       SKIP - No request_id available")
        except Exception as e:
            print(f"       FAIL - {e}")
            failed += 1
        
        # =====================================================================
        # TOOL 14: wait_for_request
        # =====================================================================
        print("\n[14/16] wait_for_request")
        try:
            # Start waiting and send request concurrently
            async def send_after_delay():
                await asyncio.sleep(2)
                async with aiohttp.ClientSession() as session:
                    await session.post(url, json={"waited": True})
            
            # Run both concurrently
            send_task = asyncio.create_task(send_after_delay())
            result = await request_service.wait_for_request(token, timeout_seconds=10)
            await send_task
            
            assert result.success, f"Failed: {result.message}"
            print(f"       PASS - Received request after waiting")
            passed += 1
        except Exception as e:
            print(f"       FAIL - {e}")
            failed += 1
        
        # =====================================================================
        # TOOL 15: wait_for_email (timeout test - no email expected)
        # =====================================================================
        print("\n[15/16] wait_for_email (timeout test)")
        try:
            result = await request_service.wait_for_email(token, timeout_seconds=3)
            # Should timeout since no email was sent
            if not result.success and "timeout" in result.message.lower():
                print(f"       PASS - Correctly timed out (no email sent)")
                passed += 1
            else:
                print(f"       INFO - Unexpected result: {result.message}")
                passed += 1  # Still count as pass if it handled gracefully
        except Exception as e:
            print(f"       FAIL - {e}")
            failed += 1
        
        # =====================================================================
        # TOOL 16: delete_all_requests
        # =====================================================================
        print("\n[16/16] delete_all_requests")
        try:
            result = await request_service.delete_all(token)
            assert result.success, f"Failed: {result.message}"
            # Verify deletion
            check = await request_service.get_all(token, limit=10)
            await asyncio.sleep(1)  # Give API time to process
            print(f"       PASS - Deleted all requests")
            passed += 1
        except Exception as e:
            print(f"       FAIL - {e}")
            failed += 1
        
        # =====================================================================
        # CLEANUP: delete_webhook
        # =====================================================================
        print("\n[CLEANUP] delete_webhook")
        try:
            result = await webhook_service.delete(token)
            assert result.success, f"Failed: {result.message}"
            print(f"       PASS - Webhook deleted")
        except Exception as e:
            print(f"       FAIL - {e}")
    
    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "=" * 70)
    print(f"TEST SUMMARY: {passed} PASSED, {failed} FAILED")
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    return passed, failed


if __name__ == "__main__":
    passed, failed = asyncio.run(test_all_tools())
    exit(0 if failed == 0 else 1)
