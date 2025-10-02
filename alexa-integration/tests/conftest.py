# alexa-integration/tests/conftest.py
import json
from pathlib import Path
import pytest

# Anchor to alexa-integration root (one level up from tests/)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVENTS_DIR = PROJECT_ROOT / "events"

@pytest.fixture
def load_event():
    """
    Load a sample Alexa event JSON from alexa-integration/events.
    Usage: event = load_event("bottle_confirmed.json")
    """
    def _loader(filename: str):
        path = EVENTS_DIR / filename
        if not path.exists():
            raise FileNotFoundError(f"No such test event: {path}")
        with path.open("r") as f:
            return json.load(f)
    return _loader
