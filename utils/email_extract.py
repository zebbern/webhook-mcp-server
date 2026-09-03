"""Extract URLs and one-time codes from captured email or HTTP bodies.

Every regular expression here is bounded or linear on purpose: these run on
the MCP event loop for each captured email, and email bodies are attacker
controlled.
"""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

URL_PATTERN = re.compile(
    r"""https?://(?:\[[0-9a-f:.%]+\][^\s<>"'\)\]]*|[^\s<>"'\)\]\[]+)""",
    re.IGNORECASE,
)
TITLE_PATTERN = re.compile(r"<title[^>]*>([^<]{0,500})</title>", re.IGNORECASE)
_URL_END = re.compile(r"""[\s<>"'​‌‍﻿]""")
# Only entities terminated by ';' are decoded, so a raw '&region=eu' or
# '&copy=1' in a plain-text URL is left alone.
_ENTITY = re.compile(r"&(?:#\d{1,7}|#x[0-9a-f]{1,6}|[a-z][a-z0-9]{1,31});", re.IGNORECASE)
_ANCHOR = re.compile(
    r"""<a\b[^>]{0,500}?href\s*=\s*["']?([^"'\s>]+)["']?[^>]{0,500}>((?:[^<]|<(?!/a\b)){0,400}?)</a\s*>""",
    re.IGNORECASE | re.DOTALL,
)

# Link ranking: a URL is an auth link when it scores above zero and is not excluded.
AUTH_KEYWORDS = ("magic", "auth", "token", "verify", "confirm", "reset", "login")
_AUTH_STRONG = re.compile(
    r"(?<![a-z])(?:verif|confirm|activat|magic|reset|validat|approve|passwordless|complete[-_]?sign)",
    re.IGNORECASE,
)
_AUTH_WEAK = re.compile(
    r"(?<![a-z])(?:login|log-?in|sign-?in|auth(?:n|entication|enticate|oriz(?:e|ation))?|"
    r"account|session|oauth|sso|token|otp)(?![a-z])",
    re.IGNORECASE,
)
_AUTH_EXCLUDE_ANY = re.compile(r"unsubscribe|unsub(?![a-z])|opt[-_]?out", re.IGNORECASE)
_AUTH_EXCLUDE_PATH = re.compile(
    r"/preferences|email[-_]?settings|\.(?:png|jpe?g|gif|svg|webp|ico|css|js)$", re.IGNORECASE
)
_AUTH_QUERY_KEYS = {"token", "code", "key", "otp", "hash", "sig", "signature", "nonce", "ticket", "verification"}
_LABEL_STRONG = re.compile(
    r"verif|confirm|activat|magic|reset|validat|approve|complete|get started|accept|join", re.IGNORECASE
)
_LABEL_WEAK = re.compile(r"sign[ -]?in|log[ -]?in|continue|open|access", re.IGNORECASE)

# OTP extraction.
_CODE_NOUN = (
    r"(?:one[-\s]?time(?:\s+(?:code|pin|password|passcode))?|otp|passcode|pin(?:\s+code)?|"
    r"(?:verification|confirmation|security|access|login|sign[-\s]?in|auth(?:entication)?|2fa|sms)\s+code|"
    r"\bcode)"
)
# 4-8 digits, optionally grouped ("123 456", "55 44 33", "1234-5678") or with a
# letter prefix ("G-847291"). The trailing guard stops a following number
# ("847291 10 minutes") from being glued on.
_DIGITS = r"((?:[A-Z]-)?(?:\d{3}[ -]\d{3}|\d{4}[ -]\d{4}|\d{2}(?:[ -]\d{2}){1,2}|\d{4,8}))(?![\w-])"
_KEYWORD_CODE = re.compile(
    _CODE_NOUN + r"\b\s*(?:(?:is|was|:|#|=|-|–|—)\s*){0,2}" + _DIGITS,
    re.IGNORECASE,
)
_CODE_THEN_KEYWORD = re.compile(
    r"(?<![\w#$€£])(?<!\d-)" + _DIGITS
    + r"\s+(?:is|as)\s+(?:your|the)\s+(?:[\w-]+\s+){0,2}(?:code|pin|passcode|password|otp)\b",
    re.IGNORECASE,
)
_NOUN_SKIP = re.compile(
    r"\b(?:zip|postal|post|promo|promotion|discount|coupon|voucher|sort|area|country|dial|qr|bar|"
    r"error|status|referral|invite|invitation|offer|swift|bic|tax|vat|source|http|response|colou?r)\s*$",
    re.IGNORECASE,
)
_SIX_DIGIT = re.compile(r"(?<![\w#$€£.,])(?<!\d-)(?:[A-Z]-)?(\d{6}|\d{3}[ -]\d{3})(?![\w-])")
_FALLBACK_SKIP = re.compile(
    r"(?:#|\b(?:order|invoice|ticket|ref(?:erence)?|account|customer|tracking|transaction|case|"
    r"zip|postal|phone|tel|fax|po box)\b(?:\s+(?:number|no\.?|num|id|#))?\s*(?:is|:|#)?)\s*$",
    re.IGNORECASE,
)
_BLOCK_OPEN = re.compile(r"<(style|script)\b[^>]*>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]{0,2000}>")
_WHITESPACE = re.compile(r"\s+")


def combined_request_text(req: dict[str, Any]) -> str:
    """Join the body fields used for link and code extraction.

    Emails carry the decoded text and HTML parts in ``text_content`` and
    ``html_content``; ``content`` is the raw message (quoted-printable, soft
    wrapped) and is only used when no decoded part exists, as for plain HTTP
    requests.
    """
    decoded = [req.get("text_content") or "", req.get("html_content") or ""]
    parts = [part for part in decoded if part] or [req.get("content") or ""]
    return " ".join(part for part in parts if part)


def unescape_entities(text: str) -> str:
    """Decode HTML entities that are properly terminated by ';' and nothing else."""
    return _ENTITY.sub(lambda match: html.unescape(match.group(0)), text or "")


def normalize_url(url: str) -> str:
    """Undo HTML escaping and stray whitespace around a URL the model passed back."""
    return _clean_link(unescape_entities(url.strip()))


def _clean_link(link: str) -> str:
    """Cut a matched URL at the first terminator and drop trailing punctuation."""
    return _URL_END.split(link, 1)[0].rstrip(".,;:!?")


def extract_urls(text: str) -> list[str]:
    """Return unique http(s) URLs, preserving first-seen order.

    HTML entities inside hrefs (``&amp;``) are decoded so the returned URL is
    the one the site expects to receive.
    """
    seen: set[str] = set()
    urls: list[str] = []
    for match in URL_PATTERN.findall(text or ""):
        link = _clean_link(unescape_entities(match))
        if link and link not in seen:
            seen.add(link)
            urls.append(link)
    return urls


def anchor_labels(text: str) -> dict[str, str]:
    """Map each http(s) href in ``text`` to the visible text of its anchor."""
    labels: dict[str, str] = {}
    for href, inner in _ANCHOR.findall(text or ""):
        if not href.lower().startswith(("http://", "https://")):
            continue
        link = _clean_link(unescape_entities(href))
        label = _WHITESPACE.sub(" ", unescape_entities(_TAG.sub(" ", inner))).strip()
        if link and label and link not in labels:
            labels[link] = label
    return labels


def auth_link_score(url: str, label: str | None = None) -> int:
    """Score how likely a URL is the verify / magic / reset step; 0 means not an auth link.

    ``label`` is the anchor text the link was shown with, which is the only
    signal for click-tracking wrappers whose URL is opaque.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return 0
    if _AUTH_EXCLUDE_ANY.search(url) or _AUTH_EXCLUDE_PATH.search(parsed.path):
        return 0
    score = 0
    if _AUTH_STRONG.search(url):
        score += 3
    keys = {key.lower() for key in parse_qs(parsed.query, keep_blank_values=True)}
    if keys & _AUTH_QUERY_KEYS:
        score += 2
    elif _AUTH_WEAK.search(url):
        score += 1
    if label:
        if _LABEL_STRONG.search(label):
            score += 3
        elif _LABEL_WEAK.search(label):
            score += 1
    return score


def rank_auth_links(urls: list[str], text: str = "") -> list[tuple[int, str]]:
    """Return (score, url) for every auth-looking URL, best first; ties keep body order.

    Pass the body as ``text`` so anchor labels ("Verify your email") can rank
    links whose URL says nothing, such as click-tracking wrappers.
    """
    labels = anchor_labels(text) if text else {}
    scored = [(auth_link_score(url, labels.get(url)), url) for url in urls]
    return sorted((pair for pair in scored if pair[0] > 0), key=lambda pair: -pair[0])


def extract_auth_links(urls: list[str], text: str = "") -> list[str]:
    """Keep verify / magic / reset / login style URLs, best candidate first.

    Unsubscribe, preference and asset links are dropped so they are never
    opened by mistake.
    """
    return [url for _, url in rank_auth_links(urls, text)]


def _strip_blocks(text: str) -> str:
    """Remove <style> and <script> blocks in one linear pass.

    An unclosed block swallows the rest of the document, as in a browser.
    """
    pieces: list[str] = []
    lower = text.lower()
    position = 0
    while True:
        opened = _BLOCK_OPEN.search(text, position)
        if not opened:
            pieces.append(text[position:])
            break
        pieces.append(text[position : opened.start()])
        closing = lower.find(f"</{opened.group(1).lower()}", opened.end())
        if closing == -1:
            break
        end = lower.find(">", closing)
        position = len(text) if end == -1 else end + 1
    return " ".join(pieces)


def _plain_text(text: str) -> str:
    """Drop markup, entities and URLs so only human-readable text remains."""
    without_tags = _TAG.sub(" ", _strip_blocks(text or ""))
    without_urls = URL_PATTERN.sub(" ", html.unescape(without_tags))
    return _WHITESPACE.sub(" ", without_urls)


def _digits(raw: str) -> str:
    return re.sub(r"^[A-Z]-|[ -]", "", raw)


def extract_verification_codes(text: str) -> list[str]:
    """Return OTP-style codes, most likely first.

    Codes introduced by a keyword ("verification code is 512930", "code: 123 456",
    "847291 is your code", "G-847291 is your Google verification code") win.
    A bare six-digit fallback only runs when no keyword form matched, and skips
    colour codes, order / reference numbers and digits glued to other characters.
    """
    plain = _plain_text(text)
    codes: list[str] = []

    def add(raw: str) -> None:
        code = _digits(raw)
        if code not in codes:
            codes.append(code)

    for match in _KEYWORD_CODE.finditer(plain):
        if _NOUN_SKIP.search(plain[max(0, match.start() - 16) : match.start()]):
            continue
        add(match.group(1))
    for match in _CODE_THEN_KEYWORD.finditer(plain):
        add(match.group(1))
    if codes:
        return codes

    for match in _SIX_DIGIT.finditer(plain):
        if _FALLBACK_SKIP.search(plain[max(0, match.start() - 32) : match.start()]):
            continue
        add(match.group(1))
    return codes


def extract_html_title(html_text: str) -> str | None:
    """Return the first HTML title, if present."""
    match = TITLE_PATTERN.search(html_text or "")
    if not match:
        return None
    title = html.unescape(_WHITESPACE.sub(" ", match.group(1))).strip()
    return title or None
