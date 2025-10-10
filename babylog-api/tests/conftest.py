import os
# Set test env BEFORE importing app code
os.environ.setdefault("TESTING", "1")
os.environ.setdefault("RESET_ENABLED", "1")  # enable reset in test env

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings

# 1) Make sure tables exist before any test uses the app
@pytest.fixture(scope="session", autouse=True)
def _bootstrap_db():
    # init_db creates the unified 'events' table
    from app.adapters.repositories import init_db
    init_db()

# 2) Clean DB before each test function
@pytest.fixture(autouse=True)
def _clean_db():
    from sqlalchemy import delete
    from app.adapters.db import SessionLocal
    from app.adapters.repositories import Event
    s = SessionLocal()
    try:
        s.execute(delete(Event))
        s.commit()
    finally:
        s.close()

@pytest.fixture
def client():
    # Using context manager ensures startup/shutdown run too (harmless if init_db() already ran)
    with TestClient(app) as c:
        yield c

@pytest.fixture
def auth_headers():
    # Use the app's configured API key to avoid mismatches in tests
    return {"x-api-key": settings.api_key}
