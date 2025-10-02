from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timezone

from app.api.deps import api_key_auth, get_session
from app.domain.models import FeedEventIn, NappyEventIn, LastOut, StatsOut
from app.adapters.repositories import SqlFeedRepo, SqlNappyEventRepo
from app.services.stats import feed_stats, nappy_stats, human_delta, parse_period

router = APIRouter()

@router.get("/health")
def health():
    return {"status": "ok"}

# ---------- Writes ----------
@router.post("/log/feedevent", status_code=201)
def log_feed(payload: FeedEventIn, _=Depends(api_key_auth), session: Session = Depends(get_session)):
    repo = SqlFeedRepo(session)
    new_id = repo.add(ts=payload.ts, type=payload.type, side=payload.side,
                      duration_min=payload.duration_min, volume_ml=payload.volume_ml,
                      notes=payload.notes)
    return {"id": new_id}

@router.post("/log/nappyevent", status_code=201)
def log_nappy(payload: NappyEventIn, _=Depends(api_key_auth), session: Session = Depends(get_session)):
    repo = SqlNappyEventRepo(session)
    new_id = repo.add(ts=payload.ts, type=payload.type, notes=payload.notes)
    return {"id": new_id}

# ---------- Deletes ----------
@router.delete("/last/feedevent", status_code=status.HTTP_204_NO_CONTENT)
def delete_last_feed(_=Depends(api_key_auth), session: Session = Depends(get_session)):
    repo = SqlFeedRepo(session)
    deleted = repo.delete_last()
    if not deleted:
        raise HTTPException(status_code=404, detail="No feed events to delete")
    # 204 No Content on success
    return

@router.delete("/last/nappyevent", status_code=status.HTTP_204_NO_CONTENT)
def delete_last_nappy(type: Optional[str] = None, _=Depends(api_key_auth), session: Session = Depends(get_session)):
    """
    If ?type=pee|poo is provided, deletes the latest of that type.
    Otherwise deletes the latest nappy event of any type.
    """
    repo = SqlNappyEventRepo(session)
    deleted = repo.delete_last(type=type)
    if not deleted:
        raise HTTPException(status_code=404, detail="No matching nappy events to delete")
    return

# ---------- Last ----------
@router.get("/last/feedevent", response_model=LastOut)
def last_feed(_=Depends(api_key_auth), session: Session = Depends(get_session)):
    repo = SqlFeedRepo(session)
    last = repo.last()
    if not last:
        raise HTTPException(status_code=404, detail="No feed events")
    return {"ts": last["ts"], "human": human_delta(last["ts"]), "data": last["data"]}

@router.get("/last/nappyevent", response_model=LastOut)
def last_nappy(type: Optional[str] = None, _=Depends(api_key_auth), session: Session = Depends(get_session)):
    repo = SqlNappyEventRepo(session)
    last = repo.last(type=type)
    if not last:
        raise HTTPException(status_code=404, detail="No nappy events")
    return {"ts": last["ts"], "human": human_delta(last["ts"]), "data": last["data"]}

# ---------- Stats ----------
@router.get("/stats/feedevents", response_model=StatsOut)
def stats_feeds(period: str, _=Depends(api_key_auth), session: Session = Depends(get_session)):
    repo = SqlFeedRepo(session)
    data = feed_stats(repo, period)
    return {"period": period, "count": data["count"], "extras": {
        "total_volume_ml": data["total_volume_ml"], "total_duration_min": data["total_duration_min"]
    }}

@router.get("/stats/nappyevents", response_model=StatsOut)
def stats_nappies(period: str, type: Optional[str] = None, _=Depends(api_key_auth), session: Session = Depends(get_session)):
    repo = SqlNappyEventRepo(session)
    data = nappy_stats(repo, period, type=type)
    return {"period": period, "count": data["count"], "extras": {"type": type} if type else None}
