"""Generate utils/action_types.json from webhook.site's action-types reference.

Usage:
    python scripts/gen_action_types.py path/to/docs/api/action-types.md

The markdown lists one `### \\`type\\`` heading per action type followed by
`- \\`param\\`: constraints` bullets. Constraints are Laravel-style validation
rules (``**required**``, ``string``, ``in:a,b``, ``min:1``, ``nullable``,
``required_if:mode,multipart`` ...). The live verification results in
``verified`` are merged in by scripts/verify_action_types.py and preserved here.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "utils" / "action_types.json"

HEADING = re.compile(r"^### `([a-z0-9_]+)`\s*$")
PARAM = re.compile(r"^- `([a-z0-9_.*]+)`:\s*(.+?)\s*$")
NO_PARAMS = re.compile(r"^\*No parameters for `([a-z0-9_]+)`\.\*$")
TYPE_WORDS = {"string", "int", "integer", "number", "numeric", "bool", "boolean", "array", "url"}

# Short, model-facing descriptions for the types people reach for most.
DESCRIPTIONS = {
    "modify_response": "Set the HTTP response (body, status, headers) the URL returns for this request; `stop` ends the chain.",
    "http": "Send an HTTP request to any URL (forward, JSON, multipart, urlencoded); response goes into $variable_name$.",
    "send_request": "Simpler HTTP request action (legacy); prefer `http`.",
    "script": "Run WebhookScript (webhook.site's scripting language); use echo(), respond(), var(), set().",
    "javascript": "Run JavaScript; access variables and set the response from code.",
    "extract_jsonpath": "Pull a value out of JSON with a JSONPath expression into $variable_name$.",
    "extract_regex": "Capture a regex match from the request into $variable_name$.",
    "extract_xpath": "Pull a value out of XML/HTML with XPath into $variable_name$.",
    "auto_json": "Register every JSON field of the body as a variable (optionally under a name prefix).",
    "condition": "Compare `input` with `value` using `operator`; `action` stop/continue/noop decides what happens when it passes.",
    "conditions": "Several conditions with mode one/all/none; `action` stop/continue/noop when they pass.",
    "rate_limit": "Reject requests beyond `count` per `period` seconds (optionally per `key`).",
    "log": "Write text or markdown to the request's action log.",
    "set_variable": "Set a runtime variable (text, random string, or formatted date).",
    "store_global_variable": "Persist a value as a Global Variable shared by all URLs.",
    "send_email": "Send an email from webhook.site (also fires on incoming emails: guard with a condition on $request.type$).",
    "send_email_smtp": "Send an email through your own SMTP server.",
    "slack_send_message": "Post to a Slack incoming webhook URL.",
    "discord_send_message": "Post to Discord through a connected provider.",
    "ntfy": "Push a notification to an ntfy.sh topic.",
    "dont_save": "Do not store this request in the history.",
    "stop": "Stop running further actions.",
    "sleep": "Pause for `delay` seconds before continuing.",
    "auth_basic": "Require HTTP Basic auth on the URL.",
    "template": "Include the actions of a saved Template.",
    "webhook_get_requests": "Fetch requests of another token into $variable_name$ (can repeat over them).",
    "text_replace": "Replace substrings in `source`.",
    "text_split": "Split `source` on `delimiter` (can repeat over the parts).",
    "text_map": "Map `source` to another value through a lookup table.",
    "text_encrypt": "AES-encrypt `source` with `password`.",
    "text_decrypt": "Decrypt text produced by text_encrypt.",
    "pdf_generate": "Render HTML or markdown to a PDF file variable.",
    "image_resize": "Resize an uploaded image.",
    "database": "Run SQL on your own MySQL/Postgres/SQL Server.",
}

PROVIDER_TYPES_NOTE = "Needs a provider connected in the webhook.site Control Panel (provider_id)."

# Parameters the docs call optional but the live API insists on (seen 2026-09-03).
LIVE_REQUIRED = {
    ("condition", "value"): "test-action returned 500 without it",
    ("condition", "input"): "without it the API compares the request body, not what you meant",
    ("microsoft_drive_download", "variable_name"): "API answered 'Missing parameter: variable_name'",
    ("text_map", "default"): "API answered 'Missing parameter: default' for an empty string",
}

# Types the product docs describe but the API reference page omits; verified live.
EXTRA_TYPES = {
    "mock": {
        "params": {
            "source": {"required": True, "type": "string", "notes": ["OpenAPI/Swagger spec as JSON or YAML, or a URL to one"]},
            "path": {"required": False, "type": "string", "notes": ["Path to match, e.g. https://example.com$request.path$"]},
        },
        "description": "Turn the URL into a mock server for an OpenAPI/Swagger spec: responses follow the spec's paths and schemas.",
    },
    "validate_json": {
        "params": {
            "source": {"required": True, "type": "string", "notes": ["JSON text to validate, e.g. $request.content$"]},
            "schema": {"required": False, "type": "string", "notes": ["JSON Schema text or URL"]},
        },
        "description": "Check that `source` is valid JSON (optionally against a JSON Schema); sets $validator.count$ and $validator.errors$, errors the action on failure.",
    },
}


def parse_rules(rules: str) -> dict:
    spec: dict = {"required": False, "type": None}
    # Rules are separated by ", " while in:/required_if: lists use bare commas.
    for raw in rules.split(", "):
        token = raw.replace("*", "").strip()
        low = token.lower()
        if not token:
            continue
        if low.startswith("required_if:"):
            spec["required_if"] = token.split(":", 1)[1]
        elif low.startswith("required_without:"):
            spec["required_without"] = token.split(":", 1)[1]
        elif low == "required" or low.endswith("_required"):
            spec["required"] = True
            if "_" in low and low.split("_")[0] in TYPE_WORDS:
                spec["type"] = low.split("_")[0]
        elif low.startswith("in:"):
            spec["in"] = [option.strip() for option in token[3:].split(",")]
        elif low.startswith("min:"):
            spec["min"] = int(token[4:])
        elif low.startswith("max:"):
            spec["max"] = int(token[4:])
        elif low.startswith("default:"):
            spec["default"] = token[8:]
        elif low == "nullable":
            spec["nullable"] = True
        elif low in TYPE_WORDS:
            spec["type"] = {"integer": "int", "numeric": "number", "boolean": "bool"}.get(low, low)
        else:
            spec.setdefault("notes", []).append(token)
    return spec


def parse(markdown: str) -> dict[str, dict]:
    types: dict[str, dict] = {}
    current: str | None = None
    for line in markdown.splitlines():
        heading = HEADING.match(line.strip())
        if heading:
            current = heading.group(1)
            types[current] = {"params": {}}
            continue
        if current is None:
            continue
        if NO_PARAMS.match(line.strip()):
            continue
        param = PARAM.match(line.strip())
        if param:
            name, rules = param.groups()
            types[current]["params"][name] = parse_rules(rules)
    for name, entry in types.items():
        entry["description"] = DESCRIPTIONS.get(name, name.replace("_", " ").capitalize())
        if "provider_id" in entry["params"]:
            entry["note"] = PROVIDER_TYPES_NOTE
    for name, entry in EXTRA_TYPES.items():
        types.setdefault(name, json.loads(json.dumps(entry)))
    for (type_name, param), reason in LIVE_REQUIRED.items():
        spec = types.get(type_name, {}).get("params", {}).get(param)
        if spec is not None:
            spec["required_live"] = True
            spec["live_note"] = reason
    return types


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if source is None or not source.exists():
        sys.exit("usage: gen_action_types.py <path to docs/api/action-types.md>")
    parsed = parse(source.read_text(encoding="utf-8"))
    previous: dict = {}
    verified_at = None
    if OUT.exists():
        existing = json.loads(OUT.read_text(encoding="utf-8"))
        previous = existing.get("types", {})
        verified_at = existing.get("verified_at")
    for name, entry in parsed.items():
        old = previous.get(name, {})
        for key in ("verified", "example"):
            if key in old:
                entry[key] = old[key]
        for param, spec in old.get("params", {}).items():
            if spec.get("required_live") and param in entry["params"]:
                entry["params"][param]["required_live"] = True
    dates = [entry.get("verified", {}).get("checked_at") for entry in parsed.values()]
    verified_at = verified_at or max((date for date in dates if date), default=None)
    payload = {
        "source": "https://docs.webhook.site/api/action-types.html",
        "verified_at": verified_at,
        "types": dict(sorted(parsed.items())),
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT} with {len(parsed)} action types")


if __name__ == "__main__":
    main()
