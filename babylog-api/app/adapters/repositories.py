from __future__ import annotations
from datetime import datetime
from typing import Optional, Callable, TypeVar, List, Dict, Any, Tuple
import logging
import time
from contextlib import contextmanager
from uuid import UUID, uuid4

from sqlalchemy import String, Text, TIMESTAMP, func, select, delete, update, JSON
from sqlalchemy.orm import Mapped, mapped_column, Session
from sqlalchemy.exc import OperationalError

from app.adapters.db import Base, engine, SessionLocal
from app.domain.ports import EventRepo

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logger = logging.getLogger(__name__)
T = TypeVar("T")

@contextmanager
def _commit_or_rollback(session: Session, op_name: str):
    try:
        yield
        session.commit()
        logger.debug("%s: commit successful", op_name)
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s: error, rolling back", op_name)
        session.rollback()
        raise

def _timed(op_name: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    def deco(fn: Callable[..., T]) -> Callable[..., T]:
        def wrapped(*args, **kwargs) -> T:
            start = time.perf_counter()
            logger.debug("%s: start args=%s kwargs=%s", op_name, args[1:], kwargs)
            try:
                return fn(*args, **kwargs)
            finally:
                dur_ms = (time.perf_counter() - start) * 1000
                logger.debug("%s: end (%.2f ms)", op_name, dur_ms)
        return wrapped
    return deco

# -----------------------------------------------------------------------------
# ORM model (unified events)
# -----------------------------------------------------------------------------
class Event(Base):
    __tablename__ = "events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    # 'metadata' is reserved in SQLAlchemy declarative; map to column "metadata"
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSON, nullable=True)

# -----------------------------------------------------------------------------
# Bootstrap tables (v2)
# -----------------------------------------------------------------------------
def init_db() -> None:
    logger.info("Initializing database schema for table: events")
    Base.metadata.create_all(bind=engine)
    logger.debug("Database schema initialization complete")

# -----------------------------------------------------------------------------
# Repository
# -----------------------------------------------------------------------------
class SqlEventRepo(EventRepo):
    def __init__(self, session: Session):
        self.session = session
        logger.debug("SqlEventRepo created with session %s", hex(id(session)))

    @_timed("Event.add")
    def add(
        self, *,
        ts: datetime,
        type: str,
        notes: Optional[str],
        tags: Optional[List[str]],
        metadata: Optional[Dict[str, Any]],
    ) -> UUID:
        logger.info("Adding event: ts=%s type=%s", ts, type)
        obj = Event(ts=ts, type=type, notes=notes, tags=tags, metadata_json=metadata)
        with _commit_or_rollback(self.session, "Event.add"):
            self.session.add(obj)
        self.session.refresh(obj)
        logger.debug("Event.add: inserted id=%s", obj.id)
        return obj.id

    @_timed("Event.get")
    def get(self, id: UUID):
        row = self.session.get(Event, id)
        if not row:
            return None
        return {
            "id": row.id, "ts": row.ts, "type": row.type,
            "notes": row.notes, "tags": row.tags, "metadata": row.metadata_json
        }

    @_timed("Event.list")
    def list(
        self, *,
        type: Optional[str],
        since: Optional[datetime],
        until: Optional[datetime],
        limit: int = 50,
        cursor: Optional[str] = None,
        sort_desc: bool = True,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        stmt = select(Event)
        if type:
            stmt = stmt.where(Event.type == type)
        if since:
            stmt = stmt.where(Event.ts >= since)
        if until:
            stmt = stmt.where(Event.ts <= until)

        if cursor:
            try:
                cur_ts = datetime.fromisoformat(cursor)
                stmt = stmt.where(Event.ts < cur_ts) if sort_desc else stmt.where(Event.ts > cur_ts)
            except Exception:
                logger.warning("Invalid cursor %s ignored", cursor)

        order = Event.ts.desc() if sort_desc else Event.ts.asc()
        stmt = stmt.order_by(order, Event.id.desc()).limit(min(max(limit, 1), 500))

        rows = self.session.execute(stmt).scalars().all()
        items = [{
            "id": r.id, "ts": r.ts, "type": r.type,
            "notes": r.notes, "tags": r.tags, "metadata": r.metadata_json
        } for r in rows]
        next_cursor = rows[-1].ts.isoformat() if rows else None
        return items, next_cursor

    @_timed("Event.last")
    def last(self, type: Optional[str] = None):
        stmt = select(Event).order_by(Event.ts.desc(), Event.id.desc()).limit(1)
        if type:
            stmt = stmt.where(Event.type == type)
        row = self.session.execute(stmt).scalar_one_or_none()
        if not row:
            logger.info("Event.last: no rows found (type=%s)", type)
            return None
        return {"ts": row.ts, "data": {
            "id": str(row.id), "type": row.type,
            "notes": row.notes, "tags": row.tags, "metadata": row.metadata_json
        }}

    @_timed("Event.update")
    def update(
        self, id: UUID, *,
        ts: Optional[datetime] = None,
        type: Optional[str] = None,
        notes: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        values: Dict[str, Any] = {}
        if ts is not None: values["ts"] = ts
        if type is not None: values["type"] = type
        if notes is not None: values["notes"] = notes
        if tags is not None: values["tags"] = tags
        if metadata is not None: values["metadata_json"] = metadata
        if not values:
            return self.get(id)

        with _commit_or_rollback(self.session, "Event.update"):
            try:
                res = self.session.execute(
                    update(Event).where(Event.id == id).values(**values).returning(Event)
                )
                row = res.fetchone()
                obj = row[0] if row else None
            except OperationalError:
                # Fallback for SQLite builds without RETURNING support
                self.session.execute(update(Event).where(Event.id == id).values(**values))
                obj = self.session.get(Event, id)

        if not obj:
            return None
        return {
            "id": obj.id, "ts": obj.ts, "type": obj.type,
            "notes": obj.notes, "tags": obj.tags, "metadata": obj.metadata_json
        }

    @_timed("Event.delete")
    def delete(self, id: UUID) -> bool:
        with _commit_or_rollback(self.session, "Event.delete"):
            res = self.session.execute(delete(Event).where(Event.id == id))
        return (res.rowcount or 0) > 0

    @_timed("Event.delete_last")
    def delete_last(self, type: Optional[str] = None) -> bool:
        sel = select(Event.id).order_by(Event.ts.desc(), Event.id.desc()).limit(1)
        if type:
            sel = sel.where(Event.type == type)
        latest_id = self.session.execute(sel).scalar_one_or_none()
        if latest_id is None:
            logger.info("Event.delete_last: nothing to delete (type=%s)", type)
            return False
        with _commit_or_rollback(self.session, "Event.delete_last"):
            self.session.execute(delete(Event).where(Event.id == latest_id))
        logger.debug("Event.delete_last: deleted id=%s", latest_id)
        return True

    @_timed("Event.stats_since")
    def stats_since(self, since: datetime, type: Optional[str] = None) -> dict:
        logger.info("Event.stats_since: since=%s type=%s", since, type)
        stmt = select(func.count(Event.id)).where(Event.ts >= since)
        if type:
            stmt = stmt.where(Event.type == type)
        count = self.session.execute(stmt).scalar_one() or 0
        return {"count": int(count)}

    @_timed("Event.delete_all")
    def delete_all(self) -> int:
        """Delete all rows from events table. Returns number of rows deleted."""
        with _commit_or_rollback(self.session, "Event.delete_all"):
            res = self.session.execute(delete(Event))
        return int(res.rowcount or 0)