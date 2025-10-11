# alexa-integration/tests/conftest.py
import os
import json
from pathlib import Path
import pytest

# Ensure envs exist for import-time references (lambda_function reads these)
os.environ.setdefault("BABYLOG_BASE_URL", "https://babylog-api.example.com")
os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("HTTP_TIMEOUT_S", "3")
os.environ.setdefault("HTTP_RETRIES", "0")

# Anchor to alexa-integration root (one level up from tests/)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVENTS_DIR = PROJECT_ROOT / "events"

@pytest.fixture
def load_event():
    """
    Load a sample Alexa event JSON from alexa-integration/events.
    Usage: event = load_event("example.json")
    """
    def _loader(filename: str):
        path = EVENTS_DIR / filename
        if not path.exists():
            raise FileNotFoundError(f"No such test event: {path}")
        with path.open("r") as f:
            return json.load(f)
    return _loader
