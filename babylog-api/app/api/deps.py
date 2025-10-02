from __future__ import annotations
from fastapi import Header, HTTPException, status, Depends
from sqlalchemy.orm import Session
from app.config import settings
from app.adapters.db import SessionLocal

def api_key_auth(x_api_key: str = Header(None)):
    if not x_api_key or x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return True

def get_session() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
