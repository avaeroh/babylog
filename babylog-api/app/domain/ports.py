from __future__ import annotations
from typing import Protocol, Optional, TypedDict, List, Dict, Any
from datetime import datetime
from uuid import UUID

class LastEvent(TypedDict):
    ts: datetime
    data: dict

class EventRow(TypedDict, total=False):
    id: UUID
    ts: datetime
    type: str
    notes: str | None
    tags: List[str] | None
    metadata: Dict[str, Any] | None

class EventRepo(Protocol):
    # Create
    def add(
        self, *,
        ts: datetime,
        type: str,
        notes: Optional[str],
        tags: Optional[List[str]],
        metadata: Optional[Dict[str, Any]],
    ) -> UUID: ...

    # Read
    def get(self, id: UUID) -> Optional[EventRow]: ...
    def list(
        self, *,
        type: Optional[str],
        since: Optional[datetime],
        until: Optional[datetime],
        limit: int,
        cursor: Optional[str],
        sort_desc: bool,
    ) -> tuple[List[EventRow], Optional[str]]: ...
    def last(self, type: Optional[str] = None) -> Optional[LastEvent]: ...

    # Update
    def update(
        self, id: UUID, *,
        ts: Optional[datetime] = None,
        type: Optional[str] = None,
        notes: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[EventRow]: ...

    # Delete
    def delete(self, id: UUID) -> bool: ...
    def delete_last(self, type: Optional[str] = None) -> bool: ...

    # Stats
    def stats_since(self, since: datetime, type: Optional[str] = None) -> dict: ...
