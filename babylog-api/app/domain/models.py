from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from uuid import UUID

def _ensure_utc(dt: Optional[datetime]) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

# -----------------------------------------------------------------------------
# Generic Event models for /v1/events
# -----------------------------------------------------------------------------
class EventBase(BaseModel):
    ts: Optional[datetime] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("ts")
    @classmethod
    def ts_utc(cls, v):
        return _ensure_utc(v)

class EventIn(EventBase):
    type: str = Field(..., description="Event type, e.g., 'feeding', 'nappy'.")

class EventUpdate(EventBase):
    # All optional, partial updates allowed
    type: Optional[str] = None

class EventOut(EventIn):
    id: UUID

class EventListOut(BaseModel):
    items: list[EventOut]
    next_cursor: Optional[str] = None

# -----------------------------------------------------------------------------
# Compatibility outputs
# -----------------------------------------------------------------------------
class LastOut(BaseModel):
    ts: datetime
    human: str
    data: dict

class StatsOut(BaseModel):
    period: str
    count: int
    extras: dict | None = None
