"""Generate the tool documentation from the server's own catalogue so it cannot drift.

Usage:
    python scripts/gen_tool_docs.py            # write docs/TOOLS.md and the README tool tables
    python scripts/gen_tool_docs.py --check    # exit 1 if either is stale

Two outputs, one source (the registered tools and their docstrings):

* ``docs/TOOLS.md``: every tool with its description, parameters and MCP hints.
* The block between ``<!-- tools:start -->`` and ``<!-- tools:end -->`` in
  ``README.md``: grouped tables with each tool's one-line summary.

``tests/test_docs_current.py`` fails when either output is out of date, and the
generator itself fails if a tool is registered without a README group.
"""

from __future__ import annotations

import asyncio
import re
import sys
import textwrap
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "TOOLS.md"
README = ROOT / "README.md"
README_START = "<!-- tools:start -->"
README_END = "<!-- tools:end -->"
sys.path.insert(0, str(ROOT))

# README grouping. Every registered tool must appear exactly once.
GROUPS: list[tuple[str, list[str]]] = [
    ("Diagnostics", ["server_status"]),
    ("Webhooks", ["create_webhook", "configure_webhook", "get_webhook_info", "get_webhook_email", "list_webhooks", "delete_webhook"]),
    ("Requests", [
        "send_requests", "get_webhook_requests", "search_requests", "get_request", "update_request",
        "download_request_file", "delete_request", "delete_all_requests", "export_webhook_data",
    ]),
    ("Real-time", ["wait_for_request", "wait_for_email", "respond_to_next_request", "follow_email_link"]),
    ("Account features (API key)", [
        "manage_custom_actions", "manage_schedules", "manage_global_variables", "manage_groups",
        "manage_queues", "manage_templates", "manage_databases", "manage_users",
    ]),
    ("Security testing", ["generate_oob_payloads", "check_for_callbacks", "extract_links_from_request"]),
]


def _type(schema: dict[str, Any]) -> str:
    if "enum" in schema:
        return " | ".join(f"`{v}`" for v in schema["enum"])
    if "anyOf" in schema:
        parts = [_type(p) for p in schema["anyOf"] if p.get("type") != "null"]
        return " or ".join(dict.fromkeys(parts)) or "any"
    kind = schema.get("type", "any")
    if kind == "array":
        return f"array of {_type(schema.get('items', {}))}"
    return str(kind)


def _dedent(description: str) -> str:
    """Docstrings keep their indentation after the first line; strip it."""
    first, _, rest = description.strip("\n").partition("\n")
    return (first.strip() + "\n" + textwrap.dedent(rest)).strip()


def _summary(description: str) -> str:
    """The docstring's first line, which is what a model reads first too."""
    return description.strip().splitlines()[0].strip().replace("|", "\\|") if description.strip() else ""


def _hints(annotations: Any) -> str:
    if annotations is None:
        return ""
    flags = []
    if annotations.read_only_hint:
        flags.append("read-only")
    if annotations.destructive_hint:
        flags.append("destructive")
    if annotations.idempotent_hint:
        flags.append("idempotent")
    return ", ".join(flags)


def render_reference(tools: list[Any]) -> str:
    lines = [
        "# Tool reference",
        "",
        "Generated from the server's own tool catalogue by `scripts/gen_tool_docs.py`; do not edit by hand. "
        "`tests/test_docs_current.py` fails when this file is out of date.",
        "",
        f"{len(tools)} tools. Every `webhook_token` accepts the UUID, an alias, a pasted `https://webhook.site/...` "
        "URL, the subdomain form, the inbox address or the DNSHook name.",
        "",
    ]
    for tool in sorted(tools, key=lambda t: t.name):
        schema = tool.input_schema or {}
        required = set(schema.get("required", []))
        lines += [f"## `{tool.name}`", ""]
        hints = _hints(tool.annotations)
        if hints:
            lines += [f"*{hints}*", ""]
        lines += [_dedent(tool.description or ""), ""]
        props = schema.get("properties", {})
        if props:
            lines += ["| Parameter | Type | Required | Default |", "| --- | --- | --- | --- |"]
            for name, prop in props.items():
                default = prop.get("default")
                lines.append(
                    f"| `{name}` | {_type(prop)} | {'yes' if name in required else ''} | "
                    f"{'' if default is None else f'`{default}`'} |"
                )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_readme_block(tools: list[Any]) -> str:
    by_name = {tool.name: tool for tool in tools}
    grouped = [name for _, names in GROUPS for name in names]
    missing = sorted(set(by_name) - set(grouped))
    unknown = sorted(set(grouped) - set(by_name))
    duplicates = sorted({name for name in grouped if grouped.count(name) > 1})
    if missing or unknown or duplicates:
        raise SystemExit(
            f"README groups in scripts/gen_tool_docs.py need attention: missing={missing} unknown={unknown} duplicates={duplicates}"
        )
    lines = [README_START, "", f"{len(tools)} tools, generated from the server by `scripts/gen_tool_docs.py`.", ""]
    for heading, names in GROUPS:
        lines += [f"#### {heading}", "", "| Tool | What it does |", "| --- | --- |"]
        for name in names:
            lines.append(f"| `{name}` | {_summary(by_name[name].description or '')} |")
        lines.append("")
    lines.append(README_END)
    return "\n".join(lines)


def splice_readme(readme: str, block: str) -> str:
    pattern = re.compile(re.escape(README_START) + r".*?" + re.escape(README_END), re.DOTALL)
    if not pattern.search(readme):
        raise SystemExit(f"README.md lacks the {README_START} / {README_END} markers")
    return pattern.sub(lambda _m: block, readme, count=1)


async def build() -> tuple[str, str]:
    """(docs/TOOLS.md text, README tool block)."""
    import server

    tools = await server.mcp.list_tools()
    return render_reference(tools), render_readme_block(tools)


def main() -> int:
    reference, block = asyncio.run(build())
    readme = README.read_text(encoding="utf-8")
    new_readme = splice_readme(readme, block)
    if "--check" in sys.argv:
        stale = []
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != reference:
            stale.append(str(OUT))
        if new_readme != readme:
            stale.append(str(README))
        if stale:
            print(f"stale: {', '.join(stale)}; run: python scripts/gen_tool_docs.py", file=sys.stderr)
            return 1
        print("docs/TOOLS.md and the README tool tables are current")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(reference, encoding="utf-8")
    if new_readme != readme:
        README.write_text(new_readme, encoding="utf-8")
    print(f"wrote {OUT} and the README tool tables")
    return 0


if __name__ == "__main__":
    sys.exit(main())
