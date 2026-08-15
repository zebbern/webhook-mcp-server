"""Shared process-level services for MCP tool handlers."""

from __future__ import annotations

from dataclasses import dataclass

from services.bugbounty_service import BugBountyService
from services.request_service import RequestService
from services.webhook_service import WebhookService
from utils.http_client import WebhookHttpClient


@dataclass
class AppContext:
    """Lifespan state shared by every MCP tool call."""

    client: WebhookHttpClient
    webhooks: WebhookService
    requests: RequestService
    bounty: BugBountyService
