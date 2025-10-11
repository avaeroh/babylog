# tests/test_lambda_helpers.py
import types
import pytest

from lambda_function import (
    normalize_notes,
    resolve_event_type,
    resolve_period,
    intent_confirmed,
)

# --- tiny builder utilities for slot objects the handlers expect ---

def slot_with_value(value: str):
    return types.SimpleNamespace(value=value)

def slot_with_resolution(value: str, rid: str):
    # Build object with .value and .resolutions.resolutions_per_authority[...]
    val_obj = types.SimpleNamespace(id=rid, name=value)
    status = types.SimpleNamespace(code=types.SimpleNamespace(value="ER_SUCCESS_MATCH"))
    rpa_item = types.SimpleNamespace(status=status, values=[types.SimpleNamespace(value=val_obj)])
    resolutions = types.SimpleNamespace(resolutions_per_authority=[rpa_item])
    return types.SimpleNamespace(value=value, resolutions=resolutions)

def make_hi_with_slots(slots: dict):
    intent = types.SimpleNamespace(slots=slots)
    req = types.SimpleNamespace(intent=intent)
    env = types.SimpleNamespace(request=req)
    return types.SimpleNamespace(request_envelope=env)

def make_hi_conf(confirmation_status: str | None):
    req = types.SimpleNamespace(intent=types.SimpleNamespace(confirmation_status=confirmation_status))
    env = types.SimpleNamespace(request=req)
    return types.SimpleNamespace(request_envelope=env)

# --- tests ---

def test_normalize_notes():
    assert normalize_notes(None) is None
    assert normalize_notes("") is None
    assert normalize_notes("  No  ") is None
    assert normalize_notes("something useful") == "something useful"

def test_resolve_event_type_prefers_resolution_id():
    hi = make_hi_with_slots({"event_type": slot_with_resolution("Feeding", "feeding")})
    assert resolve_event_type(hi) == "feeding"

def test_resolve_event_type_falls_back_to_raw():
    hi = make_hi_with_slots({"event_type": slot_with_value("nappy")})
    assert resolve_event_type(hi) == "nappy"

def test_resolve_event_type_invalid():
    hi = make_hi_with_slots({"event_type": slot_with_value("walkies")})
    assert resolve_event_type(hi) is None

def test_resolve_period_mappings():
    # Known id -> 24h / 7d mapping
    hi = make_hi_with_slots({"period": slot_with_resolution("last 24 hours", "last-24-hours")})
    assert resolve_period(hi) == "24h"
    hi = make_hi_with_slots({"period": slot_with_resolution("last 7 days", "last-7-days")})
    assert resolve_period(hi) == "7d"

def test_resolve_period_fallbacks():
    hi = make_hi_with_slots({"period": slot_with_value("in the last week")})
    assert resolve_period(hi) in ("7d",)  # heuristic fallback
    hi = make_hi_with_slots({"period": slot_with_value("something else")})
    assert resolve_period(hi) in ("7d",)  # DEFAULT_PERIOD in lambda is "7d"

def test_intent_confirmed_states():
    assert intent_confirmed(make_hi_conf("NONE")) is None
    assert intent_confirmed(make_hi_conf("CONFIRMED")) is True
    assert intent_confirmed(make_hi_conf("DENIED")) is False
