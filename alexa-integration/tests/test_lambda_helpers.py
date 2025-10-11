# alexa-integration/tests/test_lambda_helpers.py
import importlib

lf = importlib.import_module("lambda_function")

def test_normalize_event_type_aliases():
    # feed -> feeding
    assert lf.normalize_event_type("feed", None) == "feeding"
    assert lf.normalize_event_type("feeding", None) == "feeding"
    # nappy synonyms
    assert lf.normalize_event_type("diaper", None) == "nappy"
    assert lf.normalize_event_type("nappy change", None) == "nappy"
    # unknown -> None
    assert lf.normalize_event_type("walk", None) is None

def test_normalize_notes_negatives_and_trim():
    assert lf.normalize_notes(None) is None
    assert lf.normalize_notes("") is None
    assert lf.normalize_notes("  no  ") is None
    assert lf.normalize_notes("none") is None
    assert lf.normalize_notes("nah") is None
    assert lf.normalize_notes(" some text ") == "some text"
