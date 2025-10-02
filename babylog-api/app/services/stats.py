# app/services/stats.py
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from app.domain.ports import FeedRepo, NappyEventRepo

def parse_period(period: str) -> timedelta:
    """Parse a period string like '24h' or '7d' into a timedelta."""
    if not period or len(period) < 2:
        raise ValueError("Invalid period")
    n, unit = int(period[:-1]), period[-1]
    if unit == "h":
        return timedelta(hours=n)
    if unit == "d":
        return timedelta(days=n)
    raise ValueError("Invalid period unit (use h or d)")

def human_delta(ts: datetime) -> str:
    log.debug(f"Converting human_delta: ts={ts} ({ts.tzinfo})")
    """
    Convert a datetime into a human-readable difference string like '5m ago' or '2h 30m ago'.
    Handles both naive (no tzinfo) and aware datetimes by normalizing to UTC.
    """
    # Normalize ts to UTC-aware so subtraction is safe across SQLite/Postgres
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
        return f"{hours}h {rem}m ago"
    days = hours // 24
    return f"{days}d ago"

def feed_stats(repo: FeedRepo, period: str) -> dict:
    """Get feed stats for a period like '24h' or '7d'."""
    since = datetime.now(timezone.utc) - parse_period(period)
    return repo.stats_since(since)

def nappy_stats(repo: NappyEventRepo, period: str, type: str | None) -> dict:
    """Get nappy stats for a period like '24h' or '7d', optionally filtered by type."""
    since = datetime.now(timezone.utc) - parse_period(period)
    return repo.stats_since(since, type=type)
