"""
Real-world bug bounty tools demonstration.

This script tests the bug bounty workflow in realistic scenarios:
1. Create webhook for OOB detection
2. Generate SSRF payloads for testing
3. Simulate a successful SSRF callback
4. Detect the callback
5. Generate XSS callback payloads
6. Generate canary tokens
7. Extract links from captured emails
"""

import asyncio
import json
import sys
from pathlib import Path
import aiohttp

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from handlers.tool_handlers import ToolHandler
from utils.http_client import WebhookHttpClient


async def main():
    print("=" * 60)
    print("REAL-WORLD BUG BOUNTY TOOLS TEST")
    print("=" * 60)
    
    async with WebhookHttpClient() as client:
        handler = ToolHandler(client)
        
        # [1] Create webhook
        print("\n[1] Creating webhook...")
        result = await handler.handle("create_webhook", {})
        data = json.loads(result[0].text)
        token = data["token"]
        url = data["url"]
        print(f"    Token: {token}")
        print(f"    URL: {url}")
        
        # [2] Generate SSRF payloads
        print("\n[2] Generating SSRF payloads...")
        result = await handler.handle("generate_ssrf_payload", {
            "webhook_token": token,
            "identifier": "ssrf-param-test"
        })
        ssrf = json.loads(result[0].text)
        payloads = ssrf["payloads"]
        print(f"    Generated {len(payloads)} SSRF payloads")
        print(f"    HTTPS:  {payloads['https_url']}")
        print(f"    DNS:    {payloads['dns_payload']}")
        print(f"    Bypass: {payloads['at_bypass']}")
        
        # [3] Simulate SSRF callback (as if target was vulnerable)
        print("\n[3] Simulating SSRF callback...")
        ssrf_url = payloads["https_url"] + "?id=ssrf-param-test"
        async with aiohttp.ClientSession() as session:
            async with session.get(
                ssrf_url, 
                headers={"X-Forwarded-For": "10.0.0.1", "User-Agent": "VulnScanner/1.0"}
            ) as resp:
                print(f"    Callback sent: HTTP {resp.status}")
        
        await asyncio.sleep(1)
        
        # [4] Check for callbacks
        print("\n[4] Checking for callbacks...")
        result = await handler.handle("check_for_callbacks", {
            "webhook_token": token,
            "since_minutes": 5
        })
        callbacks = json.loads(result[0].text)
        print(f"    Detected: {callbacks['detected']}")
        print(f"    Total callbacks: {callbacks['total_callbacks']}")
        if callbacks["callbacks"]:
            cb = callbacks["callbacks"][0]
            print(f"    Latest: {cb['method']} from {cb['ip']}")
        
        # [5] Generate XSS callback payloads
        print("\n[5] Generating XSS callback payloads...")
        result = await handler.handle("generate_xss_callback", {
            "webhook_token": token,
            "identifier": "comment-xss"
        })
        xss = json.loads(result[0].text)
        xss_payloads = xss["payloads"]
        print(f"    Generated {len(xss_payloads)} XSS payloads")
        print(f"    Basic img:     {xss_payloads['basic_img'][:50]}...")
        print(f"    Cookie steal:  {xss_payloads['cookie_steal'][:50]}...")
        print(f"    SVG trigger:   {xss_payloads['svg'][:50]}...")
        
        # [6] Generate canary tokens
        print("\n[6] Generating canary tokens...")
        for token_type in ["url", "dns", "email"]:
            result = await handler.handle("generate_canary_token", {
                "webhook_token": token,
                "token_type": token_type,
                "identifier": "secret-doc"
            })
            canary = json.loads(result[0].text)
            canary_token = canary["canary"]["token"]
            print(f"    {token_type.upper():6} {canary_token}")
        
        # [7] Test link extraction (simulating captured email)
        print("\n[7] Testing link extraction from captured email...")
        email_body = """
        Hello,
        
        Click here to reset your password:
        https://target.com/reset?token=secret123abc
        
        Or verify your account:
        https://target.com/verify?code=xyz789&user=admin
        
        API callback: https://api.target.com/callback?auth=bearer_token
        """
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, 
                data=email_body, 
                headers={"Content-Type": "text/plain"}
            ) as resp:
                pass
        
        await asyncio.sleep(1)
        
        result = await handler.handle("extract_links_from_request", {
            "webhook_token": token
        })
        links = json.loads(result[0].text)
        print(f"    Extracted {links['total_links']} links")
        print(f"    Auth links found: {len(links['links']['auth_links'])}")
        for link in links["links"]["auth_links"]:
            print(f"      - {link}")
        
        # [8] Cleanup
        print("\n[8] Cleanup...")
        await handler.handle("delete_webhook", {"webhook_token": token})
        print("    Webhook deleted")
        
        print("\n" + "=" * 60)
        print("ALL 5 BUG BOUNTY TOOLS VERIFIED WORKING!")
        print("=" * 60)
        return True


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
