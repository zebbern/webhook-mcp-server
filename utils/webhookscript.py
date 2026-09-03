"""WebhookScript function reference for `script` custom actions.

Generated from the official function docs by scripts/gen_webhookscript.py and
checked against the live engine by scripts/verify_webhookscript.py (every name
is called through test-action; an "Undefined variable" answer means the
function does not exist).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from utils.validation import ValidationError

DATA_PATH = Path(__file__).parent / "webhookscript.json"


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def groups() -> list[str]:
    return sorted({entry["group"] for entry in load()["functions"].values()})


def reference(group: str | None = None, search: str | None = None) -> dict[str, Any]:
    """Compact reference: language notes plus one line per function.

    group narrows to one docs page (string, array, date, network, flow, ...);
    search keeps functions whose name or summary contains the text.
    """
    data = load()
    functions = data["functions"]
    if group is not None:
        if group not in groups():
            raise ValidationError(f"Unknown WebhookScript group '{group}'. Groups: {', '.join(groups())}")
        functions = {name: entry for name, entry in functions.items() if entry["group"] == group}
    if search:
        needle = search.lower()
        functions = {
            name: entry
            for name, entry in functions.items()
            if needle in name.lower() or needle in entry.get("summary", "").lower()
        }
    listing = []
    for name, entry in functions.items():
        line: dict[str, Any] = {
            "name": name,
            "group": entry["group"],
            "signature": " | ".join(entry["signatures"]),
            "summary": entry.get("summary", ""),
        }
        verified = entry.get("verified")
        if verified is not None:
            line["exists_live"] = verified.get("exists")
        listing.append(line)
    return {
        "verified_at": data.get("verified_at"),
        "groups": groups(),
        "language_notes": data["language_notes"],
        "functions": listing,
        "count": len(listing),
    }
