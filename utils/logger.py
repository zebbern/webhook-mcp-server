"""
Logging configuration for webhook-mcp-server.

Provides structured logging setup for production monitoring
and debugging capabilities.
"""

from __future__ import annotations

import logging
import sys
from typing import TextIO


def setup_logger(
    name: str,
    level: int = logging.INFO,
    stream: TextIO = sys.stderr,
) -> logging.Logger:
    """Configure structured logging for a module.
    
    Args:
        name: Logger name (typically __name__)
        level: Logging level (default: INFO)
        stream: Output stream (default: stderr)
        
    Returns:
        Configured Logger instance
        
    Example:
        >>> logger = setup_logger(__name__)
        >>> logger.info("Webhook created", extra={"token": "abc123"})
    """
    logger = logging.getLogger(name)
    
    # Prevent duplicate handlers if already configured
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    # Create console handler with formatting
    handler = logging.StreamHandler(stream)
    handler.setLevel(level)
    
    # Format: timestamp - module - level - message
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger
