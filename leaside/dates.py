"""Turning whatever a publisher calls a date into something comparable.

Sources give dates as ISO strings, plain dates, ArcGIS epoch milliseconds, and
occasionally nothing at all. An item with no date is never dropped for being old.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

FORMATS = (
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
)


def parse(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if text.isdigit() and len(text) >= 10:  # epoch seconds or milliseconds
        n = int(text)
        return datetime.fromtimestamp(n / 1000 if n > 1e11 else n, tz=timezone.utc)
    cleaned = text.replace("Z", "+0000")
    for fmt in FORMATS:
        try:
            dt = datetime.strptime(cleaned[: len(cleaned)], fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:  # RFC 2822, the shape RSS uses: "Wed, 03 Sep 2025 14:00:00 +0000"
        dt = parsedate_to_datetime(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def within_days(value, days: int) -> bool:
    """True when the date is recent enough, or unreadable. Never silently drop unknowns."""
    dt = parse(value)
    if dt is None:
        return True
    return dt >= datetime.now(timezone.utc) - timedelta(days=days)


def to_iso(value) -> str | None:
    """One canonical shape for storage so text sorting is date sorting: UTC, seconds."""
    dt = parse(value)
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
