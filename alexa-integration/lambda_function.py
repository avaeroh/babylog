# lambda_function.py
# Alexa skill handler for BabyLog — aligned with current OpenAPI spec.
# Endpoints used:
#   POST /log/feedevent
#   POST /log/nappyevent
#   GET  /last/feedevent
#   GET  /stats/feedevents?period=...
#
# Environment variables expected in Lambda:
#   BABYLOG_BASE_URL (e.g., https://babylog-api.example.com)
#   API_KEY          (required; sent as x-api-key)
#   HTTP_TIMEOUT_S   (optional; default 6)
#   HTTP_RETRIES     (optional; default 1)

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
from ask_sdk_model.dialog import (
    ElicitSlotDirective,
    ConfirmIntentDirective,
)

# ----------------- CONFIG -----------------
BASE = os.getenv("BABYLOG_BASE_URL", "https://babylog-api.example.com").rstrip("/")
API_KEY = os.getenv("API_KEY") or ""

TIMEOUT_S = float(os.getenv("HTTP_TIMEOUT_S", "6"))
RETRY = int(os.getenv("HTTP_RETRIES", "1"))

OZ_TO_ML = 29.5735

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

# ---------- Slots & parsing ----------
def get_slot(hi, name: str) -> Optional[str]:
    """
    Return the slot value as a plain string.
    Tolerates both ASK SDK objects (slot.value) and dict-shaped slots ({'value': ...}).
    """
    intent = getattr(hi.request_envelope.request, "intent", None)
    if not intent or not getattr(intent, "slots", None):
        return None
    slot = intent.slots.get(name)
    if not slot:
        return None
    if isinstance(slot, dict):
        return slot.get("value")
    return getattr(slot, "value", None)

def parse_volume(volume_value: Optional[str], volume_unit: Optional[str]) -> Optional[int]:
    """Return millilitres as int, or None if not provided or invalid."""
    if not volume_value:
        return None
    try:
        v = float(volume_value)
    except ValueError:
        return None
    unit_id = (volume_unit or "").lower()
    if unit_id in ("oz", "ounce", "ounces", "fl oz", "fluid ounces"):
        ml = round(v * OZ_TO_ML)
    else:  # default to ml if unit is missing/unknown
        ml = int(round(v))
    if ml < 0:
        return None
    return ml

def parse_duration(duration_value: Optional[str], duration_unit: Optional[str]) -> Optional[int]:
    """Return minutes as int, or None."""
    if not duration_value:
        return None
    try:
        v = float(duration_value)
    except ValueError:
        return None
    unit_id = (duration_unit or "").lower()
    if unit_id in ("h", "hour", "hours", "hr", "hrs"):
        minutes = int(round(v * 60))
    else:  # default to minutes
        minutes = int(round(v))
    if minutes < 0:
        return None
    return minutes

def summarise_bottle(volume_ml: Optional[int], notes: Optional[str]) -> str:
    parts = ["bottle feed"]
    if volume_ml is not None:
        parts.append(f"{volume_ml} millilitres")
    if notes:
        parts.append(f"notes: {notes}")
    return ", ".join(parts)

def summarise_breast(side: Optional[str], duration_min: Optional[int], notes: Optional[str]) -> str:
    parts = ["breast feed"]
    if side:
        parts.append(f"{side} side")
    if duration_min is not None:
        parts.append(f"{duration_min} minutes")
    if notes:
        parts.append(f"notes: {notes}")
    return ", ".join(parts)

def summarise_nappy(nappy_type: str, notes: Optional[str]) -> str:
    pretty = "pee" if nappy_type.lower() in ("pee", "number one", "number 1", "wee", "urine") else "poo"
    parts = [f"{pretty} nappy"]
    if notes:
        parts.append(f"notes: {notes}")
    return ", ".join(parts)

def intent_confirmed(hi) -> Optional[bool]:
    """Return True if intent CONFIRMED, False if DENIED, None if NONE."""
    intent = getattr(hi.request_envelope.request, "intent", None)
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

# ---------- Handlers ----------
class LaunchHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("LaunchRequest")(handler_input)
    def handle(self, handler_input):
        speak = ("Welcome to Baby Log. You can say, log a feed, log a bottle, "
                 "log a breast feed, or log a pee or poo nappy.")
        return handler_input.response_builder.speak(speak).ask("What would you like to do?").response

class HelpHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.HelpIntent")(handler_input)
    def handle(self, handler_input):
        speak = (
            "Here are some things you can say. "
            "Add a poo. Add a nappy event with a number two. "
            "Log a bottle 120 millilitres. "
            "Log a breast feed left for 15 minutes. "
            "Log a feed. "
            "Ask, when was the last feed? Or, how many feeds today?"
        )
        return handler_input.response_builder.speak(speak).ask("What would you like to try?").response

class FallbackHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.FallbackIntent")(handler_input)
    def handle(self, handler_input):
        speak = "Sorry, I didn’t get that. You can say, log a feed, or add a poo."
        return handler_input.response_builder.speak(speak).ask("What would you like to do?").response

class SessionEndedHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("SessionEndedRequest")(handler_input)
    def handle(self, handler_input):
        return handler_input.response_builder.response

class LogFeedIntentHandler(AbstractRequestHandler):
    """Generic feed entry. If no type is provided, ask 'Bottle or breast?'."""
    def can_handle(self, handler_input):
        return is_intent_name("LogFeedIntent")(handler_input)
    def handle(self, handler_input):
        conf = intent_confirmed(handler_input)
        feed_type = (get_slot(handler_input, "feed_type") or "").lower() or None
        notes = get_slot(handler_input, "notes")

        if not feed_type or feed_type not in ("bottle", "breast"):
            prompt = "Bottle or breast?"
            return (
                handler_input.response_builder
                .speak(prompt)
                .ask(prompt)
                .add_directive(ElicitSlotDirective(slot_to_elicit="feed_type"))
                .response
            )

        if feed_type == "bottle":
            volume_ml = parse_volume(get_slot(handler_input, "volume_value"),
                                     get_slot(handler_input, "volume_unit"))
            if conf is None:
                summary = summarise_bottle(volume_ml, notes)
                return (
                    handler_input.response_builder
                    .speak(f"{summary}. Do you want me to save it?")
                    .ask("Shall I save it?")
                    .add_directive(ConfirmIntentDirective())
                    .response
                )
            if conf is False:
                return handler_input.response_builder.speak("Okay, not saved.").response
            payload = {"type": "bottle", "volume_ml": volume_ml, "notes": notes, "ts": None}
            try:
                _http("POST", "/log/feedevent", payload)
                return handler_input.response_builder.speak("Saved your bottle feed.").response
            except Exception:
                return handler_input.response_builder.speak("Sorry, I couldn't reach the baby log API.").response

        # breast
        side = (get_slot(handler_input, "side") or "").lower() or None
        duration_min = parse_duration(get_slot(handler_input, "duration_value"),
                                      get_slot(handler_input, "duration_unit"))
        if not side or side not in ("left", "right"):
            prompt = "Left or right side?"
            return (
                handler_input.response_builder
                .speak(prompt)
                .ask(prompt)
                .add_directive(ElicitSlotDirective(slot_to_elicit="side"))
                .response
            )
        if conf is None:
            summary = summarise_breast(side, duration_min, notes)
            return (
                handler_input.response_builder
                .speak(f"{summary}. Do you want me to save it?")
                .ask("Shall I save it?")
                .add_directive(ConfirmIntentDirective())
                .response
            )
        if conf is False:
            return handler_input.response_builder.speak("Okay, not saved.").response
        payload = {"type": "breast", "side": side, "duration_min": duration_min, "notes": notes, "ts": None}
        try:
            _http("POST", "/log/feedevent", payload)
            return handler_input.response_builder.speak("Saved your breast feed.").response
        except Exception:
            return handler_input.response_builder.speak("Sorry, I couldn't reach the baby log API.").response

class LogBottleFeedIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("LogBottleFeedIntent")(handler_input)
    def handle(self, handler_input):
        conf = intent_confirmed(handler_input)
        notes = get_slot(handler_input, "notes")
        volume_value = get_slot(handler_input, "volume_value")
        volume_unit = get_slot(handler_input, "volume_unit")
        volume_ml = parse_volume(volume_value, volume_unit)

        if conf is None:
            summary = summarise_bottle(volume_ml, notes)
            return (
                handler_input.response_builder
                .speak(f"{summary}. Do you want me to save it?")
                .ask("Shall I save it?")
                .add_directive(ConfirmIntentDirective())
                .response
            )

        if conf is False:
            return handler_input.response_builder.speak("Okay, I won't save it.").response

        payload = {"type": "bottle", "volume_ml": volume_ml, "notes": notes, "ts": None}
        try:
            _http("POST", "/log/feedevent", payload)
            return handler_input.response_builder.speak("Saved your bottle feed.").response
        except Exception:
            return handler_input.response_builder.speak("Sorry, I couldn't reach the baby log API.").response

class LogBreastFeedIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("LogBreastFeedIntent")(handler_input)
    def handle(self, handler_input):
        side = (get_slot(handler_input, "side") or "").lower() or None
        duration_min = parse_duration(get_slot(handler_input, "duration_value"),
                                      get_slot(handler_input, "duration_unit"))
        notes = get_slot(handler_input, "notes")

        if not side or side not in ("left", "right"):
            prompt = "Left or right side?"
            return (
                handler_input.response_builder
                .speak(prompt)
                .ask(prompt)
                .add_directive(ElicitSlotDirective(slot_to_elicit="side"))
                .response
            )

        conf = intent_confirmed(handler_input)
        if conf is None:
            summary = summarise_breast(side, duration_min, notes)
            return (
                handler_input.response_builder
                .speak(f"{summary}. Do you want me to save it?")
                .ask("Shall I save it?")
                .add_directive(ConfirmIntentDirective())
                .response
            )

        if conf is False:
            return handler_input.response_builder.speak("Okay, not saved.").response

        payload = {"type": "breast", "side": side, "duration_min": duration_min, "notes": notes, "ts": None}
        try:
            _http("POST", "/log/feedevent", payload)
            return handler_input.response_builder.speak("Saved your breast feed.").response
        except Exception:
            return handler_input.response_builder.speak("Sorry, I couldn't reach the baby log API.").response

class LogNappyIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("LogNappyIntent")(handler_input)
    def handle(self, handler_input):
        nappy_type = (get_slot(handler_input, "type") or "").lower()
        notes = get_slot(handler_input, "notes")
        if not nappy_type:
            return (
                handler_input.response_builder
                .speak("Was it pee, or poo?")
                .ask("Pee or poo?")
                .add_directive(ElicitSlotDirective(slot_to_elicit="type"))
                .response
            )

        # Normalize “number one/two” → pee/poo
        if "two" in nappy_type or "2" in nappy_type or "poo" in nappy_type or "poop" in nappy_type:
            norm = "poo"
        else:
            norm = "pee"

        conf = intent_confirmed(handler_input)
        if conf is None:
            summary = summarise_nappy(norm, notes)
            return (
                handler_input.response_builder
                .speak(f"{summary}. Shall I save it?")
                .ask("Do you want me to save it?")
                .add_directive(ConfirmIntentDirective())
                .response
            )

        if conf is False:
            return handler_input.response_builder.speak("Okay, not saved.").response

        payload = {"type": norm, "notes": notes, "ts": None}
        try:
            _http("POST", "/log/nappyevent", payload)
            return handler_input.response_builder.speak("Saved your nappy event.").response
        except Exception:
            return handler_input.response_builder.speak("Sorry, I couldn't reach the baby log API.").response

class LastFeedIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("LastFeedIntent")(handler_input)
    def handle(self, handler_input):
        try:
            last = _http("GET", "/last/feedevent")
            human = last.get("human") or last.get("ts") or "recently"
            data = last.get("data", {})
            typ = data.get("type", "feed")
            extra = ""
            if typ == "bottle" and "volume_ml" in data:
                extra = f", {data['volume_ml']} millilitres"
            if typ == "breast" and data.get("side"):
                extra = f", {data['side']} side"
            speak = f"Last feed was {typ}{extra} at {human}."
            return handler_input.response_builder.speak(speak).response
        except Exception:
            return handler_input.response_builder.speak("Sorry, I couldn't fetch the last feed.").response

class StatsIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("StatsIntent")(handler_input)
    def handle(self, handler_input):
        period = get_slot(handler_input, "period") or "today"
        try:
            q = urllib.parse.quote(period)
            stats = _http("GET", f"/stats/feedevents?period={q}")
            count = stats.get("count", 0)
            per = stats.get("period", period)
            return handler_input.response_builder.speak(f"{count} feeds {per}.").response
        except Exception:
            return handler_input.response_builder.speak("Sorry, I couldn't get stats right now.").response

# ---------- Bootstrap ----------
sb = SkillBuilder()
for h in (
    LaunchHandler(),
    HelpHandler(),
    FallbackHandler(),
    SessionEndedHandler(),
    LogFeedIntentHandler(),
    LogBottleFeedIntentHandler(),
    LogBreastFeedIntentHandler(),
    LogNappyIntentHandler(),
    LastFeedIntentHandler(),
    StatsIntentHandler(),
):
    sb.add_request_handler(h)

lambda_handler = sb.lambda_handler()
