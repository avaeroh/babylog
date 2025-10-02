from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from datetime import datetime, timezone

def _ensure_utc(dt: Optional[datetime]) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

class FeedIn(BaseModel):
    type: Literal["breast", "bottle"]
    side: Optional[Literal["left", "right"]] = None
    duration_min: Optional[int] = Field(default=None, ge=0)
    volume_ml: Optional[int] = Field(default=None, ge=0)
    notes: Optional[str] = None
    ts: Optional[datetime] = None

    @field_validator("ts")
    @classmethod
    def ts_utc(cls, v):
        return _ensure_utc(v)

class NappyEventIn(BaseModel):
    type: Literal["pee", "poo"]
    description: Optional[str] = None
    ts: Optional[datetime] = None

    @field_validator("ts")
    @classmethod
    def ts_utc(cls, v):
        return _ensure_utc(v)

class LastOut(BaseModel):
    ts: datetime
    human: str
    data: dict

class StatsOut(BaseModel):
    period: str
    count: int
    extras: dict | None = None
