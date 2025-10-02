# tests/test_lambda_helpers.py
import types
import pytest

from lambda_function import (
    parse_volume, parse_duration, summarise_bottle, summarise_breast,
    summarise_nappy, intent_confirmed, OZ_TO_ML
)

def test_parse_volume_ml():
    assert parse_volume("120", "ml") == 120
    assert parse_volume("120", None) == 120  # default to ml
    assert parse_volume("-5", "ml") is None

def test_parse_volume_oz_to_ml_rounding():
    assert parse_volume("4", "oz") == round(4 * OZ_TO_ML)
    assert parse_volume("3.5", "ounces") == round(3.5 * OZ_TO_ML)

def test_parse_duration_minutes_and_hours():
    assert parse_duration("15", "min") == 15
    assert parse_duration("1", "hours") == 60
    assert parse_duration("1.5", "h") == 90
    assert parse_duration("-1", "min") is None

def test_summaries():
    assert "bottle feed, 120 millilitres" in summarise_bottle(120, None)
    assert "notes: test" in summarise_bottle(120, "test")
    s = summarise_breast("left", 15, "sleepy")
    assert "left side" in s and "15 minutes" in s and "notes: sleepy" in s
    assert "pee nappy" in summarise_nappy("pee", None)
    assert "poo nappy" in summarise_nappy("number two", "messy")

def make_hi(confirmation_status: str | None):
    """Build a tiny stub with the shape used by intent_confirmed()."""
    req = types.SimpleNamespace(intent=types.SimpleNamespace(confirmation_status=confirmation_status))
    env = types.SimpleNamespace(request=req)
    return types.SimpleNamespace(request_envelope=env)

def test_intent_confirmed_states():
    assert intent_confirmed(make_hi("NONE")) is None
    assert intent_confirmed(make_hi("CONFIRMED")) is True
    assert intent_confirmed(make_hi("DENIED")) is False
