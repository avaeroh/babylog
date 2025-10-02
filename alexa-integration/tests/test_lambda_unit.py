# alexa-integration/tests/test_lambda_unit.py
import importlib
import os
import types
import pytest

# Ensure envs exist for import-time references
os.environ.setdefault("BABYLOG_BASE_URL", "https://babylog-api.example.com")
os.environ.setdefault("API_KEY", "test-key")

lf = importlib.import_module("lambda_function")

class DummyRB:
    def __init__(self):
        self.speech = None
        self.reprompt = None
        self.directives = []
    def speak(self, text):
        self.speech = text; return self
    def ask(self, text):
        self.reprompt = text; return self
    def add_directive(self, d):
        self.directives.append(d); return self
    @property
    def response(self):
        return {"speech": self.speech, "reprompt": self.reprompt, "directives": self.directives}

def make_hi(event):
    """
    Build a minimal object graph with .request_envelope.request.intent.slots
    so handler code that expects attributes doesn't crash.
    """
    req_dict = event["request"]
    intent_dict = req_dict.get("intent", {})
    intent_ns = types.SimpleNamespace(**intent_dict)
    if isinstance(getattr(intent_ns, "slots", None), dict):
        # keep dict; handlers read values out of it
        pass
    else:
        intent_ns.slots = {}
    req = types.SimpleNamespace(type=req_dict.get("type"), intent=intent_ns)
    env = types.SimpleNamespace(request=req)
    return types.SimpleNamespace(request_envelope=env, response_builder=DummyRB())

def test_bottle_first_turn_prompts_confirmation(monkeypatch, load_event):
    event = load_event("bottle_no_confirm.json")
    hi = make_hi(event)

    called = {"n": 0}
    def _no_http(*a, **k):
        called["n"] += 1
        return {}
    monkeypatch.setattr(lf, "_http", _no_http)

    handler = lf.LogBottleFeedIntentHandler()
    resp = handler.handle(hi)
    assert "save" in (resp["speech"] or "").lower()
    assert {"type": "Dialog.ConfirmIntent"} in resp["directives"]
    assert called["n"] == 0

def test_bottle_confirmed_posts(monkeypatch, load_event):
    event = load_event("bottle_confirmed.json")
    hi = make_hi(event)

    seen = {}
    def _ok(method, path, payload=None):
        seen["method"] = method; seen["path"] = path; seen["payload"] = payload
        return {}
    monkeypatch.setattr(lf, "_http", _ok)

    handler = lf.LogBottleFeedIntentHandler()
    resp = handler.handle(hi)
    assert seen["method"] == "POST"
    assert seen["path"] == "/feeds"
    assert seen["payload"]["type"] == "bottle"
    # 4 oz -> about 118 ml
    assert 115 <= seen["payload"]["volume_ml"] <= 120
    assert "saved" in (resp["speech"] or "").lower()

def test_breast_requires_side_then_posts(monkeypatch):
    # Missing side -> elicit
    event_missing = {
      "version":"1.0",
      "request":{"type":"IntentRequest","intent":{"name":"LogBreastFeedIntent","confirmationStatus":"NONE","slots":{}}}
    }
    hi1 = make_hi(event_missing)
    handler = lf.LogBreastFeedIntentHandler()
    resp1 = handler.handle(hi1)
    assert "left or right" in (resp1["speech"] or "").lower()

    # Confirmed with side -> POST
    event = {
      "version": "1.0",
      "request": {
        "type": "IntentRequest",
        "intent": {
          "name": "LogBreastFeedIntent",
          "confirmationStatus": "CONFIRMED",
          "slots": {
            "side": {"name": "side", "value": "left", "confirmationStatus": "NONE"},
            "duration_value": {"name": "duration_value", "value": "15", "confirmationStatus": "NONE"},
            "duration_unit": {"name": "duration_unit", "value": "minutes", "confirmationStatus": "NONE"},
            "notes": {"name": "notes", "value": "sleepy", "confirmationStatus": "NONE"}
          }
        }
      }
    }
    hi2 = make_hi(event)
    seen = {}
    def _ok(method, path, payload=None):
        seen["payload"] = payload; return {}
    monkeypatch.setattr(lf, "_http", _ok)
    resp2 = handler.handle(hi2)
    assert seen["payload"]["type"] == "breast"
    assert seen["payload"]["side"] == "left"
    assert seen["payload"]["duration_min"] == 15
    assert "saved" in (resp2["speech"] or "").lower()

def test_nappy_number_two_maps_to_poo_and_posts(monkeypatch, load_event):
    event = load_event("nappy_confirmed.json")
    hi = make_hi(event)
    seen = {}
    def _ok(method, path, payload=None):
        seen["payload"] = payload; return {}
    monkeypatch.setattr(lf, "_http", _ok)

    handler = lf.LogNappyIntentHandler()
    resp = handler.handle(hi)
    assert seen["payload"]["type"] == "poo"
    assert "saved" in (resp["speech"] or "").lower()
