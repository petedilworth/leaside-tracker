"""Find the field you mean in a record whose exact key names you were never told.

Two sources - the City Clerk notices and the CKAN collision rows - were parsed with
guessed key names. The guesses for title matched; the guesses for date and link did
not, so 136 notices arrived with no date and no link and looked fine on the surface.
This module replaces guessing with matching: an exact list first, then any key whose
lowercase name contains a wanted fragment and none of the excluded ones.
"""
from __future__ import annotations

from typing import Iterable


def flatten(record: dict, prefix: str = "") -> dict:
    """One level of nesting is enough to see inside {"notice": {...}} shapes."""
    out = {}
    for k, v in record.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict) and not prefix:
            out.update(flatten(v, f"{k}."))
        else:
            out[key] = v
    return out


def _usable(v) -> str | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, str) and v.strip():
        return v.strip()
    if isinstance(v, (int, float)):
        return str(v)
    return None


def pick(record: dict, exact: Iterable[str] = (), contains: Iterable[str] = (),
         exclude: Iterable[str] = (), accept=None) -> tuple[str | None, str | None]:
    """Return (key, value). `contains` is tried in order, so put the best fragment first.

    `accept` is an optional predicate on the value, for cases like "must look like a
    URL", so a field called `link_text` cannot win over a field called `url`.
    """
    flat = flatten(record)
    lower = {k: k.lower() for k in flat}

    def ok(k):
        v = _usable(flat[k])
        return v is not None and (accept is None or accept(v))

    for k in exact:
        if k in flat and ok(k):
            return k, _usable(flat[k])
    excl = tuple(e.lower() for e in exclude)
    for frag in contains:
        frag = frag.lower()
        for k, lk in lower.items():
            if frag in lk and not any(e in lk for e in excl) and ok(k):
                return k, _usable(flat[k])
    return None, None


def keys_with_samples(record: dict, width: int = 60) -> list[tuple[str, str]]:
    """For the health report: every key and a short sample of its value."""
    return [(k, str(v)[:width].replace("\n", " ")) for k, v in flatten(record).items()]


def looks_like_url(v: str) -> bool:
    return v.startswith(("http://", "https://", "/")) and " " not in v.strip()
