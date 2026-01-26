"""
Integration test for the complete MCP server.

Tests the full flow from server.py through all layers.
"""

from __future__ import annotations

import asyncio
import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.http_client import WebhookHttpClient, WEBHOOK_SITE_API


class TestIntegration:
    """Integration tests for webhook.site API operations."""
    
    @pytest.mark.asyncio
    async def test_full_webhook_lifecycle(self):
        """Test complete webhook lifecycle: create, send, get, delete."""
        async with WebhookHttpClient() as client:
            # 1. Create webhook
            response = await client.post("/token")
            response.raise_for_status()
            data = response.json()
            token = data["uuid"]
            
            assert token is not None
            print(f"Created webhook: {token}")
            
            # 2. Send data
            send_response = await client.post(
                f"/{token}",
                json_data={"test": "integration", "value": 123},
            )
            assert send_response.status_code == 200
            print("Sent test data")
            
            # Wait for data to be available (API eventual consistency)
            await asyncio.sleep(3)
            
            # 3. Get requests
            requests_data = await client.get(
                f"/token/{token}/requests",
                params={"per_page": 10},
            )
            assert len(requests_data.get("data", [])) >= 1
            print(f"Retrieved {len(requests_data['data'])} requests")
            
            # 4. Get webhook info
            info = await client.get(f"/token/{token}")
            assert info["uuid"] == token
            print("Retrieved webhook info")
            
            # 5. Update webhook
            update_data = await client.put(
                f"/token/{token}",
                json_data={"default_status": 201},
            )
            assert update_data["default_status"] == 201
            print("Updated webhook settings")
            
            # 6. Delete requests
            delete_status = await client.delete(f"/token/{token}/request")
            assert delete_status in [200, 204]
            print("Deleted all requests")
            
            # 7. Delete webhook
            delete_status = await client.delete(f"/token/{token}")
            assert delete_status in [200, 204]
            print("Deleted webhook")
            
            print("\n[PASS] Full lifecycle test passed!")
    
    @pytest.mark.asyncio
    async def test_search_functionality(self):
        """Test search with various query types."""
        async with WebhookHttpClient() as client:
            # Create webhook
            response = await client.post("/token")
            response.raise_for_status()
            token = response.json()["uuid"]
            
            try:
                # Send various requests
                await client.post(f"/{token}", json_data={"type": "order", "id": 1})
                await asyncio.sleep(0.2)
                await client.post(f"/{token}", json_data={"type": "user", "id": 2})
                await asyncio.sleep(0.2)
                await client.post(f"/{token}", json_data={"type": "order", "id": 3})
                await asyncio.sleep(0.5)
                
                # Search for 'order' type
                results = await client.get(
                    f"/token/{token}/requests",
                    params={"query": "content:order"},
                )
                
                # Should find matches
                assert "data" in results
                print(f"Search found {len(results['data'])} results for 'order'")
                
            finally:
                # Cleanup
                await client.delete(f"/token/{token}")
    
    @pytest.mark.asyncio
    async def test_custom_response_configuration(self):
        """Test webhook with custom response configuration."""
        async with WebhookHttpClient() as client:
            # Create webhook with custom config
            response = await client.post(
                "/token",
                json_data={
                    "default_status": 201,
                    "default_content": '{"created": true}',
                    "default_content_type": "application/json",
                    "cors": True,
                },
            )
            response.raise_for_status()
            data = response.json()
            token = data["uuid"]
            
            try:
                assert data["default_status"] == 201
                assert data["cors"] is True
                print("Custom webhook created with configuration")
                
                # Verify the custom response
                test_response = await client.post(
                    f"/{token}",
                    json_data={"test": "custom"},
                )
                assert test_response.status_code == 201
                print(f"Received custom status: {test_response.status_code}")
                
            finally:
                await client.delete(f"/token/{token}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
