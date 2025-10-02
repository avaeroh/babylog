import os
os.environ.setdefault("TESTING", "1")

import pytest
from fastapi.testclient import TestClient
from app.main import app

# 1) Make sure tables exist before any test uses the app
@pytest.fixture(scope="session", autouse=True)
def _bootstrap_db():
    from app.adapters.repositories import init_db  # calls Base.metadata.create_all(bind=engine)
    init_db()
# 2) Clean DB before each test function
@pytest.fixture(autouse=True)
def _clean_db():
    from sqlalchemy import delete
    from app.adapters.db import SessionLocal
    from app.adapters.repositories import Feed, NappyEvent
    s = SessionLocal()
    try:
        s.execute(delete(Feed))
        s.execute(delete(NappyEvent))
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
    return {"x-api-key": os.getenv("API_KEY", "CHANGE_ME_API_KEY")}
