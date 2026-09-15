"""Turning publisher text into plain text.

Feeds send HTML in their summaries. Notices send whatever the clerk typed. The page
autoescapes, so nothing dangerous gets through, but raw tags were being shown as text.
"""
from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup

_WS = re.compile(r"\s+")


def clean(value, limit: int | None = None) -> str | None:
    """Strip tags, unescape entities, collapse whitespace. Empty becomes None."""
    if value is None:
        return None
    text = str(value)
    if "<" in text and ">" in text:
        text = BeautifulSoup(text, "html.parser").get_text(" ")
    text = html.unescape(text)
    text = _WS.sub(" ", text).strip()
    if not text:
        return None
    if limit and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text
