# app/services/stats.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
import logging

from app.domain.ports import EventRepo  # <-- unified repo

log = logging.getLogger(__name__)

def parse_period(period: str) -> timedelta:
    """
    Parse a compact period string into a timedelta.
    Supported: '<n>h' (hours), '<n>d' (days)
    """
    if not period or len(period) < 2:
        raise ValueError("Invalid period")
    try:
        n, unit = int(period[:-1]), period[-1]
    except Exception:
        raise ValueError("Invalid period")  # noqa: B904
    if n <= 0:
        raise ValueError("Period must be positive")
    if unit == "h":
        return timedelta(hours=n)
    if unit == "d":
        return timedelta(days=n)
    raise ValueError("Invalid period unit (use 'h' or 'd')")

def human_delta(ts: datetime) -> str:
    """
    Convert a datetime into a human-readable difference like:
    '5s ago', '12m ago', '3h 05m ago', '2d ago'
    """
    log.debug("Converting human_delta: ts=%s (tz=%s)", ts, getattr(ts, "tzinfo", None))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    else:
        ts = ts.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    delta = now - ts
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        rem = minutes % 60
        return f"{hours}h {rem:02d}m ago"
    days = hours // 24
    return f"{days}d ago"

def events_stats(repo: EventRepo, period: str, type: Optional[str] = None) -> dict:
    """
    Get event stats for a period like '24h' or '7d'.
    Optionally filter by event `type` (e.g., 'feeding', 'nappy').
    Returns: {"count": int}
    """
    since = datetime.now(timezone.utc) - parse_period(period)
    return repo.stats_since(since, type=type)
