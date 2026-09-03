"""Generate utils/webhookscript.json from the WebhookScript function docs.

Usage:
    python scripts/gen_webhookscript.py path/to/docs/webhookscript

Every ``docs/webhookscript/functions/*.md`` page lists functions as
``### name(***type*** arg, ...) : return`` headings followed by a description.
This turns them into one compact entry per function so a model writing a
``script`` action can look up real names and signatures instead of guessing.
Live verification results (``verified``) written by
scripts/verify_webhookscript.py are preserved across regenerations.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "utils" / "webhookscript.json"

HEADING = re.compile(r"^###\s+([a-z_0-9]+)\s*(\(.*\))?\s*(?::\s*(.+?))?\s*$")
INLINE_MARKUP = re.compile(r"[*`]+")
LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")

# Facts about the language that trip up people (and models) used to JS/PHP.
LANGUAGE_NOTES = [
    "Custom Action variables are NOT substituted inside a script: read them with var('request.content') (the $ signs are optional).",
    "set(name, value) exports a variable to later actions; store(name, value) writes a permanent Global Variable.",
    "Strict typing: 5 + \"4\" is an error. Convert with to_string()/to_number() or build strings with string_format('{} items', n).",
    "Strings: + concatenates, - removes a substring (or every regex match), 2 * \"ab\" repeats.",
    "Regex literal r\"...\" (PCRE, unicode); \"hello\" == r\"l{2}\" is a match test; string_replace supports $1 back-references.",
    "Arrays are ordered maps: ['a', 'b', 'k': 1]; ranges 1..5 and 1..2..9 build arrays; keys are 0-based.",
    "Any function can be called method-style: value.string_upper() == string_upper(value); the type prefix may be dropped (\"x\".upper() is NOT valid, \"x\".length() is, via string_length).",
    "Control flow: if/else, for (item in array_or_string), while, break, continue; functions are first-class and capture scope.",
    "respond(content, status, headers) stops execution and answers the request; set_response/set_content/set_status/set_header change the response and continue.",
    "echo()/dump() write to the action output shown on the request; dd() dumps and stops.",
    "Undocumented names that exist live: get() and get_variable() (same as var), length(), base64url_encode(). Documented but NOT defined live: base64_urlencode (use base64url_encode), number_length. Also undefined: file_contents, array_slice, match.",
    "Timeouts: the whole action chain must answer within 30 s (queued actions get 120 s); http()/request() default to a 5 s timeout.",
]


def clean(text: str) -> str:
    text = LINK.sub(r"\1", text)
    text = INLINE_MARKUP.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_page(path: Path) -> dict[str, dict]:
    functions: dict[str, dict] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        match = HEADING.match(lines[i])
        if not match:
            i += 1
            continue
        name, args, returns = match.groups()
        signature = clean(f"{name}{args or ''}" + (f" : {returns}" if returns else ""))
        summary = ""
        j = i + 1
        while j < len(lines) and not lines[j].startswith("### "):
            line = lines[j].strip()
            if line.startswith("```"):
                # skip the code sample
                j += 1
                while j < len(lines) and not lines[j].startswith("```"):
                    j += 1
            elif line and not line.startswith("#") and not summary:
                summary = clean(line)
            j += 1
        entry = functions.setdefault(name, {"group": path.stem, "signatures": [], "summary": summary})
        if signature not in entry["signatures"]:
            entry["signatures"].append(signature)
        if not entry["summary"]:
            entry["summary"] = summary
        i = j
    return functions


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if source is None or not (source / "functions").is_dir():
        sys.exit("usage: gen_webhookscript.py <path to docs/webhookscript>")
    functions: dict[str, dict] = {}
    for page in sorted((source / "functions").glob("*.md")):
        for name, entry in parse_page(page).items():
            if name in functions:
                functions[name]["signatures"].extend(s for s in entry["signatures"] if s not in functions[name]["signatures"])
            else:
                functions[name] = entry
    previous: dict = {}
    verified_at = None
    extra: dict = {}
    if OUT.exists():
        existing = json.loads(OUT.read_text(encoding="utf-8"))
        previous = existing.get("functions", {})
        verified_at = existing.get("verified_at")
        # Names the verifier found live that the docs do not list.
        extra = existing.get("extra_functions", {})
        for name, entry in extra.items():
            functions.setdefault(name, dict(entry))
    for name, entry in functions.items():
        if "verified" in previous.get(name, {}):
            entry["verified"] = previous[name]["verified"]
    payload = {
        "source": "https://docs.webhook.site/webhookscript/functions/",
        "verified_at": verified_at,
        "language_notes": LANGUAGE_NOTES,
        "extra_functions": extra,
        "functions": dict(sorted(functions.items())),
    }
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT} with {len(functions)} functions")


if __name__ == "__main__":
    main()
