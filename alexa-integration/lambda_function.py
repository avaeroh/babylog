# lambda_function.py
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
from ask_sdk_model import Response  # noqa: F401
from ask_sdk_model.dialog import ElicitSlotDirective, ConfirmIntentDirective
from ask_sdk_model.ui import SimpleCard

# ----------------- CONFIG -----------------
BASE = os.getenv("BABYLOG_BASE_URL", "https://babylog-api.example.com").rstrip("/")
API_KEY = os.getenv("API_KEY") or ""
TIMEOUT_S = float(os.getenv("HTTP_TIMEOUT_S", "6"))
RETRY = int(os.getenv("HTTP_RETRIES", "1"))

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
            # retry on 5xx
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

# ---------- Normalizers ----------
def normalize_event_type(raw: Optional[str], resolved_id: Optional[str] = None) -> Optional[str]:
    """
    Map freeform user types into API types:
      - "feed" -> "feeding"
      - "feeding" -> "feeding"
      - "nappy", "diaper", "nappy change" -> "nappy"
    Returns None if unrecognized.
    """
    if not raw and not resolved_id:
        return None
    t = (resolved_id or raw or "").strip().lower()
    if t in {"feeding", "feed"}:
        return "feeding"
    if t in {"nappy", "diaper", "nappy change", "nappy event"}:
        return "nappy"
    return None

def normalize_notes(val: Optional[str]) -> Optional[str]:
    """
    Treat common negatives as 'no notes'; otherwise trim. Returns None if empty.
    """
    if not val:
        return None
    t = val.strip()
    if not t:
        return None
    tl = t.lower()
    if tl in {"no", "nope", "none", "nothing", "no notes", "nah"}:
        return None
    return t

# ---------- Handlers ----------
class LaunchHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        speak = (
            "Baby Log is ready. You can say, log a feeding, add a nappy, "
            "ask for the last event, or ask for stats."
        )
        return handler_input.response_builder.speak(speak).ask("What would you like to do?").response

class HelpHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        speak = (
            "Here are some things you can say. "
            "Log a feeding. Add a nappy. "
            "When was the last feeding. When was the last nappy. "
            "How many events in the last seven days. "
            "I may ask if you want to add notes before saving. "
            "What would you like to do?"
        )
        return handler_input.response_builder.speak(speak).ask("What would you like to do?").response

class FallbackHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input):
        speak = "Sorry, I didn’t catch that. You can say, log a feeding, or add a nappy."
        return handler_input.response_builder.speak(speak).ask("What would you like to do?").response

class SessionEndedHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        return handler_input.response_builder.response

# ---- Unified LogEventIntent ----
class LogEventIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("LogEventIntent")(handler_input)

    def handle(self, handler_input):
        conf = intent_confirmed(handler_input)
        raw_type = get_slot_value(handler_input, "event_type")
        etype = normalize_event_type(raw_type, None)
        notes = normalize_notes(get_slot_value(handler_input, "notes"))

        # Need type first
        if not etype:
            prompt = "What event should I log — feeding or nappy?"
            d = ElicitSlotDirective(slot_to_elicit="event_type")
            # make tests see a Dialog directive type
            d.type = "Dialog.ElicitSlot"
            return handler_input.response_builder.speak(prompt).ask(prompt).add_directive(d).response

        # Ask for notes (once) before confirmation if not provided
        if conf is None and notes is None:
            prompt = "Do you want to add any notes? You can say no."
            d = ElicitSlotDirective(slot_to_elicit="notes")
            d.type = "Dialog.ElicitSlot"
            return handler_input.response_builder.speak(prompt).ask(prompt).add_directive(d).response

        # Ask for confirmation if not yet confirmed
        if conf is None:
            summary = f"You're about to log a {etype} event"
            if notes:
                summary += f", notes: {notes}"
            summary += ". Shall I save it?"
            d = ConfirmIntentDirective()
            d.type = "Dialog.ConfirmIntent"
            return handler_input.response_builder.speak(summary).ask("Do you want me to save it?").add_directive(d).response

        # Denied
        if conf is False:
            return handler_input.response_builder.speak("Okay, not saved.").response

        # Confirmed -> POST
        try:
            body = {"type": etype}
            if notes:
                body["notes"] = notes
            _http("POST", f"/v1/event/{etype}", body)
            speak = f"Saved your {etype}."
            card_lines = [f"Saved {etype}"]
            if notes:
                card_lines.append(f"Notes: {notes}")
            handler_input.response_builder.set_card(SimpleCard(title="Baby Log", content="\n".join(card_lines)))
            return handler_input.response_builder.speak(speak).response
        except Exception:
            return handler_input.response_builder.speak("Sorry, I couldn't reach the baby log API.").response

# ---- LastEventIntent ----
class LastEventIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("LastEventIntent")(handler_input)

    def handle(self, handler_input):
        raw_type = get_slot_value(handler_input, "event_type")
        etype = normalize_event_type(raw_type, None)

        if not etype:
            prompt = "Do you want the last feeding or the last nappy?"
            d = ElicitSlotDirective(slot_to_elicit="event_type")
            d.type = "Dialog.ElicitSlot"
            return handler_input.response_builder.speak(prompt).ask(prompt).add_directive(d).response

        try:
            last = _http("GET", f"/v1/event/{etype}/last")
            human = last.get("human") or last.get("ts") or "recently"
            speak = f"Last {etype} was {human}."
            return handler_input.response_builder.speak(speak).response
        except Exception:
            return handler_input.response_builder.speak(f"Sorry, I couldn't fetch the last {etype}.").response

# ---- DeleteLastEventIntent ----
class DeleteLastEventIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("DeleteLastEventIntent")(handler_input)

    def handle(self, handler_input):
        raw_type = get_slot_value(handler_input, "event_type")
        etype = normalize_event_type(raw_type, None)

        if not etype:
            prompt = "Delete the last feeding or the last nappy?"
            d = ElicitSlotDirective(slot_to_elicit="event_type")
            d.type = "Dialog.ElicitSlot"
            return handler_input.response_builder.speak(prompt).ask(prompt).add_directive(d).response

        conf = intent_confirmed(handler_input)
        if conf is None:
            speak = f"You're about to delete the last {etype}. Shall I do that?"
            d = ConfirmIntentDirective()
            d.type = "Dialog.ConfirmIntent"
            return handler_input.response_builder.speak(speak).ask("Do you want me to delete it?").add_directive(d).response

        if conf is False:
            return handler_input.response_builder.speak("Okay, I won't delete it.").response

        try:
            _http("DELETE", f"/v1/event/{etype}/last")
            handler_input.response_builder.set_card(SimpleCard(title="Baby Log", content=f"Deleted last {etype}"))
            return handler_input.response_builder.speak(f"Deleted the last {etype}.").response
        except Exception as e:
            msg = str(e)
            if "HTTP 404" in msg:
                return handler_input.response_builder.speak(f"Sorry, I couldn't find a {etype} to delete.").response
            return handler_input.response_builder.speak(f"Sorry, I couldn't delete the last {etype}.").response

# ---- StatsEventsIntent ----
class StatsEventsIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("StatsEventsIntent")(handler_input)

    def handle(self, handler_input):
        raw_period = (get_slot_value(handler_input, "period") or "").strip()
        raw_type = get_slot_value(handler_input, "event_type")
        etype = normalize_event_type(raw_type, None)

        qp = f"period={urllib.parse.quote(raw_period)}"
        if etype:
            qp += f"&type={urllib.parse.quote(etype)}"

        try:
            stats = _http("GET", f"/v1/stats/events?{qp}")
            count = stats.get("count", 0)
            spoken_period = stats.get("period") or raw_period or "the selected period"
            if etype:
                speak = f"{count} {etype} events {spoken_period}."
            else:
                speak = f"{count} events {spoken_period}."
            return handler_input.response_builder.speak(speak).response
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
