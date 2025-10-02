# app/adapters/db.py
from __future__ import annotations
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool   # <-- add this

TESTING = os.getenv("TESTING") == "1"
DATABASE_URL = os.getenv("DATABASE_URL")

if TESTING:
    # Single in-memory DB shared across the whole process
    DATABASE_URL = "sqlite+pysqlite:///:memory:"
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
else:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set")
    engine = create_engine(DATABASE_URL, future=True)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
Base = declarative_base()
