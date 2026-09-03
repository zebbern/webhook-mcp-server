"""Docs must match the code: the generated reference, the README tool tables and the badge are current."""

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


def test_generated_tool_reference_and_readme_tables_are_current() -> None:
    import gen_tool_docs

    reference, block = asyncio.run(gen_tool_docs.build())
    assert gen_tool_docs.OUT.exists(), "run python scripts/gen_tool_docs.py"
    assert gen_tool_docs.OUT.read_text(encoding="utf-8") == reference, "docs/TOOLS.md is stale; run scripts/gen_tool_docs.py"
    readme = gen_tool_docs.README.read_text(encoding="utf-8")
    assert gen_tool_docs.splice_readme(readme, block) == readme, "README tool tables are stale; run scripts/gen_tool_docs.py"


def test_readme_tool_tables_name_every_tool_and_the_badge_count_is_right() -> None:
    import gen_tool_docs

    readme = gen_tool_docs.README.read_text(encoding="utf-8")
    block = readme.split(gen_tool_docs.README_START, 1)[1].split(gen_tool_docs.README_END, 1)[0]
    documented = set(re.findall(r"^\| `([a-z_]+)`", block, re.MULTILINE))
    assert documented == _tool_names()
    badge = re.search(r"MCP-(\d+)%20tools", readme)
    assert badge and int(badge.group(1)) == len(_tool_names())


def test_docs_pages_exist_and_are_linked() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for page in ("docs/TOOLS.md", "docs/webhook-site-notes.md", "docs/testing.md", "docs/releasing.md"):
        assert (ROOT / page).exists(), page
        assert page in readme, f"README does not link {page}"
