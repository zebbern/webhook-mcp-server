"""Docs must match the code: the generated reference is current and the README names every tool."""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def _tool_names() -> set[str]:
    import server

    return {tool.name for tool in asyncio.run(server.mcp.list_tools())}


def test_generated_tool_reference_is_current() -> None:
    import gen_tool_docs

    expected = asyncio.run(gen_tool_docs.build())
    assert gen_tool_docs.OUT.exists(), "run python scripts/gen_tool_docs.py"
    assert gen_tool_docs.OUT.read_text(encoding="utf-8") == expected, "docs/TOOLS.md is stale; run scripts/gen_tool_docs.py"


def test_readme_tools_reference_names_every_tool() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Tools Reference", 1)[1].split("## Examples", 1)[0]
    documented = set(re.findall(r"^\| `([a-z_]+)`", section, re.MULTILINE))
    missing = _tool_names() - documented
    assert not missing, f"README Tools Reference lacks: {sorted(missing)}"
    badge = re.search(r"MCP-(\d+)%20tools", readme)
    assert badge and int(badge.group(1)) == len(_tool_names())
