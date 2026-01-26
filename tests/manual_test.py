"""
Manual comprehensive test of all 14 MCP tools.
This script tests each tool against the real webhook.site API.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.http_client import WebhookHttpClient, WEBHOOK_SITE_API
from services.webhook_service import WebhookService
from services.request_service import RequestService
from models.schemas import WebhookConfig, SearchFilters, DeleteFilters


def print_result(tool_name: str, result, expected_success: bool = True):
    """Print test result with pass/fail status."""
    status = "[PASS]" if result.success == expected_success else "[FAIL]"
    print(f"{status} {tool_name}")
    if not result.success == expected_success:
        print(f"       Expected success={expected_success}, got success={result.success}")
        print(f"       Message: {result.message}")
    return result.success == expected_success


async def run_comprehensive_test():
    """Run comprehensive test of all 14 tools."""
    print("=" * 60)
    print("COMPREHENSIVE MANUAL TEST - All 14 MCP Tools")
    print("=" * 60)
    print()
    
    passed = 0
    failed = 0
    token = None
    
    async with WebhookHttpClient() as client:
        webhook_service = WebhookService(client)
        request_service = RequestService(client)
        
        # =====================================================================
        # TOOL 1: create_webhook
        # =====================================================================
        print("[1/14] Testing create_webhook...")
        result = await webhook_service.create()
        if print_result("create_webhook", result):
            passed += 1
            token = result.data["token"]
            print(f"       Token: {token}")
            print(f"       URL: {result.data['url']}")
        else:
            failed += 1
            print("       FATAL: Cannot continue without token")
            return
        
        # =====================================================================
        # TOOL 2: create_webhook_with_config
        # =====================================================================
        print("\n[2/14] Testing create_webhook_with_config...")
        config = WebhookConfig(
            default_status=201,
            default_content='{"status": "created"}',
            default_content_type="application/json",
            cors=True,
            timeout=2,
        )
        result = await webhook_service.create_with_config(config)
        if print_result("create_webhook_with_config", result):
            passed += 1
            token2 = result.data["token"]
            print(f"       Configured token: {token2}")
            print(f"       Status: {result.data['default_status']}")
            print(f"       CORS: {result.data['cors']}")
            # Delete this extra token
            await webhook_service.delete(token2)
        else:
            failed += 1
        
        # =====================================================================
        # TOOL 12: get_webhook_url
        # =====================================================================
        print("\n[12/14] Testing get_webhook_url...")
        result = webhook_service.get_url(token)
        if print_result("get_webhook_url", result):
            passed += 1
            expected_url = f"{WEBHOOK_SITE_API}/{token}"
            if result.data["url"] == expected_url:
                print(f"       URL correct: {result.data['url']}")
            else:
                print(f"       URL MISMATCH: got {result.data['url']}, expected {expected_url}")
                failed += 1
                passed -= 1
        else:
            failed += 1
        
        # =====================================================================
        # TOOL 13: get_webhook_email
        # =====================================================================
        print("\n[13/14] Testing get_webhook_email...")
        result = webhook_service.get_email(token)
        if print_result("get_webhook_email", result):
            passed += 1
            expected_email = f"{token}@email.webhook.site"
            if result.data["email"] == expected_email:
                print(f"       Email correct: {result.data['email']}")
            else:
                print(f"       Email MISMATCH: got {result.data['email']}")
                failed += 1
                passed -= 1
        else:
            failed += 1
        
        # =====================================================================
        # TOOL 14: get_webhook_dns
        # =====================================================================
        print("\n[14/14] Testing get_webhook_dns...")
        result = webhook_service.get_dns(token)
        if print_result("get_webhook_dns", result):
            passed += 1
            expected_dns = f"{token}.dnshook.site"
            if result.data["dns_domain"] == expected_dns:
                print(f"       DNS domain correct: {result.data['dns_domain']}")
                print(f"       Example subdomain: {result.data['example_subdomain']}")
            else:
                print(f"       DNS MISMATCH: got {result.data['dns_domain']}")
                failed += 1
                passed -= 1
        else:
            failed += 1
        
        # =====================================================================
        # TOOL 3: send_to_webhook
        # =====================================================================
        print("\n[3/14] Testing send_to_webhook...")
        test_data = {"event": "test", "value": 42, "nested": {"key": "value"}}
        result = await webhook_service.send_data(token, test_data)
        if print_result("send_to_webhook", result):
            passed += 1
            print(f"       Status code: {result.data['status_code']}")
            print(f"       Data sent: {result.data['data_sent']}")
        else:
            failed += 1
        
        # Wait for data propagation
        print("\n       Waiting 3s for API propagation...")
        await asyncio.sleep(3)
        
        # =====================================================================
        # TOOL 4: get_webhook_requests
        # =====================================================================
        print("\n[4/14] Testing get_webhook_requests...")
        result = await request_service.get_all(token, limit=10)
        if print_result("get_webhook_requests", result):
            passed += 1
            request_count = result.data.get("count", 0)
            print(f"       Found {request_count} request(s)")
            if request_count > 0:
                first_req = result.data["requests"][0]
                print(f"       First request method: {first_req['method']}")
                print(f"       First request content preview: {str(first_req.get('content', ''))[:50]}...")
        else:
            failed += 1
        
        # =====================================================================
        # TOOL 6: get_latest_request
        # =====================================================================
        print("\n[6/14] Testing get_latest_request...")
        result = await request_service.get_latest(token)
        if print_result("get_latest_request", result):
            passed += 1
            print(f"       Method: {result.data.get('method')}")
            print(f"       Created at: {result.data.get('created_at')}")
        else:
            failed += 1
        
        # Send another request for search testing
        await webhook_service.send_data(token, {"search_test": True, "keyword": "findme"})
        await asyncio.sleep(2)
        
        # =====================================================================
        # TOOL 5: search_requests
        # =====================================================================
        print("\n[5/14] Testing search_requests...")
        filters = SearchFilters(query="content:findme", limit=10)
        result = await request_service.search(token, filters)
        if print_result("search_requests", result):
            passed += 1
            print(f"       Search results: {result.data.get('count', 0)} match(es)")
        else:
            failed += 1
        
        # =====================================================================
        # TOOL 7: get_webhook_info
        # =====================================================================
        print("\n[7/14] Testing get_webhook_info...")
        result = await webhook_service.get_info(token)
        if print_result("get_webhook_info", result):
            passed += 1
            print(f"       Token: {result.data['token']}")
            print(f"       Created: {result.data['created_at']}")
            print(f"       Expires: {result.data['expires_at']}")
            print(f"       Default status: {result.data['default_status']}")
        else:
            failed += 1
        
        # =====================================================================
        # TOOL 8: update_webhook
        # =====================================================================
        print("\n[8/14] Testing update_webhook...")
        update_config = WebhookConfig(
            default_status=202,
            default_content="Updated content",
            cors=True,
        )
        result = await webhook_service.update(token, update_config)
        if print_result("update_webhook", result):
            passed += 1
            print(f"       Updated status: {result.data.get('default_status')}")
        else:
            failed += 1
        
        # Verify update worked
        verify_result = await webhook_service.get_info(token)
        if verify_result.data.get("default_status") == 202:
            print("       Verified: status is now 202")
        else:
            print(f"       WARNING: status is {verify_result.data.get('default_status')}, expected 202")
        
        # Get a request ID for deletion test
        requests_result = await request_service.get_all(token, limit=1)
        request_id = None
        if requests_result.data.get("requests"):
            request_id = requests_result.data["requests"][0]["uuid"]
        
        # =====================================================================
        # TOOL 10: delete_request
        # =====================================================================
        print("\n[10/14] Testing delete_request...")
        if request_id:
            result = await request_service.delete_one(token, request_id)
            if print_result("delete_request", result):
                passed += 1
                print(f"       Deleted request: {request_id[:8]}...")
            else:
                failed += 1
        else:
            print("       SKIP: No request ID available")
            failed += 1
        
        # =====================================================================
        # TOOL 11: delete_all_requests
        # =====================================================================
        print("\n[11/14] Testing delete_all_requests...")
        result = await request_service.delete_all(token)
        if print_result("delete_all_requests", result):
            passed += 1
            print(f"       Status: {result.data.get('status_code')}")
        else:
            failed += 1
        
        # =====================================================================
        # TOOL 9: delete_webhook
        # =====================================================================
        print("\n[9/14] Testing delete_webhook...")
        result = await webhook_service.delete(token)
        if print_result("delete_webhook", result):
            passed += 1
            print(f"       Webhook {token[:8]}... deleted")
        else:
            failed += 1
        
        # Verify deletion - should fail to get info
        print("       Verifying deletion...")
        try:
            verify_result = await webhook_service.get_info(token)
            if not verify_result.success:
                print("       Verified: webhook no longer accessible")
            else:
                print("       WARNING: webhook still accessible after deletion")
        except Exception:
            print("       Verified: webhook no longer accessible (exception)")
    
    # =========================================================================
    # SUMMARY
    # =========================================================================
    print()
    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    
    if failed == 0:
        print("\nALL TESTS PASSED! All 14 tools working correctly.")
    else:
        print(f"\n{failed} test(s) failed. Review output above.")
    
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_comprehensive_test())
    sys.exit(0 if success else 1)
