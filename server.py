#!/usr/bin/env python3
"""
Webhook.site MCP Server

A Model Context Protocol (MCP) server for interacting with webhook.site.
Provides tools for creating, managing, and monitoring webhooks.

Usage:
    python server.py
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server import MCPServer

from handlers.tools import register_tools
from models.app_context import AppContext
from services.account_service import AccountService
from services.actions_service import ActionsService
from services.bugbounty_service import BugBountyService
from services.database_service import DatabaseService
from services.request_service import RequestService
from services.schedule_service import ScheduleService
from services.webhook_service import WebhookService
from utils.http_client import WebhookHttpClient
from utils.safe_url import ALLOW_HOSTS_ENV, HostAllowList
from utils.validation import resolve_default_expiry

DEFAULT_EXPIRY_ENV = "WEBHOOK_SITE_DEFAULT_EXPIRY"


@asynccontextmanager
async def app_lifespan(_server: MCPServer[AppContext]) -> AsyncIterator[AppContext]:
    """Open one webhook.site HTTP client for the life of the process."""
    api_key = os.environ.get("WEBHOOK_SITE_API_KEY")
    follow_allowlist = HostAllowList.from_env(os.environ.get(ALLOW_HOSTS_ENV))
    default_expiry = resolve_default_expiry(os.environ.get(DEFAULT_EXPIRY_ENV))
    async with WebhookHttpClient(api_key=api_key) as client:
        yield AppContext(
            client=client,
            webhooks=WebhookService(client, default_expiry=default_expiry),
            requests=RequestService(client, follow_allowlist=follow_allowlist),
            bounty=BugBountyService(client),
            account=AccountService(client),
            actions=ActionsService(client),
            schedules=ScheduleService(client),
            databases=DatabaseService(client),
        )


mcp = MCPServer("webhook-site-mcp", lifespan=app_lifespan)
register_tools(mcp)


def run_server() -> None:
    """Synchronous entry point for the console script."""
    mcp.run()


if __name__ == "__main__":
    run_server()
