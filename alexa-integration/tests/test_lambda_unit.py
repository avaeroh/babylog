# alexa-integration/tests/test_lambda_unit.py
import importlib
from conftest import make_hi  # absolute import so pytest runs it as a script

lf = importlib.import_module("lambda_function")

# ---------- LogEventIntent ----------

def test_log_event_elicits_type_first():
    hi = make_hi("LogEventIntent")  # no slots at all
    handler = lf.LogEventIntentHandler()
    resp = handler.handle(hi)
    assert "feeding or nappy" in (resp["speech"] or "").lower()
    assert any(d["type"].lower().startswith("dialog.elicitslot") for d in resp["directives"])

def test_log_event_elicits_notes_then_confirms(monkeypatch):
    handler = lf.LogEventIntentHandler()

    # 1) We have type=feeding, no notes, not confirmed -> elicit notes
    hi1 = make_hi("LogEventIntent", slots={"event_type": "feeding"})
    resp1 = handler.handle(hi1)
    assert "notes" in (resp1["speech"] or "").lower()
    assert any(d["type"].lower().startswith("dialog.elicitslot") for d in resp1["directives"])

    # 2) Provide notes, still not confirmed -> ask to confirm (ConfirmIntent)
    hi2 = make_hi("LogEventIntent", slots={"event_type": "feeding", "notes": "sleepy"})
    resp2 = handler.handle(hi2)
    assert "save it" in (resp2["speech"] or "").lower()
    assert any("confirmintent" in d["type"].lower() for d in resp2["directives"])

def test_log_event_confirmed_posts(monkeypatch):
    seen = {}
    def _ok(method, path, payload=None):
        seen["method"] = method; seen["path"] = path; seen["payload"] = payload
        return {}

    monkeypatch.setattr(lf, "_http", _ok)

    hi = make_hi(
        "LogEventIntent",
        slots={"event_type": "feeding", "notes": "bottle 120"},
        confirmation_status="CONFIRMED",
    )
    handler = lf.LogEventIntentHandler()
    resp = handler.handle(hi)
    assert seen["method"] == "POST"
    assert seen["path"] == "/v1/event/feeding"
    assert seen["payload"]["type"] == "feeding"
    assert seen["payload"]["notes"] == "bottle 120"
    assert "saved" in (resp["speech"] or "").lower()

def test_log_event_feed_alias_posts_to_feeding(monkeypatch):
    seen = {}
    def _ok(method, path, payload=None):
        seen["method"] = method; seen["path"] = path; seen["payload"] = payload
        return {}
    monkeypatch.setattr(lf, "_http", _ok)

    hi = make_hi(
        "LogEventIntent",
        slots={"event_type": "feed", "notes": "quick sip"},
        confirmation_status="CONFIRMED",
    )
    handler = lf.LogEventIntentHandler()
    handler.handle(hi)
    assert seen["path"] == "/v1/event/feeding"

# ---------- LastEventIntent ----------

def test_last_event_elicit_type_then_fetch(monkeypatch):
    handler = lf.LastEventIntentHandler()

    # 1) Missing type -> elicit event_type
    hi1 = make_hi("LastEventIntent")
    resp1 = handler.handle(hi1)
    assert "last feeding or the last nappy" in (resp1["speech"] or "").lower()

    # 2) With type=feeding -> GET /last
    seen = {}
    def _ok(method, path, payload=None):
        seen["method"] = method; seen["path"] = path
        return {"human": "2h 5m ago"}
    monkeypatch.setattr(lf, "_http", _ok)

    hi2 = make_hi("LastEventIntent", slots={"event_type": "feeding"})
    resp2 = handler.handle(hi2)
    assert seen["method"] == "GET"
    assert seen["path"] == "/v1/event/feeding/last"
    assert "2h 5m ago" in (resp2["speech"] or "")

# ---------- DeleteLastEventIntent ----------

def test_delete_last_event_confirms_then_deletes(monkeypatch):
    handler = lf.DeleteLastEventIntentHandler()

    # 1) Ask for confirmation
    hi1 = make_hi("DeleteLastEventIntent", slots={"event_type": "nappy"})
    resp1 = handler.handle(hi1)
    assert "delete the last nappy" in (resp1["speech"] or "").lower()
    assert any("confirmintent" in d["type"].lower() for d in resp1["directives"])

    # 2) Confirmed -> DELETE
    seen = {}
    def _ok(method, path, payload=None):
        seen["method"] = method; seen["path"] = path
        return {}
    monkeypatch.setattr(lf, "_http", _ok)

    hi2 = make_hi("DeleteLastEventIntent", slots={"event_type": "nappy"}, confirmation_status="CONFIRMED")
    resp2 = handler.handle(hi2)
    assert seen["method"] == "DELETE"
    assert seen["path"] == "/v1/event/nappy/last"
    assert "deleted the last nappy" in (resp2["speech"] or "").lower()

def test_delete_last_event_404_wording(monkeypatch):
    handler = lf.DeleteLastEventIntentHandler()

    def _not_found(method, path, payload=None):
        raise RuntimeError("HTTP 404: Not Found")
    monkeypatch.setattr(lf, "_http", _not_found)

    hi = make_hi("DeleteLastEventIntent", slots={"event_type": "feeding"}, confirmation_status="CONFIRMED")
    resp = handler.handle(hi)
    assert "couldn't find a feeding to delete" in (resp["speech"] or "").lower()

# ---------- StatsEventsIntent ----------

def test_stats_events_without_type(monkeypatch):
    seen = {}
    def _ok(method, path, payload=None):
        seen["method"] = method; seen["path"] = path
        # Simulate API echoing "period" for speech clarity
        return {"count": 3, "period": "the last seven days"}
    monkeypatch.setattr(lf, "_http", _ok)

    hi = make_hi("StatsEventsIntent", slots={"period": "last 7 days"})
    handler = lf.StatsEventsIntentHandler()
    resp = handler.handle(hi)
    assert seen["method"] == "GET"
    assert seen["path"].startswith("/v1/stats/events?")
    qs = seen["path"].split("?", 1)[1]
    assert "period=" in qs and "type=" not in qs
    assert "3" in (resp["speech"] or "").lower()

def test_stats_events_with_type(monkeypatch):
    seen = {}
    def _ok(method, path, payload=None):
        seen["path"] = path
        return {"count": 5, "period": "today"}
    monkeypatch.setattr(lf, "_http", _ok)

    # "feed" must normalize to "feeding" in the querystring
    hi = make_hi("StatsEventsIntent", slots={"period": "today", "event_type": "feed"})
    handler = lf.StatsEventsIntentHandler()
    handler.handle(hi)
    qs = seen["path"].split("?", 1)[1]
    params = dict(kv.split("=", 1) for kv in qs.split("&"))
    assert params.get("type") == "feeding"
