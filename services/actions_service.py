"""Custom Actions on a token: the workflow steps webhook.site runs on each request or email."""

from __future__ import annotations

from typing import Any

from models.schemas import ToolResult
from utils.http_client import WebhookHttpClient


def _action_payload(
    type: str | None,
    order: int | None,
    parameters: dict[str, Any] | None,
    disabled: bool | None,
    queue: bool | None,
    delay: int | None,
    condition: str | None,
    queue_id: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": type,
        "order": order,
        "parameters": parameters,
        "disabled": disabled,
        "queue": queue,
        "delay": delay,
        "condition": condition,
        "queue_id": queue_id,  # Queue Profile to throttle queued runs (verified live)
    }
    return {key: value for key, value in payload.items() if value is not None}


class ActionsService:
    """List, create, update, delete, test and replay Custom Actions."""

    def __init__(self, client: WebhookHttpClient) -> None:
        self._client = client

    async def list(self, webhook_token: str) -> ToolResult:
        data = await self._client.get(f"/token/{webhook_token}/actions")
        actions = data.get("data", data if isinstance(data, list) else [])
        return ToolResult(
            success=True,
            message=f"Retrieved {len(actions)} custom actions",
            data={"actions": actions},
        )

    async def create(
        self,
        webhook_token: str,
        type: str,
        parameters: dict[str, Any] | None = None,
        order: int | None = None,
        disabled: bool | None = None,
        queue: bool | None = None,
        delay: int | None = None,
        condition: str | None = None,
        queue_id: int | None = None,
    ) -> ToolResult:
        payload = _action_payload(type, order, parameters or {}, disabled, queue, delay, condition, queue_id)
        response = await self._client.post(f"/token/{webhook_token}/actions", json_data=payload)
        action = response.json()
        return ToolResult(
            success=True,
            message=f"Custom action '{type}' created",
            data={"action": action},
        )

    async def update(
        self,
        webhook_token: str,
        action_id: str,
        type: str | None = None,
        parameters: dict[str, Any] | None = None,
        order: int | None = None,
        disabled: bool | None = None,
        queue: bool | None = None,
        delay: int | None = None,
        condition: str | None = None,
        queue_id: int | None = None,
    ) -> ToolResult:
        # The API replaces the whole action on PUT (a partial body is a 422), so
        # merge the requested changes into the saved action first.
        current = await self._find(webhook_token, action_id)
        payload = _action_payload(
            type if type is not None else current.get("type"),
            order if order is not None else current.get("order"),
            parameters if parameters is not None else current.get("parameters"),
            disabled if disabled is not None else current.get("disabled"),
            queue if queue is not None else current.get("queue"),
            delay if delay is not None else current.get("delay"),
            condition if condition is not None else current.get("condition"),
            queue_id if queue_id is not None else current.get("queue_id"),
        )
        action = await self._client.put(f"/token/{webhook_token}/actions/{action_id}", json_data=payload)
        return ToolResult(success=True, message="Custom action updated", data={"action": action})

    async def _find(self, webhook_token: str, action_id: str) -> dict[str, Any]:
        data = await self._client.get(f"/token/{webhook_token}/actions")
        actions = data.get("data", data if isinstance(data, list) else [])
        for action in actions:
            if action.get("uuid") == action_id:
                return action
        return {}

    async def delete(self, webhook_token: str, action_id: str) -> ToolResult:
        status = await self._client.delete(f"/token/{webhook_token}/actions/{action_id}")
        return ToolResult(
            success=status in (200, 204),
            message="Custom action deleted",
            data={"action_id": action_id, "status_code": status},
        )

    async def test(
        self,
        webhook_token: str,
        type: str,
        parameters: dict[str, Any] | None = None,
        order: int | None = None,
        request_id: str | None = None,
        action_id: str | None = None,
    ) -> ToolResult:
        """Dry-run an action against a captured request without saving it."""
        params: dict[str, Any] = {}
        if request_id:
            params["request_id"] = request_id
        if action_id:
            params["action_id"] = action_id
        # The test endpoint validates `order` even for a throwaway action.
        payload = _action_payload(type, order if order is not None else 1, parameters or {}, None, None, None, None)
        response = await self._client.post(
            f"/token/{webhook_token}/test-action",
            json_data=payload,
            params=params or None,
        )
        result = response.json()
        return ToolResult(
            success=bool(result.get("success", True)),
            message="Custom action test run finished",
            data={"result": result.get("result", result)},
        )

    async def execute(
        self,
        webhook_token: str,
        request_id: str,
        error_notifications: bool = False,
    ) -> ToolResult:
        """Re-run every action of the token against one captured request."""
        response = await self._client.post(
            f"/token/{webhook_token}/request/{request_id}/execute",
            params={"error_notifications": str(error_notifications).lower()},
        )
        result = response.json()
        return ToolResult(
            success=bool(result.get("success", True)),
            message=f"Custom actions executed for request {request_id}",
            data={"request_id": request_id, "result": result.get("result", result)},
        )
