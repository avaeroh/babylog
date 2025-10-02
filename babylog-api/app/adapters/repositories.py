from __future__ import annotations
from datetime import datetime
from typing import Optional, Callable, TypeVar
import logging
import time
from contextlib import contextmanager

from sqlalchemy import String, Integer, Text, TIMESTAMP, func, select, delete
from sqlalchemy.orm import Mapped, mapped_column, Session

from app.adapters.db import Base, engine, SessionLocal
from app.domain.ports import FeedRepo, NappyEventRepo

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logger = logging.getLogger(__name__)
T = TypeVar("T")

@contextmanager
def _commit_or_rollback(session: Session, op_name: str):
    """Commit the transaction; rollback and log on exceptions."""
    try:
        yield
        session.commit()
        logger.debug("%s: commit successful", op_name)
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s: error, rolling back", op_name)
        session.rollback()
        raise

def _timed(op_name: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to time repository operations."""
    def deco(fn: Callable[..., T]) -> Callable[..., T]:
        def wrapped(*args, **kwargs) -> T:
            start = time.perf_counter()
            logger.debug("%s: start args=%s kwargs=%s", op_name, args[1:], kwargs)
            try:
                result = fn(*args, **kwargs)
                return result
            finally:
                dur_ms = (time.perf_counter() - start) * 1000
                logger.debug("%s: end (%.2f ms)", op_name, dur_ms)
        return wrapped
    return deco

# -----------------------------------------------------------------------------
# ORM models
# -----------------------------------------------------------------------------
class Feed(Base):
    __tablename__ = "feeds"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    type: Mapped[str] = mapped_column(String(10), nullable=False)  # 'breast'|'bottle'
    side: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # 'left'|'right'
    duration_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    volume_ml: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class NappyEvent(Base):
    __tablename__ = "nappyevents"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    type: Mapped[str] = mapped_column(String(10), nullable=False)  # 'pee'|'poo'
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

# -----------------------------------------------------------------------------
# Bootstrap tables (v1)
# -----------------------------------------------------------------------------
def init_db() -> None:
    logger.info("Initializing database schema for tables: feeds, nappyevents")
    Base.metadata.create_all(bind=engine)
    logger.debug("Database schema initialization complete")

# -----------------------------------------------------------------------------
# Repositories
# -----------------------------------------------------------------------------
class SqlFeedRepo(FeedRepo):
    def __init__(self, session: Session):
        self.session = session
        logger.debug("SqlFeedRepo created with session %s", hex(id(session)))

    @_timed("Feed.add")
    def add(self, *, ts: datetime, type: str, side: Optional[str],
            duration_min: Optional[int], volume_ml: Optional[int],
            notes: Optional[str]) -> int:
        logger.info("Adding feed: ts=%s type=%s side=%s duration_min=%s volume_ml=%s",
                    ts, type, side, duration_min, volume_ml)
        obj = Feed(ts=ts, type=type, side=side,
                   duration_min=duration_min, volume_ml=volume_ml, notes=notes)
        with _commit_or_rollback(self.session, "Feed.add"):
            self.session.add(obj)
        self.session.refresh(obj)
        logger.debug("Feed.add: inserted id=%s", obj.id)
        return obj.id

    @_timed("Feed.last")
    def last(self):
        stmt = select(Feed).order_by(Feed.id.desc()).limit(1)
        logger.debug("Feed.last: executing %s", stmt)
        row = self.session.execute(stmt).scalar_one_or_none()
        if not row:
            logger.info("Feed.last: no rows found")
            return None
        result = {"ts": row.ts, "data": {
            "type": row.type, "side": row.side,
            "duration_min": row.duration_min, "volume_ml": row.volume_ml,
            "notes": row.notes
        }}
        logger.debug("Feed.last: returning %s", result)
        return result

    @_timed("Feed.stats_since")
    def stats_since(self, since: datetime) -> dict:
        logger.info("Feed.stats_since: since=%s", since)
        count = self.session.execute(
            select(func.count(Feed.id)).where(Feed.ts >= since)
        ).scalar_one() or 0
        total_vol = self.session.execute(
            select(func.coalesce(func.sum(Feed.volume_ml), 0)).where(Feed.ts >= since)
        ).scalar_one() or 0
        total_dur = self.session.execute(
            select(func.coalesce(func.sum(Feed.duration_min), 0)).where(Feed.ts >= since)
        ).scalar_one() or 0
        result = {
            "count": int(count),
            "total_volume_ml": int(total_vol),
            "total_duration_min": int(total_dur),
        }
        logger.debug("Feed.stats_since: result=%s", result)
        return result

    @_timed("Feed.delete_last")
    def delete_last(self) -> bool:
        logger.info("Feed.delete_last: deleting most recent feed")
        latest_id = self.session.execute(
            select(Feed.id).order_by(Feed.id.desc()).limit(1)
        ).scalar_one_or_none()
        if latest_id is None:
            logger.info("Feed.delete_last: nothing to delete")
            return False
        with _commit_or_rollback(self.session, "Feed.delete_last"):
            self.session.execute(delete(Feed).where(Feed.id == latest_id))
        logger.debug("Feed.delete_last: deleted id=%s", latest_id)
        return True


class SqlNappyEventRepo(NappyEventRepo):
    def __init__(self, session: Session):
        self.session = session
        logger.debug("SqlNappyEventRepo created with session %s", hex(id(session)))

    @_timed("NappyEvent.add")
    def add(self, *, ts: datetime, type: str, notes: Optional[str]) -> int:
        logger.info("Adding nappy event: ts=%s type=%s", ts, type)
        obj = NappyEvent(ts=ts, type=type, notes=notes)
        with _commit_or_rollback(self.session, "NappyEvent.add"):
            self.session.add(obj)
        self.session.refresh(obj)
        logger.debug("NappyEvent.add: inserted id=%s", obj.id)
        return obj.id

    @_timed("NappyEvent.last")
    def last(self, type: Optional[str] = None):
        stmt = select(NappyEvent).order_by(NappyEvent.id.desc())
        if type:
            stmt = stmt.where(NappyEvent.type == type)
        logger.debug("NappyEvent.last: executing %s", stmt.limit(1))
        row = self.session.execute(stmt.limit(1)).scalar_one_or_none()
        if not row:
            logger.info("NappyEvent.last: no rows found (type=%s)", type)
            return None
        result = {"ts": row.ts, "data": {"type": row.type, "notes": row.notes}}
        logger.debug("NappyEvent.last: returning %s", result)
        return result

    @_timed("NappyEvent.stats_since")
    def stats_since(self, since: datetime, type: Optional[str] = None) -> dict:
        logger.info("NappyEvent.stats_since: since=%s type=%s", since, type)
        stmt = select(func.count(NappyEvent.id)).where(NappyEvent.ts >= since)
        if type:
            stmt = stmt.where(NappyEvent.type == type)
        logger.debug("NappyEvent.stats_since: executing %s", stmt)
        count = self.session.execute(stmt).scalar_one() or 0
        result = {"count": int(count)}
        logger.debug("NappyEvent.stats_since: result=%s", result)
        return result

    @_timed("NappyEvent.delete_last")
    def delete_last(self, type: Optional[str] = None) -> bool:
        logger.info("NappyEvent.delete_last: deleting most recent event (type=%s)", type)
        sel = select(NappyEvent.id).order_by(NappyEvent.id.desc()).limit(1)
        if type:
            sel = sel.where(NappyEvent.type == type)
        latest_id = self.session.execute(sel).scalar_one_or_none()
        if latest_id is None:
            logger.info("NappyEvent.delete_last: nothing to delete (type=%s)", type)
            return False
        with _commit_or_rollback(self.session, "NappyEvent.delete_last"):
            self.session.execute(delete(NappyEvent).where(NappyEvent.id == latest_id))
        logger.debug("NappyEvent.delete_last: deleted id=%s", latest_id)
        return True
