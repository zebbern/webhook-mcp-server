"""Extract URLs and one-time codes from captured email or HTTP bodies."""

from __future__ import annotations

import re
from typing import Any

URL_PATTERN = re.compile(r"""https?://[^\s<>"'\)\]]+""", re.IGNORECASE)
TITLE_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
AUTH_KEYWORDS = ("magic", "auth", "token", "verify", "confirm", "reset", "login")
_KEYWORD_CODE = re.compile(
    r"(?:verification\s+code|one[-\s]?time(?:\s+(?:code|pin|password))?|otp|passcode|pin(?:\s+code)?|\bcode)\s*[:#=\-]\s*(\d{4,8})",
    re.IGNORECASE,
)
_SIX_DIGIT = re.compile(r"\b(\d{6})\b")


def combined_request_text(req: dict[str, Any]) -> str:
    """Join the raw body fields used for link and code extraction."""
    parts = [
        req.get("content") or "",
        req.get("text_content") or "",
        req.get("html_content") or "",
    ]
    return " ".join(part for part in parts if part)


def extract_urls(text: str) -> list[str]:
    """Return unique http(s) URLs, preserving first-seen order."""
    seen: set[str] = set()
    urls: list[str] = []
    for match in URL_PATTERN.findall(text or ""):
        link = match.rstrip(".,;:!?")
        if link not in seen:
            seen.add(link)
            urls.append(link)
    return urls


def extract_auth_links(urls: list[str]) -> list[str]:
    """Keep verify / magic / reset / login style URLs."""
    return [url for url in urls if any(keyword in url.lower() for keyword in AUTH_KEYWORDS)]


def extract_verification_codes(text: str) -> list[str]:
    """Return OTP-style codes, ignoring digits that only appear inside URLs."""
    stripped = URL_PATTERN.sub(" ", text or "")
    seen: set[str] = set()
    codes: list[str] = []
    for match in _KEYWORD_CODE.finditer(stripped):
        code = match.group(1)
        if code not in seen:
            seen.add(code)
            codes.append(code)
    for match in _SIX_DIGIT.finditer(stripped):
        code = match.group(1)
        if code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def extract_html_title(html: str) -> str | None:
    """Return the first HTML title, if present."""
    match = TITLE_PATTERN.search(html or "")
    if not match:
        return None
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    return title or None
