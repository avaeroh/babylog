# lambda_function.py
# Alexa skill handler for BabyLog — aligned with the unified, versioned API.
# Endpoints used:
#   POST   /v1/event/{etype}
#   GET    /v1/event/{etype}/last
#   DELETE /v1/event/{etype}/last
#   GET    /v1/stats/events?period=<Nh|Nd>[&type=<etype>]
#
# Environment variables expected in Lambda:
#   BABYLOG_BASE_URL (e.g., https://babylog-api.example.com)
#   API_KEY          (optional; sent as x-api-key if set)
#   HTTP_TIMEOUT_S   (optional; default 6)
#   HTTP_RETRIES     (optional; default 1)

from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error
import urllib.parse
from typing import Any, Dict, Optional

from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestHandler
from ask_sdk_core.utils import is_request_type, is_intent_name
from ask_sdk_model import Response  # noqa: F401  (type hints)
from ask_sdk_model.dialog import ElicitSlotDirective, ConfirmIntentDirective
from ask_sdk_model.ui import SimpleCard

# ----------------- CONFIG -----------------
BASE = os.getenv("BABYLOG_BASE_URL", "https://babylog-api.example.com").rstrip("/")
API_KEY = os.getenv("API_KEY") or ""
TIMEOUT_S = float(os.getenv("HTTP_TIMEOUT_S", "6"))
RETRY = int(os.getenv("HTTP_RETRIES", "1"))

DEFAULT_PERIOD = "7d"  # if user doesn't specify a period

# ---------- HTTP ----------
def _http(method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = f"{BASE}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["x-api-key"] = API_KEY

    for attempt in range(RETRY + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                b = r.read().decode("utf-8")
                return json.loads(b) if b else {}
        except urllib.error.HTTPError as e:
            if 500 <= e.code < 600 and attempt < RETRY:
                time.sleep(0.15 * (attempt + 1))
                continue
            detail = e.read().decode("utf-8") if e.fp else ""
            raise RuntimeError(f"HTTP {e.code}: {detail or e.reason}")
        except urllib.error.URLError as e:
            if attempt < RETRY:
                time.sleep(0.15 * (attempt + 1))
                continue
            raise RuntimeError(f"Network error: {e.reason}")

# ---------- Slot helpers ----------
def _get_slot_obj(handler_input, name: str):
    intent = getattr(handler_input.request_envelope.request, "intent", None)
    slots = getattr(intent, "slots", None)
    if not slots:
        return None
    return slots.get(name)

def get_slot_value(handler_input, name: str) -> Optional[str]:
    slot = _get_slot_obj(handler_input, name)
    if not slot:
        return None
    if isinstance(slot, dict):
        return slot.get("value")
    return getattr(slot, "value", None)

def get_slot_resolution_id(handler_input, name: str) -> Optional[str]:
    slot = _get_slot_obj(handler_input, name)
    try:
        rpa = slot.resolutions.resolutions_per_authority  # type: ignore[attr-defined]
        for auth in rpa or []:
            code = getattr(getattr(auth, "status", None), "code", None)
            if str(getattr(code, "value", code)) == "ER_SUCCESS_MATCH":
                vals = getattr(auth, "values", None) or []
                if vals and vals[0].value and vals[0].value.id:
                    return vals[0].value.id
    except Exception:
        pass
    return None

def intent_confirmed(handler_input) -> Optional[bool]:
    intent = getattr(handler_input.request_envelope.request, "intent", None)
    if not intent:
        return None
    status = getattr(intent, "confirmation_status", None) or getattr(intent, "confirmationStatus", None)
    if not status:
        return None
    status = str(status)
    if status.endswith("CONFIRMED"):
        return True
    if status.endswith("DENIED"):
        return False
    return None

# ---------- Normalization ----------
def normalize_notes(val: Optional[str]) -> Optional[str]:
    if not val:
        return None
    t = val.strip().lower()
    if t in {"no", "nope", "none", "nothing", "no notes", "nah"}:
        return None
    return val.strip()

def resolve_event_type(handler_input) -> Optional[str]:
    # Resolution ID preferred (from custom slot), otherwise raw value.
    rid = get_slot_resolution_id(handler_input, "event_type")
    raw = (get_slot_value(handler_input, "event_type") or "").strip().lower()
    etype = (rid or raw) or None
    if etype in {"feeding", "nappy"}:
        return etype
    return None

# Alexa "period" slot → API period string ('Nh' or 'Nd')
_PERIOD_ID_TO_API = {
    "last-24-hours": "24h",
    "last-7-days": "7d",
    "today": "24h",      # approximate (your API doesn't do "since midnight")
    "yesterday": "24h",  # simple approximation
    "this-week": "7d",
    "last-week": "7d",
    "this-month": "7d",  # conservative default
    "last-month": "7d",
}

def resolve_period(handler_input) -> str:
    rid = get_slot_resolution_id(handler_input, "period")
    if rid and rid in _PERIOD_ID_TO_API:
        return _PERIOD_ID_TO_API[rid]
    raw = (get_slot_value(handler_input, "period") or "").strip().lower()
    # very light fallback parsing
    if "24" in raw:
        return "24h"
    if "7" in raw or "week" in raw:
        return "7d"
    return DEFAULT_PERIOD

# ---------- Handlers ----------
class LaunchHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("LaunchRequest")(handler_input)
    def handle(self, handler_input):
        speak = "Baby Log is ready. You can log a feeding or a nappy, ask for the last event, or get stats."
        return handler_input.response_builder.speak(speak).ask("What would you like to do?").response

class HelpHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.HelpIntent")(handler_input)
    def handle(self, handler_input):
        speak = (
            "Try saying: log a feeding with notes, or log a nappy with notes. "
            "Ask: when was the last feeding, or last nappy. "
            "For stats: how many events in the last seven days, or how many nappy events last week. "
            "To undo: delete last feeding or delete last nappy."
        )
        return handler_input.response_builder.speak(speak).ask("What would you like to do?").response

class FallbackHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.FallbackIntent")(handler_input)
    def handle(self, handler_input):
        speak = "Sorry, I didn’t get that. You can say, log a feeding, add a nappy, or ask for stats."
        return handler_input.response_builder.speak(speak).ask("What would you like to do?").response

class SessionEndedHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("SessionEndedRequest")(handler_input)
    def handle(self, handler_input):
        return handler_input.response_builder.response

# --- Create event ---
class LogEventIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("LogEventIntent")(handler_input)
    def handle(self, handler_input):
        etype = resolve_event_type(handler_input)
        if not etype:
            prompt = "What type of event — feeding or nappy?"
            return handler_input.response_builder.speak(prompt).ask(prompt)\
                .add_directive(ElicitSlotDirective(slot_to_elicit="event_type")).response

        notes = normalize_notes(get_slot_value(handler_input, "notes"))
        conf = intent_confirmed(handler_input)
        if conf is None:
            summary = f"You're about to log a {etype}"
            if notes:
                summary += f" with notes: {notes}"
            summary += ". Shall I save it?"
            return handler_input.response_builder.speak(summary).ask("Do you want me to save it?")\
                .add_directive(ConfirmIntentDirective()).response
        if conf is False:
            return handler_input.response_builder.speak("Okay, not saved.").response

        try:
            body = {"notes": notes}  # ts is optional; server will set default
            _http("POST", f"/v1/event/{urllib.parse.quote(etype)}", body)
            card = f"Saved {etype}" + (f"\nNotes: {notes}" if notes else "")
            handler_input.response_builder.set_card(SimpleCard(title="Baby Log", content=card))
            return handler_input.response_builder.speak(f"Saved your {etype} event.").response
        except Exception:
            return handler_input.response_builder.speak("Sorry, I couldn't reach the baby log API.").response

# --- Last by type ---
class LastEventIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("LastEventIntent")(handler_input)
    def handle(self, handler_input):
        etype = resolve_event_type(handler_input)
        if not etype:
            prompt = "Which type — feeding or nappy?"
            return handler_input.response_builder.speak(prompt).ask(prompt)\
                .add_directive(ElicitSlotDirective(slot_to_elicit="event_type")).response
        try:
            last = _http("GET", f"/v1/event/{urllib.parse.quote(etype)}/last")
            human = last.get("human") or last.get("ts") or "recently"
            speak = f"Last {etype} was {human}."
            return handler_input.response_builder.speak(speak).response
        except Exception:
            return handler_input.response_builder.speak(f"Sorry, I couldn't fetch the last {etype}.").response

# --- Delete last by type ---
class DeleteLastEventIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("DeleteLastEventIntent")(handler_input)
    def handle(self, handler_input):
        etype = resolve_event_type(handler_input)
        if not etype:
            prompt = "Delete last which type — feeding or nappy?"
            return handler_input.response_builder.speak(prompt).ask(prompt)\
                .add_directive(ElicitSlotDirective(slot_to_elicit="event_type")).response

        conf = intent_confirmed(handler_input)
        if conf is None:
            speak = f"You're about to delete the last {etype}. Shall I do that?"
            return handler_input.response_builder.speak(speak).ask("Do you want me to delete it?")\
                .add_directive(ConfirmIntentDirective()).response
        if conf is False:
            return handler_input.response_builder.speak("Okay, I won't delete it.").response

        try:
            _http("DELETE", f"/v1/event/{urllib.parse.quote(etype)}/last")
            handler_input.response_builder.set_card(SimpleCard(title="Baby Log", content=f"Deleted last {etype}"))
            return handler_input.response_builder.speak(f"Deleted the last {etype}.").response
        except Exception:
            return handler_input.response_builder.speak(f"Sorry, I couldn't delete the last {etype}.").response

# --- Stats (optionally by type) ---
class StatsEventsIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("StatsEventsIntent")(handler_input)
    def handle(self, handler_input):
        period = resolve_period(handler_input)
        etype = resolve_event_type(handler_input)  # optional
        try:
            qp = f"period={urllib.parse.quote(period)}"
            if etype:
                qp += f"&type={urllib.parse.quote(etype)}"
            stats = _http("GET", f"/v1/stats/events?{qp}")
            count = stats.get("count", 0)
            noun = f"{etype} events" if etype else "events"
            return handler_input.response_builder.speak(f"{count} {noun} in the last {period}.").response
        except Exception:
            return handler_input.response_builder.speak("Sorry, I couldn't get stats right now.").response

# ---------- Bootstrap ----------
sb = SkillBuilder()
for h in (
    LaunchHandler(),
    HelpHandler(),
    FallbackHandler(),
    SessionEndedHandler(),
    LogEventIntentHandler(),
    LastEventIntentHandler(),
    DeleteLastEventIntentHandler(),
    StatsEventsIntentHandler(),
):
    sb.add_request_handler(h)

lambda_handler = sb.lambda_handler()
