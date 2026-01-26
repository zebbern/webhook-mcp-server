#!/usr/bin/env python3
"""
Webhook.site MCP Server

A Model Context Protocol (MCP) server for interacting with webhook.site.
Provides tools for creating, managing, and monitoring webhooks.

Usage:
    python server.py

Architecture:
    server.py          - MCP entry point (this file)
    handlers/          - Tool call routing
    services/          - Business logic
    models/            - Data models and schemas
    utils/             - HTTP client utilities
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from models.schemas import TOOL_DEFINITIONS
from handlers.tool_handlers import ToolHandler
from utils.http_client import WebhookHttpClient


# =============================================================================
# SERVER INITIALIZATION
# =============================================================================

server = Server("webhook-site-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return all available webhook.site tools.
    
    Returns:
        List of Tool definitions from models/schemas.py
    """
    return TOOL_DEFINITIONS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle MCP tool calls.
    
    Routes tool calls through the handler layer which delegates
    to appropriate services.
    
    Args:
        name: Tool name
        arguments: Tool arguments
        
    Returns:
        List of TextContent responses
    """
    async with WebhookHttpClient() as client:
        handler = ToolHandler(client)
        return await handler.handle(name, arguments)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

async def main() -> None:
    """Run the MCP server.
    
    Starts the stdio transport and runs the server
    until interrupted.
    """
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def run_server() -> None:
    """Synchronous entry point for console script."""
    asyncio.run(main())


if __name__ == "__main__":
    run_server()
