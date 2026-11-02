"""Police call types in the owner's groups, from config/call_types.yaml.

classify("BREAK & ENTER IN PROGRESS") -> ("Break-ins", "Break and enter").
A type on the ignore list is ("Ignore", None): hidden unless asked for.
Anything else not listed is ("Other", None): a type new to this area, shown.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

CONFIG = Path("config/call_types.yaml")


def _norm(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().upper()


@lru_cache(maxsize=4)
def _load(path: str):
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    groups, lookup = [], {}
    for g in raw.get("groups", []):
        groups.append(g["name"])
        for kind, types in (g.get("kinds") or {}).items():
            for t in types:
                lookup[_norm(t)] = (g["name"], kind)
    other = raw.get("other", "Other")
    ignored = raw.get("ignored", "Ignore")
    for t in raw.get("ignore") or []:
        lookup[_norm(t)] = (ignored, None)
    return groups + [other, ignored], lookup, other, ignored


def groups(path: Path | str = CONFIG) -> list[str]:
    """Every group in the owner's order, then Other, then Ignore."""
    return list(_load(str(path))[0])


def other(path: Path | str = CONFIG) -> str:
    return _load(str(path))[2]


def ignored(path: Path | str = CONFIG) -> str:
    return _load(str(path))[3]


def is_ignored(item: dict, path: Path | str = CONFIG) -> bool:
    return classify(call_type_of(item), path)[0] == ignored(path)


def call_type_of(item: dict) -> str:
    """The police's own type for a stored call: from the record, else the title."""
    raw = item.get("raw")
    if isinstance(raw, dict) and raw.get("CALL_TYPE"):
        return _norm(raw["CALL_TYPE"])
    return _norm((item.get("title") or "").split(" near ")[0])


def classify(call_type: str, path: Path | str = CONFIG) -> tuple[str, str | None]:
    _, lookup, other_name, _ = _load(str(path))
    return lookup.get(_norm(call_type), (other_name, None))


def counts(items, path: Path | str = CONFIG, include_ignored: bool = False) -> list[tuple[str, int]]:
    """[(group, n)] in the owner's order, groups with no calls left out.
    Other is counted; Ignore only when asked."""
    n: dict[str, int] = {}
    for it in items:
        g, _ = classify(call_type_of(it), path)
        n[g] = n.get(g, 0) + 1
    order = groups(path)
    if not include_ignored:
        order = order[:-1]
    return [(g, n[g]) for g in order if n.get(g)]
