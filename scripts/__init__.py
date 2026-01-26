"""
Webhook.site MCP Server - Helper Scripts

Utility scripts for working with webhook.site:
- check_webhook.py: Check webhook for incoming requests and extract magic links
- get_temp_email.py: Quickly create a new temporary email address
"""

from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
