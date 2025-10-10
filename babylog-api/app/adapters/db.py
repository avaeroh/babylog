from __future__ import annotations
import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool   # <-- add this

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logger = logging.getLogger(__name__)

TESTING = os.getenv("TESTING") == "1"
DATABASE_URL = os.getenv("DATABASE_URL")

if TESTING:
    logger.info("TESTING mode enabled: using in-memory SQLite DB with StaticPool")
    DATABASE_URL = "sqlite+pysqlite:///:memory:"
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
else:
    if not DATABASE_URL:
        logger.error("DATABASE_URL not set and TESTING=0")
        raise RuntimeError("DATABASE_URL not set")
    logger.info("Connecting to database: %s", DATABASE_URL)
    engine = create_engine(DATABASE_URL, future=True)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
Base = declarative_base()

logger.debug("SessionLocal factory created with engine %s", engine)
logger.debug("Declarative Base initialized")
