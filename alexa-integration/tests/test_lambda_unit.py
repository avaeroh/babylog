import importlib
import types
import urllib.parse

# Import the lambda module after envs are set (done in conftest)
lf = importlib.import_module("lambda_function")

# ---- stubs / builders ----

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
        # store the name only to keep assertions simple
        name = getattr(d, "type", None) or getattr(d, "object_type", None) or getattr(d, "__class__", type("x",(object,),{})).__name__
        if hasattr(d, "type"):
            self.directives.append({"type": d.type})
        else:
            self.directives.append({"type": str(name)})
        return self
    def set_card(self, _):
        return self
    @property
    def response(self):
        return {"speech": self.speech, "reprompt": self.reprompt, "directives": self.directives}

def make_hi(intent_name: str, slots: dict | None = None, confirmation_status: str = "NONE"):
    """
    Build a minimal object graph with .request_envelope.request.intent.slots
    so handler code that expects attributes doesn't crash.
    """
    intent_ns = types.SimpleNamespace(
        name=intent_name,
        confirmation_status=confirmation_status,
        slots=slots or {}
    )
    req = types.SimpleNamespace(type="IntentRequest", intent=intent_ns)
    env = types.SimpleNamespace(request=req)
    return types.SimpleNamespace(request_envelope=env, response_builder=DummyRB())

def slot_value(v: str):
    return types.SimpleNamespace(value=v)

def slot_resolution(v: str, rid: str):
    val_obj = types.SimpleNamespace(id=rid, name=v)
    status = types.SimpleNamespace(code=types.SimpleNamespace(value="ER_SUCCESS_MATCH"))
    rpa_item = types.SimpleNamespace(status=status, values=[types.SimpleNamespace(value=val_obj)])
    resolutions = types.SimpleNamespace(resolutions_per_authority=[rpa_item])
    return types.SimpleNamespace(value=v, resolutions=resolutions)

# ---- tests ----

def test_log_event_prompts_for_type_then_confirm(monkeypatch):
    handler = lf.LogEventIntentHandler()

    # Missing event_type -> elicit
    hi1 = make_hi("LogEventIntent", slots={"notes": slot_value("hello")}, confirmation_status="NONE")
    resp1 = handler.handle(hi1)
    assert "type" in (resp1["speech"] or "").lower()
    assert any(d.get("type","").endswith("ElicitSlot") for d in resp1["directives"])

    # With event_type + notes, first turn -> ask to confirm (no HTTP call)
    called = {"n": 0}
    def _no_http(*a, **k):
        called["n"] += 1
        return {}
    monkeypatch.setattr(lf, "_http", _no_http)

    slots2 = {
        "event_type": slot_resolution("Feeding", "feeding"),
        "notes": slot_value("baby seemed hungry"),
    }
    hi2 = make_hi("LogEventIntent", slots=slots2, confirmation_status="NONE")
    resp2 = handler.handle(hi2)
    assert "save" in (resp2["speech"] or "").lower()
    assert any(d.get("type","").endswith("ConfirmIntent") for d in resp2["directives"])
    assert called["n"] == 0  # no HTTP yet

    # Confirmed -> POST /v1/event/{etype}
    seen = {}
    def _ok(method, path, payload=None):
        seen["method"] = method; seen["path"] = path; seen["payload"] = payload; return {}
    monkeypatch.setattr(lf, "_http", _ok)

    hi3 = make_hi("LogEventIntent", slots=slots2, confirmation_status="CONFIRMED")
    resp3 = handler.handle(hi3)
    assert seen["method"] == "POST"
    assert seen["path"] == f"/v1/event/{urllib.parse.quote('feeding')}"
    assert seen["payload"] == {"notes": "baby seemed hungry"}
    assert "saved" in (resp3["speech"] or "").lower()

def test_last_event_calls_correct_endpoint(monkeypatch):
    handler = lf.LastEventIntentHandler()
    slots = {"event_type": slot_resolution("Nappy", "nappy")}
    seen = {}
    def _ok(method, path, payload=None):
        seen["method"] = method; seen["path"] = path; return {"human": "2 hours ago"}
    monkeypatch.setattr(lf, "_http", _ok)

    hi = make_hi("LastEventIntent", slots=slots)
    resp = handler.handle(hi)
    assert seen["method"] == "GET"
    assert seen["path"] == "/v1/event/nappy/last"
    assert "last nappy" in (resp["speech"] or "").lower()

def test_delete_last_event_confirmation_flow(monkeypatch):
    handler = lf.DeleteLastEventIntentHandler()
    slots = {"event_type": slot_resolution("Feeding", "feeding")}

    # Ask to confirm initially
    hi1 = make_hi("DeleteLastEventIntent", slots=slots, confirmation_status="NONE")
    resp1 = handler.handle(hi1)
    assert "delete the last feeding" in (resp1["speech"] or "").lower()

    # Confirmed -> DELETE
    seen = {}
    def _ok(method, path, payload=None):
        seen["method"] = method; seen["path"] = path; return {}
    monkeypatch.setattr(lf, "_http", _ok)

    hi2 = make_hi("DeleteLastEventIntent", slots=slots, confirmation_status="CONFIRMED")
    resp2 = handler.handle(hi2)
    assert seen["method"] == "DELETE"
    assert seen["path"] == "/v1/event/feeding/last"
    assert "deleted" in (resp2["speech"] or "").lower()

def test_stats_events_with_type_and_period(monkeypatch):
    handler = lf.StatsEventsIntentHandler()
    slots = {
        "event_type": slot_resolution("Nappy", "nappy"),
        "period": slot_resolution("last 7 days", "last-7-days"),
    }

    seen = {}
    def _ok(method, path, payload=None):
        seen["method"] = method; seen["path"] = path; return {"count": 5}
    monkeypatch.setattr(lf, "_http", _ok)

    hi = make_hi("StatsEventsIntent", slots=slots)
    resp = handler.handle(hi)
    assert seen["method"] == "GET"
    assert seen["path"] == "/v1/stats/events?period=7d&type=nappy"
    assert "5" in (resp["speech"] or "")

def test_stats_events_without_type_uses_default_period(monkeypatch):
    handler = lf.StatsEventsIntentHandler()
    slots = {
        "period": slot_value("something unrecognized"),  # falls back to DEFAULT_PERIOD -> "7d"
    }

    seen = {}
    def _ok(method, path, payload=None):
        seen["method"] = method; seen["path"] = path; return {"count": 2}
    monkeypatch.setattr(lf, "_http", _ok)

    hi = make_hi("StatsEventsIntent", slots=slots)
    resp = handler.handle(hi)
    assert seen["method"] == "GET"
    assert seen["path"] == "/v1/stats/events?period=7d"
    assert "2" in (resp["speech"] or "")
