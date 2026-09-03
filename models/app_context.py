"""Shared process-level services for MCP tool handlers."""

from __future__ import annotations

from dataclasses import dataclass

from services.account_service import AccountService
from services.actions_service import ActionsService
from services.bugbounty_service import BugBountyService
from services.database_service import DatabaseService
from services.request_service import RequestService
from services.schedule_service import ScheduleService
from services.webhook_service import WebhookService
from utils.http_client import WebhookHttpClient


@dataclass
class AppContext:
    """Lifespan state shared by every MCP tool call."""

    client: WebhookHttpClient
    webhooks: WebhookService
    requests: RequestService
    bounty: BugBountyService
    account: AccountService
    actions: ActionsService
    schedules: ScheduleService
    databases: DatabaseService
