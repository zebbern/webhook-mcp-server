"""Record real webhook.site exchanges so offline tests can replay the truth.

Enabled by ``WEBHOOK_MCP_RECORD=<file.jsonl>``. Two kinds of lines are written:

    {"kind": "tool", "seq": 12, "name": "get_webhook_requests"}
    {"kind": "http", "seq": 12, "method": "GET", "url": "...", "params": {...},
     "json": {...}, "status": 200, "content_type": "application/json",
     "response": {...} | "<text>", "response_is_text": false}

``seq`` ties every HTTP exchange to the tool call that caused it, so a replay
can select exactly the exchanges of the tool calls it reproduces.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any

ENV = "WEBHOOK_MCP_RECORD"

# Real mailboxes only: not token inboxes, and not URL userinfo like https://evil.com@webhook.site/...
_EMAIL = re.compile(r"(?<![/\w.])[A-Za-z0-9._%+-]+@(?!email\.webhook\.site|emailhook\.site)[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_IPV4 = re.compile(r"\b(?!127\.|10\.|192\.168\.|0\.0\.0\.0)(?:\d{1,3}\.){3}\d{1,3}\b")


def sanitize(value: Any) -> Any:
    """Replace personal data (emails, public IPs, user names) in recorded payloads."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            is_user_record = "email" in value or "user_type_id" in value
            if key == "name" and isinstance(item, str) and is_user_record:
                out[key] = "Recorded User"
            else:
                out[key] = sanitize(item)
        return out
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        value = _EMAIL.sub("user@example.com", value)
        return _IPV4.sub("203.0.113.10", value)
    return value


class Recorder:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._seq = 0
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("", encoding="utf-8")

    def mark(self, tool: str) -> None:
        with self._lock:
            self._seq += 1
            self._write({"kind": "tool", "seq": self._seq, "name": tool})

    def http(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None,
        json_body: Any,
        status: int,
        content_type: str,
        response: Any,
        response_is_text: bool,
        location: str | None = None,
    ) -> None:
        with self._lock:
            self._write(
                {
                    "kind": "http",
                    "seq": self._seq,
                    "method": method.upper(),
                    "url": url,
                    "params": sanitize(params),
                    "json": sanitize(json_body),
                    "status": status,
                    "content_type": content_type,
                    "location": location,
                    "response": sanitize(response),
                    "response_is_text": response_is_text,
                }
            )

    def _write(self, line: dict[str, Any]) -> None:
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")


_recorder: Recorder | None = None
_checked = False


def active() -> Recorder | None:
    """The process-wide recorder, created on first use when the env var is set."""
    global _recorder, _checked
    if not _checked:
        _checked = True
        target = os.environ.get(ENV, "").strip()
        if target:
            _recorder = Recorder(Path(target))
    return _recorder
