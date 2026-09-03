"""Reference for webhook.site Custom Action types and variables, verified against the live API.

``action_types.json`` is generated from webhook.site's action-types reference
(scripts/gen_action_types.py) and annotated by scripts/verify_action_types.py,
which runs every type through the real test-action endpoint. Each entry carries:

* ``params``: documented parameters with ``required`` (docs) and ``required_live``
  (the API refused the call without it, even though the docs say optional)
* ``verified``: ``ok`` (ran), ``runtime_error`` (accepted, external host failed),
  ``needs_provider`` (needs a provider connected in the Control Panel),
  ``server_error`` (the API returned 500 for a minimal payload)
* ``example``: parameters that the API accepted
"""

from __future__ import annotations

import difflib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from utils.validation import ValidationError

DATA_PATH = Path(__file__).with_name("action_types.json")

STATUS_TEXT = {
    "ok": "verified working",
    "runtime_error": "parameters accepted; fails only when the external host or resource is unreachable",
    "needs_provider": "needs a provider connected in the webhook.site Control Panel",
    "server_error": "the API returned 500 for a minimal payload; pass every documented parameter",
    "validation_error": "the API rejected the documented minimal payload",
}

# Base variables, checked live on 2026-09-03 with a log action (see the docs' variables page).
BASE_VARIABLES = [
    ("request.uuid", "all", "Request UUID"),
    ("request.token_id", "all", "Token UUID"),
    ("request.content", "all", "Body (web) or raw email"),
    ("request.date", "all", "Created at, Y-m-d H:i:s"),
    ("request.timestamp", "all", "Created at, unix seconds"),
    ("request.hostname", "all", "Host the request hit"),
    ("request.header.<name>", "all", "One variable per header, lowercase name"),
    ("request.size", "all", "Body size in bytes"),
    ("request.type", "all", "web, email or dns"),
    ("request.file.<field>.filename|size|content|content_type|id|link", "all", "Uploaded files / attachments"),
    ("request.query.<name>", "web", "One variable per query-string key"),
    ("request.form.<name>", "web", "One variable per form field"),
    ("request.ip", "web", "Client IP"),
    ("request.user_agent", "web", "User-Agent header"),
    ("request.url", "web", "Full URL"),
    ("request.path", "web", "Sub-path after the token, default /"),
    ("request.query", "web", "Full query string"),
    ("request.method", "web", "HTTP method"),
    ("request.sender", "email", "Envelope sender"),
    ("request.message_id", "email", "Message-ID"),
    ("request.text_content", "email", "Plain text (HTML converted)"),
    ("request.html_content", "email", "HTML part"),
    ("request.destinations", "email", "Recipients, comma separated"),
    ("request.checks.<name>", "email", "spam, virus, spf, dkim, dmarc as true/false"),
    ("error.<order>", "all", "Error text of the action with that order, when it failed"),
]
MODIFIERS = [
    ".json", ".json_format", ".html_encode", ".html_decode", ".html_strip",
    ".base64_encode", ".base64_decode", ".url_encode", ".url_decode", ".upper", ".lower",
]


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def all_types() -> dict[str, dict[str, Any]]:
    return load()["types"]


def required_params(entry: dict[str, Any]) -> list[str]:
    return [name for name, spec in entry["params"].items() if spec.get("required") or spec.get("required_live")]


def summarise(name: str, entry: dict[str, Any]) -> dict[str, Any]:
    """One line per type for the catalogue view."""
    verified = entry.get("verified", {})
    return {
        "type": name,
        "description": entry.get("description", ""),
        "required": required_params(entry),
        "optional": [p for p in entry["params"] if p not in required_params(entry) and "." not in p and "*" not in p],
        "status": verified.get("status"),
    }


def describe(name: str) -> dict[str, Any]:
    """Full parameter reference for one type; raises ValidationError with suggestions if unknown."""
    entry = _lookup(name)
    verified = entry.get("verified", {})
    params = {}
    for param, spec in entry["params"].items():
        detail: dict[str, Any] = {"required": bool(spec.get("required") or spec.get("required_live"))}
        if spec.get("type"):
            detail["type"] = spec["type"]
        for key in ("in", "min", "max", "default", "required_if", "required_without", "notes", "live_note"):
            if key in spec:
                detail[key] = spec[key]
        params[param] = detail
    result: dict[str, Any] = {
        "type": name,
        "description": entry.get("description", ""),
        "params": params,
        "verified": {
            "status": verified.get("status"),
            "meaning": STATUS_TEXT.get(verified.get("status", ""), "not verified"),
            "checked_at": verified.get("checked_at"),
            "output": verified.get("message"),
        },
    }
    if entry.get("note"):
        result["note"] = entry["note"]
    if entry.get("example"):
        result["example_parameters"] = entry["example"]
    return result


def variables_reference() -> dict[str, Any]:
    return {
        "syntax": "Wrap a variable in dollar signs: $request.content$. Escape with backslashes to keep a literal.",
        "base_variables": [{"name": n, "for": scope, "meaning": m} for n, scope, m in BASE_VARIABLES],
        "modifiers": {"syntax": "$name.modifier$", "available": MODIFIERS},
        "action_outputs": "Actions that set variable_name expose their result as $variable_name$; extract/split/get-requests with repeat expose $name.0.field$, $name.1.field$ ... or loop per item.",
        "global_variables": "Global Variables (manage_global_variables) are available everywhere as $name$.",
    }


def validate_action(name: str, parameters: dict[str, Any] | None, *, partial: bool = False) -> None:
    """Reject unknown types and, unless partial, missing required parameters."""
    entry = _lookup(name)
    if partial or parameters is None:
        return
    missing = [p for p in required_params(entry) if p not in parameters or parameters[p] in (None, "")]
    if missing:
        raise ValidationError(
            f"Custom action '{name}' needs parameters: {', '.join(missing)}. "
            f"Call manage_custom_actions(action='types', type='{name}') for the reference."
        )


def _lookup(name: str) -> dict[str, Any]:
    types = all_types()
    if name in types:
        return types[name]
    lowered = name.lower()
    by_affix = [t for t in types if lowered.startswith(t) or t.startswith(lowered) or t in lowered]
    close = by_affix + [t for t in difflib.get_close_matches(lowered, list(types), n=3, cutoff=0.5) if t not in by_affix]
    hint = f" Did you mean: {', '.join(close[:3])}?" if close else ""
    raise ValidationError(
        f"Unknown custom action type '{name}'.{hint} Call manage_custom_actions(action='types') for the list."
    )
