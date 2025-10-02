from __future__ import annotations
from typing import Protocol, Optional, TypedDict
from datetime import datetime

class LastEvent(TypedDict):
    ts: datetime
    data: dict

class FeedRepo(Protocol):
    def add(self, *, ts: datetime, type: str, side: Optional[str],
            duration_min: Optional[int], volume_ml: Optional[int],
            notes: Optional[str]) -> int: ...
    def last(self) -> Optional[LastEvent]: ...
    def stats_since(self, since: datetime) -> dict: ...
    def delete_last(self) -> bool: ...  # <--- NEW

class NappyEventRepo(Protocol):
    def add(self, *, ts: datetime, type: str, notes: Optional[str]) -> int: ...
    def last(self, type: Optional[str] = None) -> Optional[LastEvent]: ...
    def stats_since(self, since: datetime, type: Optional[str] = None) -> dict: ...
    def delete_last(self, type: Optional[str] = None) -> bool: ...  # <--- NEW
