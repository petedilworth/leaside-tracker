"""Which copy of the code is actually running.

A health report was once sent back describing a database that none of the previous
three sessions' fixes had touched, because the launcher ran without pulling first.
Nothing on the page or in the report said which version produced it, so it took a
round trip to work out. Every output now carries this stamp.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _git(*args) -> str | None:
    try:
        out = subprocess.run(("git", *args), cwd=ROOT, capture_output=True,
                             text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def describe() -> dict:
    """Commit, its date, and how stale it is. Falls back to file dates without git."""
    commit = _git("rev-parse", "--short", "HEAD")
    when = _git("log", "-1", "--format=%cI")
    dirty = bool(_git("status", "--porcelain"))
    if when is None:
        newest = max((p.stat().st_mtime for p in (ROOT / "leaside").rglob("*.py")),
                     default=None)
        if newest:
            when = datetime.fromtimestamp(newest, tz=timezone.utc).isoformat(
                timespec="seconds")
    age_days = None
    if when:
        try:
            age_days = (datetime.now(timezone.utc)
                        - datetime.fromisoformat(when)).total_seconds() / 86400
        except ValueError:
            pass
    return {"commit": commit, "date": when, "age_days": age_days, "dirty": dirty}


def label() -> str:
    v = describe()
    parts = []
    if v["commit"]:
        parts.append(v["commit"] + ("+local changes" if v["dirty"] else ""))
    if v["date"]:
        parts.append("dated " + v["date"][:10])
    if v["age_days"] is not None:
        parts.append(f"{v['age_days']:.0f} days old")
    return " · ".join(parts) or "version unknown"


def warn_if_stale(days: float = 3.0) -> str | None:
    """A sentence to print when the code is old enough that a pull is probably due."""
    v = describe()
    if v["age_days"] is not None and v["age_days"] > days:
        return (f"This code is {v['age_days']:.0f} days old ({v['commit'] or 'unknown'}). "
                "If Claude has sent fixes since, run `git pull` before reading anything "
                "into these results.")
    return None
