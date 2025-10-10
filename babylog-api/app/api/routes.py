from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID
from app.config import settings 

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import api_key_auth, get_session
from app.domain.models import (
    EventIn,
    EventUpdate,
    EventOut,
    EventListOut,
    LastOut,
    StatsOut,
)
from app.adapters.repositories import SqlEventRepo
from app.services.stats import events_stats, human_delta, parse_period

# Versioned router
router = APIRouter(prefix="/v1")

# -------------------------------------------------------------------------
# Health
# -------------------------------------------------------------------------
@router.get("/health")
def health():
    return {"status": "ok"}

# -------------------------------------------------------------------------
# Events: CRUD on /v1/events
# -------------------------------------------------------------------------
@router.post("/events", response_model=EventOut, status_code=201)
def create_event(
    payload: EventIn,
    _=Depends(api_key_auth),
    session: Session = Depends(get_session),
):
    repo = SqlEventRepo(session)
    new_id = repo.add(
        ts=payload.ts,
        type=payload.type,
        notes=payload.notes,
        tags=payload.tags,
        metadata=payload.metadata,
    )
    created = repo.get(new_id)
    # Safety: if created somehow None, map to 500
    if not created:
        raise HTTPException(status_code=500, detail="Failed to fetch created event")
    return created  # conforms to EventOut

@router.get("/events", response_model=EventListOut)
def list_events(
    type: Optional[str] = None,
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = None,
    limit: int = Query(50, ge=1, le=500),
    cursor: Optional[str] = None,
    sort: str = Query("ts:desc", pattern="^(ts:(asc|desc))$"),
    _=Depends(api_key_auth),
    session: Session = Depends(get_session),
):
    repo = SqlEventRepo(session)
    sort_desc = sort.endswith(":desc")
    items, next_cursor = repo.list(
        type=type,
        since=from_,
        until=to,
        limit=limit,
        cursor=cursor,
        sort_desc=sort_desc,
    )
    return {"items": items, "next_cursor": next_cursor}

@router.get("/events/{id}", response_model=EventOut)
def get_event(
    id: UUID,
    _=Depends(api_key_auth),
    session: Session = Depends(get_session),
):
    repo = SqlEventRepo(session)
    row = repo.get(id)
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")
    return row

@router.patch("/events/{id}", response_model=EventOut)
def update_event(
    id: UUID,
    payload: EventUpdate,
    _=Depends(api_key_auth),
    session: Session = Depends(get_session),
):
    repo = SqlEventRepo(session)
    updated = repo.update(
        id,
        ts=payload.ts,
        type=payload.type,
        notes=payload.notes,
        tags=payload.tags,
        metadata=payload.metadata,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Event not found")
    return updated

@router.delete("/events/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(
    id: UUID,
    _=Depends(api_key_auth),
    session: Session = Depends(get_session),
):
    repo = SqlEventRepo(session)
    deleted = repo.delete(id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Event not found")
    return  # 204

# -------------------------------------------------------------------------
# Convenience typed endpoints (feeding/nappy/etc.)
# -------------------------------------------------------------------------
@router.post("/event/{etype}", response_model=EventOut, status_code=201)
def create_typed_event(
    etype: str,
    payload: EventUpdate,  # only generic fields; type comes from path
    _=Depends(api_key_auth),
    session: Session = Depends(get_session),
):
    repo = SqlEventRepo(session)
    new_id = repo.add(
        ts=payload.ts or datetime.utcnow(),  # ts validator in models also covers this
        type=etype,
        notes=payload.notes,
        tags=payload.tags,
        metadata=payload.metadata,
    )
    created = repo.get(new_id)
    if not created:
        raise HTTPException(status_code=500, detail="Failed to fetch created event")
    return created

@router.get("/event/{etype}/last", response_model=LastOut)
def last_by_type(
    etype: Optional[str] = None,
    _=Depends(api_key_auth),
    session: Session = Depends(get_session),
):
    repo = SqlEventRepo(session)
    last = repo.last(type=etype)
    if not last:
        raise HTTPException(status_code=404, detail="No events")
    return {"ts": last["ts"], "human": human_delta(last["ts"]), "data": last["data"]}

@router.delete("/event/{etype}/last", status_code=status.HTTP_204_NO_CONTENT)
def delete_last_by_type(
    etype: Optional[str] = None,
    _=Depends(api_key_auth),
    session: Session = Depends(get_session),
):
    repo = SqlEventRepo(session)
    deleted = repo.delete_last(type=etype)
    if not deleted:
        raise HTTPException(status_code=404, detail="No matching events to delete")
    return  # 204
# -------------------------------------------------------------------------
# Stats (top-level namespace)
# -------------------------------------------------------------------------
@router.get("/stats/events", response_model=StatsOut)
def stats_events(
    period: str,
    type: Optional[str] = None,
    _=Depends(api_key_auth),
    session: Session = Depends(get_session),
):
    """
    Stats for events in a period like '24h' or '7d'.
    Optional type filter (e.g., 'feeding', 'nappy').
    """
    # Validate early for clear 400 via your ValueError handler
    parse_period(period)

    repo = SqlEventRepo(session)
    data = events_stats(repo, period, type=type)
    return {"period": period, "count": data["count"], "extras": {"type": type} if type else None}


# -------------------------------------------------------------------------
# Admin: Reset (feature-flag protected)
# -------------------------------------------------------------------------
@router.post("/admin/reset")
def admin_reset(
    _=Depends(api_key_auth),
    session: Session = Depends(get_session),
):
    """
    Deletes all data from the database while keeping tables/schema.
    Protected by API key and RESET_ENABLED=1.
    """
    if not settings.reset_enabled:
        # 403 so it’s clear the endpoint exists but is disabled
        raise HTTPException(
            status_code=403,
            detail="Reset is disabled. Set RESET_ENABLED=1 to enable."
        )

    repo = SqlEventRepo(session)
    deleted = repo.delete_all()
    return {"deleted": deleted}