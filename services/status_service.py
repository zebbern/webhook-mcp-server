"""Diagnostics: answer "why doesn't X work?" in one call."""

from __future__ import annotations

import importlib.metadata
import os
import uuid
from typing import Any

from models.schemas import ToolResult
from utils.http_client import RATE_LIMIT_MAX_WAIT_ENV, WebhookApiError, WebhookHttpClient
from utils.realtime import SocketFactory, SocketWaiter
from utils.safe_url import ALLOW_HOSTS_ENV, HostAllowList


def _version() -> str:
    try:
        return importlib.metadata.version("webhook-mcp-server")
    except importlib.metadata.PackageNotFoundError:
        return "unknown (not installed as a package)"


class StatusService:
    """Report configuration, API reachability, plan hints and socket availability."""

    def __init__(
        self,
        client: WebhookHttpClient,
        follow_allowlist: HostAllowList | None = None,
        default_expiry: int | None = None,
        socket_factory: SocketFactory | None = None,
    ) -> None:
        self._client = client
        self._allowlist = follow_allowlist or HostAllowList()
        self._default_expiry = default_expiry
        self._socket_factory = socket_factory

    async def report(self, check_socket: bool = True) -> ToolResult:
        key_set = bool(self._client.api_key)
        report: dict[str, Any] = {
            "version": _version(),
            "api_key_set": key_set,
            "default_expiry_seconds": self._default_expiry,
            "follow_email_link_allow_hosts": {
                "hosts": sorted(self._allowlist.hosts),
                "suffixes": ["*" + suffix for suffix in self._allowlist.suffixes],
                "networks": [str(network) for network in self._allowlist.networks],
            },
            "proxy_env": {
                name: bool(os.environ.get(name) or os.environ.get(name.lower()))
                for name in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "NO_PROXY")
            },
            "rate_limit_max_wait_seconds": self._client.rate_limit_max_wait,
            "env_vars": ["WEBHOOK_SITE_API_KEY", "WEBHOOK_SITE_DEFAULT_EXPIRY", ALLOW_HOSTS_ENV, RATE_LIMIT_MAX_WAIT_ENV],
        }

        # Reachability + account: the token list needs a key; anonymous mode is confirmed by
        # a GET on a random token id, which webhook.site answers with 404.
        if key_set:
            try:
                page = await self._client.get("/token", params={"per_page": 1})
                tokens = page.get("data") or []
                report["account"] = {
                    "reachable": True,
                    "authenticated": True,
                    "tokens_seen": len(tokens),
                    "premium_urls": bool(tokens and tokens[0].get("premium")),
                }
            except WebhookApiError as exc:
                report["account"] = {
                    "reachable": exc.status_code is not None,
                    "authenticated": exc.status_code not in (401, 403),
                    "error": str(exc),
                }
        else:
            try:
                await self._client.get(f"/token/{uuid.uuid4()}")
                report["account"] = {"reachable": True, "authenticated": False}
            except WebhookApiError as exc:
                if exc.status_code == 404:
                    report["account"] = {"reachable": True, "authenticated": False}
                else:
                    report["account"] = {"reachable": exc.status_code is not None, "authenticated": False, "error": str(exc)}

        if check_socket:
            waiter = SocketWaiter(str(uuid.uuid4()), self._client.api_key, factory=self._socket_factory)
            connected = await waiter.start(timeout=5)
            await waiter.close()
            report["realtime_socket"] = "connected" if connected else "unavailable (wait tools fall back to polling)"

        problems = []
        if not key_set:
            problems.append("No WEBHOOK_SITE_API_KEY: URLs expire after 7 days and account tools (list_webhooks, manage_*) return 401.")
        if key_set and not report["account"].get("authenticated", True):
            problems.append("The API rejected WEBHOOK_SITE_API_KEY.")
        if not report["account"].get("reachable", False):
            problems.append("webhook.site is not reachable from this server (network, proxy or DNS).")
        report["problems"] = problems
        return ToolResult(
            success=not problems,
            message="Server ready" if not problems else "; ".join(problems),
            data=report,
        )
