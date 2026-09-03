"""Check every WebhookScript function name in utils/webhookscript.json against the live engine.

Usage:
    WEBHOOK_SITE_API_KEY=... python scripts/verify_webhookscript.py

Each name is called with no arguments through POST /token/{id}/test-action on a
throwaway token. The engine answers "Undefined variable 'name'" for functions
that do not exist and "Function expects N arguments" (or runs) for ones that
do, so the reply settles existence without side effects. Names with side
effects (delay, import, http, request, multipart, db, store, delete, exec,
respond, stop, dd, action) are referenced as values instead of called
(``type(name)``), which the engine also rejects for unknown names.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.webhook_service import WebhookService  # noqa: E402
from utils.http_client import WebhookHttpClient  # noqa: E402

DATA = ROOT / "utils" / "webhookscript.json"
SIDE_EFFECTS = {"delay", "import", "http", "request", "multipart", "db", "store", "delete", "exec", "respond", "stop", "dd", "action"}
# Names official examples use that the function pages never document.
EXTRA = {
    "get": {"group": "variables", "signatures": ["get(string variable_name, any default) : any"], "summary": "Alias of var() used in official examples (undocumented)."},
    "get_variable": {"group": "variables", "signatures": ["get_variable(string variable_name) : any"], "summary": "Alias of var() (undocumented)."},
    "base64url_encode": {"group": "string", "signatures": ["base64url_encode(string value) : string"], "summary": "URL-safe base64, same as base64_urlencode (undocumented alias)."},
    "length": {"group": "general", "signatures": ["length(string/array value) : number"], "summary": "Length of a string or array (undocumented alias)."},
}


async def probe(client: WebhookHttpClient, token: str, name: str) -> tuple[bool, str]:
    code = f"echo(type({name}))" if name in SIDE_EFFECTS else f"{name}()"
    response = await client.post(f"/token/{token}/test-action", json_data={"type": "script", "order": 1, "parameters": {"script": code}})
    data = response.json()
    output = (data.get("result") or {}).get("output") or {}
    messages = [str(m) for value in output.values() for m in (value if isinstance(value, list) else [value])]
    text = " | ".join(messages)
    exists = not text.startswith("Undefined variable")
    return exists, text[:120]


async def main() -> None:
    api_key = os.environ.get("WEBHOOK_SITE_API_KEY")
    if not api_key:
        sys.exit("WEBHOOK_SITE_API_KEY is required")
    data = json.loads(DATA.read_text(encoding="utf-8"))
    for name, entry in EXTRA.items():
        data["functions"].setdefault(name, dict(entry))
    data.setdefault("extra_functions", {}).update(EXTRA)
    today = dt.date.today().isoformat()
    async with WebhookHttpClient(api_key=api_key) as client:
        created = await WebhookService(client).configure(__import__("models.schemas", fromlist=["WebhookConfig"]).WebhookConfig(expiry=1800))
        token = created.data["token"]
        try:
            missing = []
            for name in sorted(data["functions"]):
                exists, message = await probe(client, token, name)
                data["functions"][name]["verified"] = {"exists": exists, "checked_at": today, "message": message}
                if not exists:
                    missing.append(name)
                print(f"{'ok     ' if exists else 'MISSING'} {name}: {message[:70]}")
        finally:
            await client.delete(f"/token/{token}")
    data["verified_at"] = today
    data["functions"] = dict(sorted(data["functions"].items()))
    DATA.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n{len(data['functions']) - len(missing)} functions exist, {len(missing)} missing: {missing}")


if __name__ == "__main__":
    asyncio.run(main())
