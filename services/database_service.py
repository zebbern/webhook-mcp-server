"""Webhook.site Databases: hosted SQL storage usable from Custom Actions and the API."""

from __future__ import annotations

from typing import Any

from models.schemas import ToolResult
from utils.http_client import WebhookHttpClient


class DatabaseService:
    """List, create, update, delete and query account databases."""

    def __init__(self, client: WebhookHttpClient) -> None:
        self._client = client

    async def list(self, page: int = 1, max_items: int = 200) -> ToolResult:
        items, pagination = await self._client.paginate(
            "/databases", {"page": page, "per_page": 50}, max_items=max_items
        )
        return ToolResult(
            success=True,
            message=f"Retrieved {len(items)} databases",
            data={"databases": items, "pagination": pagination},
        )

    async def create(self, name: str, plan: str, group_id: int | None = None) -> ToolResult:
        payload: dict[str, Any] = {"name": name, "plan": plan}
        if group_id is not None:
            payload["group_id"] = group_id
        response = await self._client.post("/databases", json_data=payload)
        database = response.json()
        return ToolResult(success=True, message=f"Database '{name}' created", data={"database": database})

    async def update(self, database_id: str, name: str | None = None, group_id: int | None = None) -> ToolResult:
        # The API requires name and plan on every PUT and rejects a null group_id.
        items, _ = await self._client.paginate("/databases", {"per_page": 50}, max_items=500, delay=0)
        current = next((item for item in items if str(item.get("id")) == str(database_id)), {})
        payload: dict[str, Any] = {
            "name": name if name is not None else current.get("name"),
            "plan": current.get("plan", "db-s"),
        }
        chosen_group = group_id if group_id is not None else current.get("group_id")
        if chosen_group is not None:
            payload["group_id"] = chosen_group
        database = await self._client.put(f"/databases/{database_id}", json_data=payload)
        return ToolResult(success=True, message="Database updated", data={"database": database})

    async def delete(self, database_id: str) -> ToolResult:
        status = await self._client.delete(f"/databases/{database_id}")
        return ToolResult(
            success=status in (200, 204),
            message=f"Database {database_id} deleted",
            data={"id": database_id, "status_code": status},
        )

    async def query(
        self,
        database_id: str,
        query: str,
        params: list[Any] | dict[str, Any] | None = None,
    ) -> ToolResult:
        payload: dict[str, Any] = {"query": query}
        if params is not None:
            payload["params"] = params
        response = await self._client.post(f"/databases/{database_id}/query", json_data=payload)
        body = response.json()
        error = body.get("error")
        rows = body.get("result") or []
        return ToolResult(
            success=error is None,
            message=f"Query returned {len(rows)} rows" if error is None else f"Query failed: {error}",
            data={
                "id": database_id,
                "result": rows,
                "error": error,
                "time_ms": body.get("time"),
            },
        )
