"""Schedules: webhook.site sends a request to any URL on an interval or cron expression."""

from __future__ import annotations

from typing import Any

from models.schemas import ToolResult
from utils.http_client import WebhookHttpClient

SCHEDULE_FIELDS = (
    "name",
    "interval",
    "cron",
    "request_url",
    "request_method",
    "request_body",
    "request_headers",
    "timeout",
    "require_body",
    "require_status_min",
    "require_status_max",
)


class ScheduleService:
    """CRUD, run-now and logs for account schedules."""

    def __init__(self, client: WebhookHttpClient) -> None:
        self._client = client

    @staticmethod
    def _payload(fields: dict[str, Any]) -> dict[str, Any]:
        return {key: fields[key] for key in SCHEDULE_FIELDS if fields.get(key) is not None}

    async def list(self, page: int = 1, max_items: int = 200) -> ToolResult:
        items, pagination = await self._client.paginate(
            "/schedules", {"page": page, "per_page": 50}, max_items=max_items
        )
        return ToolResult(
            success=True,
            message=f"Retrieved {len(items)} schedules",
            data={"schedules": items, "pagination": pagination},
        )

    async def get(self, schedule_id: int) -> ToolResult:
        schedule = await self._client.get(f"/schedules/{schedule_id}")
        return ToolResult(success=True, message="Schedule retrieved", data={"schedule": schedule})

    async def create(self, **fields: Any) -> ToolResult:
        response = await self._client.post("/schedules", json_data=self._payload(fields))
        schedule = response.json()
        return ToolResult(
            success=True,
            message=f"Schedule '{schedule.get('name')}' created",
            data={"schedule": schedule},
        )

    async def update(self, schedule_id: int, **fields: Any) -> ToolResult:
        # PUT replaces the schedule (interval and request_url are always required),
        # so merge the change into the saved schedule.
        current = await self._client.get(f"/schedules/{schedule_id}")
        merged = {key: current.get(key) for key in SCHEDULE_FIELDS}
        merged.update({key: value for key, value in fields.items() if value is not None})
        schedule = await self._client.put(f"/schedules/{schedule_id}", json_data=self._payload(merged))
        return ToolResult(success=True, message="Schedule updated", data={"schedule": schedule})

    async def delete(self, schedule_id: int) -> ToolResult:
        status = await self._client.delete(f"/schedules/{schedule_id}")
        return ToolResult(
            success=status in (200, 204),
            message=f"Schedule {schedule_id} deleted",
            data={"id": schedule_id, "status_code": status},
        )

    async def run_now(self, schedule_id: int) -> ToolResult:
        # This is a web route: it answers with a redirect to the schedule's log page.
        response = await self._client.post(f"/schedules/{schedule_id}/run-now", allow_redirect=True)
        return ToolResult(
            success=True,
            message=f"Schedule {schedule_id} triggered; read the outcome with action='logs'",
            data={
                "id": schedule_id,
                "status_code": response.status_code,
                "logs_url": response.headers.get("location"),
            },
        )

    async def logs(self, schedule_id: int, sorting: str = "newest", page: int = 1) -> ToolResult:
        data = await self._client.get(
            f"/schedules/{schedule_id}/logs",
            params={"sorting": sorting, "page": page},
            accept="application/json",
        )
        logs = data.get("data", [])
        return ToolResult(
            success=True,
            message=f"Retrieved {len(logs)} log entries",
            data={
                "id": schedule_id,
                "logs": logs,
                "pagination": {
                    "total": data.get("total"),
                    "current_page": data.get("current_page"),
                    "last_page": data.get("last_page"),
                },
            },
        )
