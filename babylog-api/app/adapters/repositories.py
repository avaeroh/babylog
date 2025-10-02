from __future__ import annotations
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Text, TIMESTAMP, func, select, delete
from sqlalchemy.orm import Mapped, mapped_column, Session

from app.adapters.db import Base, engine, SessionLocal
from app.domain.ports import FeedRepo, NappyEventRepo


# ORM models
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
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# Bootstrap tables (v1)
def init_db() -> None:
    Base.metadata.create_all(bind=engine)


# Repositories
class SqlFeedRepo(FeedRepo):
    def __init__(self, session: Session):
        self.session = session

    def add(self, *, ts: datetime, type: str, side: Optional[str],
            duration_min: Optional[int], volume_ml: Optional[int],
            notes: Optional[str]) -> int:
        obj = Feed(ts=ts, type=type, side=side,
                   duration_min=duration_min, volume_ml=volume_ml, notes=notes)
        self.session.add(obj)
        self.session.commit()
        self.session.refresh(obj)
        return obj.id

    def last(self):
        stmt = select(Feed).order_by(Feed.id.desc()).limit(1)
        row = self.session.execute(stmt).scalar_one_or_none()
        if not row:
            return None
        return {"ts": row.ts, "data": {
            "type": row.type, "side": row.side,
            "duration_min": row.duration_min, "volume_ml": row.volume_ml,
            "notes": row.notes
        }}

    def stats_since(self, since: datetime) -> dict:
        count = self.session.execute(
            select(func.count(Feed.id)).where(Feed.ts >= since)
        ).scalar_one() or 0
        total_vol = self.session.execute(
            select(func.coalesce(func.sum(Feed.volume_ml), 0)).where(Feed.ts >= since)
        ).scalar_one() or 0
        total_dur = self.session.execute(
            select(func.coalesce(func.sum(Feed.duration_min), 0)).where(Feed.ts >= since)
        ).scalar_one() or 0
        return {
            "count": int(count),
            "total_volume_ml": int(total_vol),
            "total_duration_min": int(total_dur),
        }

    def delete_last(self) -> bool:
        latest_id = self.session.execute(
            select(Feed.id).order_by(Feed.id.desc()).limit(1)
        ).scalar_one_or_none()
        if latest_id is None:
            return False
        self.session.execute(delete(Feed).where(Feed.id == latest_id))
        self.session.commit()
        return True

class SqlNappyEventRepo(NappyEventRepo):
    def __init__(self, session: Session):
        self.session = session

    def add(self, *, ts: datetime, type: str, description: Optional[str]) -> int:
        obj = NappyEvent(ts=ts, type=type, description=description)
        self.session.add(obj)
        self.session.commit()
        self.session.refresh(obj)
        return obj.id

    def last(self, type: Optional[str] = None):
        stmt = select(NappyEvent).order_by(NappyEvent.id.desc())
        if type:
            stmt = stmt.where(NappyEvent.type == type)
        row = self.session.execute(stmt.limit(1)).scalar_one_or_none()
        if not row:
            return None
        return {"ts": row.ts, "data": {"type": row.type, "description": row.description}}

    def stats_since(self, since: datetime, type: Optional[str] = None) -> dict:
        stmt = select(func.count(NappyEvent.id)).where(NappyEvent.ts >= since)
        if type:
            stmt = stmt.where(NappyEvent.type == type)
        count = self.session.execute(stmt).scalar_one() or 0
        return {"count": int(count)}

    def delete_last(self, type: Optional[str] = None) -> bool:
        sel = select(NappyEvent.id).order_by(NappyEvent.id.desc()).limit(1)
        if type:
            sel = sel.where(NappyEvent.type == type)
        latest_id = self.session.execute(sel).scalar_one_or_none()
        if latest_id is None:
            return False
        self.session.execute(delete(NappyEvent).where(NappyEvent.id == latest_id))
        self.session.commit()
        return True