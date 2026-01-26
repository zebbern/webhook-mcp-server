"""
Input validation utilities for webhook-mcp-server.

Provides secure validation functions to prevent injection attacks,
ensure data integrity, and handle edge cases safely.
"""

from __future__ import annotations

import re
from uuid import UUID


class ValidationError(ValueError):
    """Raised when validation fails."""
    pass


def validate_webhook_token(token: str) -> None:
    """Validate webhook token is a valid UUID format.
    
    Args:
        token: Webhook UUID token
        
    Raises:
        ValidationError: If token is not a valid UUID
        
    Example:
        >>> validate_webhook_token("550e8400-e29b-41d4-a716-446655440000")
        >>> validate_webhook_token("invalid")  # Raises ValidationError
    """
    if not token or not isinstance(token, str):
        raise ValidationError("Webhook token must be a non-empty string")
    
    try:
        UUID(token)
    except (ValueError, AttributeError) as e:
        raise ValidationError(
            f"Invalid webhook token format. Expected UUID, got: {token[:20]}..."
        ) from e


def validate_positive_int(
    value: int,
    name: str,
    min_val: int = 0,
    max_val: int | None = None,
) -> None:
    """Validate integer is positive and within bounds.
    
    Args:
        value: Integer value to validate
        name: Parameter name for error messages
        min_val: Minimum allowed value (inclusive)
        max_val: Maximum allowed value (inclusive), None for no limit
        
    Raises:
        ValidationError: If value is out of range
        
    Example:
        >>> validate_positive_int(10, "timeout", min_val=1, max_val=30)
        >>> validate_positive_int(-1, "timeout")  # Raises ValidationError
    """
    if not isinstance(value, int):
        raise ValidationError(f"{name} must be an integer, got {type(value).__name__}")
    
    if value < min_val:
        raise ValidationError(f"{name} must be >= {min_val}, got {value}")
    
    if max_val is not None and value > max_val:
        raise ValidationError(f"{name} must be <= {max_val}, got {value}")


def validate_http_status_code(status: int) -> None:
    """Validate HTTP status code is in valid range.
    
    Args:
        status: HTTP status code
        
    Raises:
        ValidationError: If status code is invalid
    """
    if not 100 <= status <= 599:
        raise ValidationError(
            f"HTTP status code must be 100-599, got {status}"
        )


def validate_alias(alias: str) -> None:
    """Validate webhook alias format.
    
    Args:
        alias: Webhook alias (subdomain)
        
    Raises:
        ValidationError: If alias format is invalid
        
    Rules:
        - Length: 3-32 characters
        - Characters: alphanumeric, hyphens, underscores only
        - Cannot start/end with hyphen
    """
    if not isinstance(alias, str):
        raise ValidationError("Alias must be a string")
    
    if not 3 <= len(alias) <= 32:
        raise ValidationError(
            f"Alias length must be 3-32 characters, got {len(alias)}"
        )
    
    # Alphanumeric, hyphen, underscore only
    if not re.match(r'^[a-zA-Z0-9_-]+$', alias):
        raise ValidationError(
            "Alias can only contain letters, numbers, hyphens, and underscores"
        )
    
    # Cannot start or end with hyphen
    if alias.startswith('-') or alias.endswith('-'):
        raise ValidationError("Alias cannot start or end with a hyphen")


def validate_expiry(expiry: int) -> None:
    """Validate webhook expiry time.
    
    Args:
        expiry: Expiry time in seconds
        
    Raises:
        ValidationError: If expiry is invalid
        
    Rules:
        - Maximum: 604800 seconds (7 days)
        - Minimum: 0 (no expiry)
    """
    validate_positive_int(expiry, "expiry", min_val=0, max_val=604800)


def sanitize_identifier(identifier: str) -> str:
    """Sanitize user-provided identifier for safe use.
    
    Args:
        identifier: User-provided identifier
        
    Returns:
        Sanitized identifier (alphanumeric and underscores only)
        
    Example:
        >>> sanitize_identifier("my-test_123")
        'my-test_123'
        >>> sanitize_identifier("<script>alert(1)</script>")
        'scriptalert1script'
    """
    # Remove all non-alphanumeric characters except underscore and hyphen
    return re.sub(r'[^a-zA-Z0-9_-]', '', identifier)
