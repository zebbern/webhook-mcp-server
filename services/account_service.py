"""Account-level webhook.site resources: token list, groups, templates, global variables, users.

Every endpoint here needs an API key. Lists are walked with the client's
pagination helper and return a ``pagination`` summary next to the items.
"""

from __future__ import annotations

from typing import Any

from models.schemas import ToolResult
from services.webhook_service import format_token
from utils.http_client import WebhookApiError, WebhookHttpClient


def _compact(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


class AccountService:
    """CRUD over account resources that are not tied to one token."""

    def __init__(self, client: WebhookHttpClient) -> None:
        self._client = client

    # --- shared helpers ---------------------------------------------------

    async def _list(
        self,
        path: str,
        label: str,
        params: dict[str, Any] | None = None,
        *,
        max_items: int = 200,
    ) -> ToolResult:
        items, pagination = await self._client.paginate(path, params, max_items=max_items)
        return ToolResult(
            success=True,
            message=f"Retrieved {len(items)} {label}",
            data={label: items, "pagination": pagination},
        )

    async def _create(self, path: str, label: str, payload: dict[str, Any]) -> ToolResult:
        response = await self._client.post(path, json_data=_compact(payload))
        data = response.json() if response.content else {}
        return ToolResult(success=True, message=f"{label} created", data={label.lower(): data})

    async def _update(self, path: str, label: str, payload: dict[str, Any]) -> ToolResult:
        data = await self._client.put(path, json_data=_compact(payload))
        return ToolResult(success=True, message=f"{label} updated", data={label.lower(): data})

    async def _find(self, path: str, resource_id: Any, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Fetch one item of a list endpoint by id (the API has no single-item GET for these).

        PUT replaces the whole record on webhook.site, so updates merge into this.
        """
        items, _ = await self._client.paginate(path, params or {"per_page": 100}, max_items=1000, delay=0)
        for item in items:
            if str(item.get("id")) == str(resource_id):
                return item
        return {}

    @staticmethod
    def _merge(current: dict[str, Any], keys: tuple[str, ...], **changes: Any) -> dict[str, Any]:
        merged = {key: current.get(key) for key in keys}
        merged.update({key: value for key, value in changes.items() if value is not None})
        return merged

    async def _delete(self, path: str, label: str, resource_id: Any) -> ToolResult:
        status = await self._client.delete(path)
        return ToolResult(
            success=status in (200, 204),
            message=f"{label} {resource_id} deleted",
            data={"id": resource_id, "status_code": status},
        )

    # --- tokens -----------------------------------------------------------

    async def list_tokens(
        self,
        page: int = 1,
        per_page: int = 50,
        order_by: str = "created_at",
        order_direction: str = "desc",
        max_items: int = 200,
    ) -> ToolResult:
        """List the tokens (URLs / inboxes) that belong to the account."""
        params = {
            "page": page,
            "per_page": per_page,
            "order_by": order_by,
            "order_direction": order_direction,
        }
        items, pagination = await self._client.paginate("/token", params, max_items=max_items)
        webhooks = [format_token(item) for item in items]
        return ToolResult(
            success=True,
            message=f"Retrieved {len(webhooks)} webhooks",
            data={"webhooks": webhooks, "pagination": pagination},
        )

    # --- groups -----------------------------------------------------------

    async def list_groups(self, page: int = 1, max_items: int = 200) -> ToolResult:
        return await self._list("/groups", "groups", {"page": page}, max_items=max_items)

    async def create_group(self, name: str) -> ToolResult:
        return await self._create("/groups", "Group", {"name": name})

    async def update_group(self, group_id: int, name: str) -> ToolResult:
        return await self._update(f"/groups/{group_id}", "Group", {"name": name})

    async def delete_group(self, group_id: int) -> ToolResult:
        return await self._delete(f"/groups/{group_id}", "Group", group_id)

    # --- templates --------------------------------------------------------

    async def list_templates(self, page: int = 1, max_items: int = 200) -> ToolResult:
        return await self._list("/templates", "templates", {"page": page}, max_items=max_items)

    async def create_template(
        self,
        name: str,
        actions: list[dict[str, Any]] | None = None,
        variables: list[dict[str, Any]] | None = None,
    ) -> ToolResult:
        return await self._create(
            "/templates", "Template", {"name": name, "actions": actions, "variables": variables}
        )

    async def update_template(
        self,
        template_id: int,
        name: str | None = None,
        actions: list[dict[str, Any]] | None = None,
        variables: list[dict[str, Any]] | None = None,
    ) -> ToolResult:
        current = await self._find("/templates", template_id)
        payload = self._merge(current, ("name", "actions", "variables"), name=name, actions=actions, variables=variables)
        return await self._update(f"/templates/{template_id}", "Template", payload)

    async def delete_template(self, template_id: int) -> ToolResult:
        return await self._delete(f"/templates/{template_id}", "Template", template_id)

    # --- global variables -------------------------------------------------

    async def list_variables(
        self,
        search: str | None = None,
        page: int = 1,
        max_items: int = 200,
    ) -> ToolResult:
        params: dict[str, Any] = {"page": page, "per_page": 100}
        if search:
            params["search"] = search
        return await self._list("/global-variables", "variables", params, max_items=max_items)

    async def create_variable(self, name: str, value: str) -> ToolResult:
        return await self._create("/global-variables", "Variable", {"name": name, "value": value})

    async def update_variable(
        self,
        variable_id: int,
        name: str | None = None,
        value: str | None = None,
    ) -> ToolResult:
        # A value-only PUT wipes the variable's name on webhook.site, so always send both.
        current = await self._find("/global-variables", variable_id)
        payload = self._merge(current, ("name", "value"), name=name, value=value)
        return await self._update(f"/global-variables/{variable_id}", "Variable", payload)

    async def delete_variable(self, variable_id: int) -> ToolResult:
        return await self._delete(f"/global-variables/{variable_id}", "Variable", variable_id)

    # --- queue profiles (undocumented; shape verified live 2026-09-03) --------
    # POST/PUT need name, amount (jobs), duration (seconds per window), expiry
    # (job lifetime seconds), delay (initial delay seconds). GET /queues/{id} 404s,
    # so single lookups go through the list.

    async def list_queues(self, page: int = 1, max_items: int = 200) -> ToolResult:
        return await self._list("/queues", "queues", {"page": page, "per_page": 100}, max_items=max_items)

    async def create_queue(
        self,
        name: str,
        amount: int,
        duration: int,
        expiry: int,
        delay: int = 0,
        group_id: int | None = None,
    ) -> ToolResult:
        return await self._create(
            "/queues",
            "Queue",
            {"name": name, "amount": amount, "duration": duration, "expiry": expiry, "delay": delay, "group_id": group_id},
        )

    async def update_queue(
        self,
        queue_id: int,
        name: str | None = None,
        amount: int | None = None,
        duration: int | None = None,
        expiry: int | None = None,
        delay: int | None = None,
        group_id: int | None = None,
    ) -> ToolResult:
        current = await self._find("/queues", queue_id)
        payload = self._merge(
            current,
            ("name", "amount", "duration", "expiry", "delay", "group_id"),
            name=name, amount=amount, duration=duration, expiry=expiry, delay=delay, group_id=group_id,
        )
        return await self._update(f"/queues/{queue_id}", "Queue", payload)

    async def delete_queue(self, queue_id: int) -> ToolResult:
        return await self._delete(f"/queues/{queue_id}", "Queue", queue_id)

    async def live_variables(self) -> list[str]:
        """Names of the base variables the API currently defines (GET /variables; undocumented)."""
        try:
            data = await self._client.get("/variables")
        except WebhookApiError:
            return []
        return sorted(data.keys()) if isinstance(data, dict) else []

    # --- users ------------------------------------------------------------

    async def list_users(self, page: int = 1, max_items: int = 200) -> ToolResult:
        return await self._list("/users", "users", {"page": page}, max_items=max_items)

    async def invite_user(
        self,
        name: str,
        email: str,
        user_type_id: int,
        role_id: int | None = None,
    ) -> ToolResult:
        return await self._create(
            "/users/invite",
            "User",
            {"name": name, "email": email, "user_type_id": user_type_id, "role_id": role_id},
        )

    async def update_user(
        self,
        user_id: int,
        name: str | None = None,
        email: str | None = None,
        user_type_id: int | None = None,
        role_id: int | None = None,
    ) -> ToolResult:
        current = await self._find("/users", user_id, params={"page": 1})
        payload = self._merge(
            current,
            ("name", "email", "user_type_id"),
            name=name,
            email=email,
            user_type_id=user_type_id,
            role_id=role_id,
        )
        return await self._update(f"/users/{user_id}", "User", payload)

    async def delete_user(self, user_id: int) -> ToolResult:
        return await self._delete(f"/users/{user_id}", "User", user_id)
