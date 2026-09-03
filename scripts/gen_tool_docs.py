"""Generate docs/TOOLS.md from the live tool catalogue so the reference cannot drift.

Usage:
    python scripts/gen_tool_docs.py            # write docs/TOOLS.md
    python scripts/gen_tool_docs.py --check    # exit 1 if docs/TOOLS.md is stale
"""

from __future__ import annotations

import asyncio
import sys
import textwrap
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "TOOLS.md"
sys.path.insert(0, str(ROOT))


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


def render(tools: list[Any]) -> str:
    lines = [
        "# Tool reference",
        "",
        "Generated from the server's own tool catalogue by `scripts/gen_tool_docs.py`; do not edit by hand. "
        "`tests/test_docs_current.py` fails when this file is out of date.",
        "",
        f"{len(tools)} tools.",
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


async def build() -> str:
    import server

    tools = await server.mcp.list_tools()
    return render(tools)


def main() -> int:
    text = asyncio.run(build())
    if "--check" in sys.argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print(f"{OUT} is stale; run: python scripts/gen_tool_docs.py", file=sys.stderr)
            return 1
        print("docs/TOOLS.md is current")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
