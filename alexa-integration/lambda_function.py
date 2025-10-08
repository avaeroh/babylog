# lambda_function.py
# Alexa skill handler for BabyLog — aligned with your OpenAPI spec.
# Endpoints used:
#   POST   /log/feedevent
#   POST   /log/nappyevent
#   GET    /last/feedevent
#   GET    /last/nappyevent[?type=pee|poo]
#   DELETE /last/feedevent
#   DELETE /last/nappyevent[?type=pee|poo]
#   GET    /stats/feedevents?period=...
#   GET    /stats/nappyevents?period=...[&type=pee|poo]
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

OZ_TO_ML = 29.5735
DEFAULT_PERIOD_ID = "last-7-days"  # canonical period we pass to API when not specified

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

# ---------- Slot helpers & parsing ----------
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

def parse_volume(volume_value: Optional[str], volume_unit: Optional[str]) -> Optional[int]:
    if not volume_value:
        return None
    try:
        v = float(volume_value)
    except ValueError:
        return None
    unit_id = (volume_unit or "").lower()
    if unit_id in ("oz", "ounce", "ounces", "fl oz", "fluid ounces"):
        ml = round(v * OZ_TO_ML)
    else:
        ml = int(round(v))
    if ml < 0:
        return None
    return ml

def parse_duration(duration_value: Optional[str], duration_unit: Optional[str]) -> Optional[int]:
    if not duration_value:
        return None
    try:
        v = float(duration_value)
    except ValueError:
        return None
    unit_id = (duration_unit or "").lower()
    if unit_id in ("h", "hour", "hours", "hr", "hrs"):
        minutes = int(round(v * 60))
    else:
        minutes = int(round(v))
    if minutes < 0:
        return None
    return minutes

def normalise_nappy(raw_value: Optional[str], resolved_id: Optional[str]) -> Optional[str]:
    if resolved_id in ("pee", "poo"):
        return resolved_id
    t = (raw_value or "").strip().lower()
    if not t:
        return None
    if "two" in t or t == "2" or "poo" in t or "poop" in t or "pooh" in t or "stool" in t or "faec" in t:
        return "poo"
    if "one" in t or t == "1" or "pee" in t or "wee" in t or "urine" in t:
        return "pee"
    return None

def mentions_both_types(raw_value: Optional[str]) -> bool:
    if not raw_value:
        return False
    t = raw_value.strip().lower()
    return (
        ("pee" in t and ("poo" in t or "poop" in t or "pooh" in t)) or
        ("number one" in t and "number two" in t) or
        ("1" in t and "2" in t)
    )

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

# ---------- Period canonicalization ----------
# Fallback map if ER doesn't return an id (rare, but defensive)
_PERIOD_FALLBACK = {
    "today": "today",
    "yesterday": "yesterday",
    "last 24 hours": "last-24-hours",
    "past 24 hours": "last-24-hours",
    "in the last 24 hours": "last-24-hours",
    "last day": "last-24-hours",
    "past day": "last-24-hours",
    "last 7 days": "last-7-days",
    "last seven days": "last-7-days",
    "past 7 days": "last-7-days",
    "last week": "last-week",
    "past week": "last-7-days",
    "in the last week": "last-7-days",
    "over the last week": "last-7-days",
    "this week": "this-week",
    "current week": "this-week",
    "this month": "this-month",
    "current month": "this-month",
    "last month": "last-month",
    "previous month": "last-month",
}

_PERIOD_SPOKEN = {
    "today": "today",
    "yesterday": "yesterday",
    "last-24-hours": "the last twenty four hours",
    "last-7-days": "the last seven days",
    "this-week": "this week",
    "last-week": "last week",
    "this-month": "this month",
    "last-month": "last month",
}

def resolve_period_id(handler_input) -> str:
    rid = get_slot_resolution_id(handler_input, "period")
    if rid:
        return rid
    raw = (get_slot_value(handler_input, "period") or "").strip().lower()
    if raw in _PERIOD_FALLBACK:
        return _PERIOD_FALLBACK[raw]
    return DEFAULT_PERIOD_ID

def period_id_to_spoken(pid: str) -> str:
    return _PERIOD_SPOKEN.get(pid, pid.replace("-", " "))

# ---------- Speech helpers ----------
def say_nappy_type(t: Optional[str]) -> str:
    if t == "pee":
        return "number one"
    if t == "poo":
        return "number two"
    return "nappy"

# ---------- Notes normalization helper ----------
def normalize_notes(val: Optional[str]) -> Optional[str]:
    """
    Treat common negative responses as 'no notes'.
    Leaves other content untouched (including freeform dictation).
    """
    if not val:
        return None
    t = val.strip().lower()
    if t in {"no", "nope", "none", "nothing", "no notes", "nah"}:
        return None
    return val.strip()

# ---------- Handlers ----------
class LaunchHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("LaunchRequest")(handler_input)
    def handle(self, handler_input):
        speak = "Baby Log is ready, how can I help?"
        return handler_input.response_builder.speak(speak).ask("How can I help?").response

class HelpHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.HelpIntent")(handler_input)
    def handle(self, handler_input):
        speak = (
            "You can log feeds and nappies, check the last event, get stats, or undo the last entry. "
            "For feeds: say, log a bottle — volume is optional; or log a breast feed — left or right is required, duration is optional. "
            "You can add notes to any log. "
            "For nappies: say, add a nappy and tell me number one or number two. "
            "Ask, when was the last feed, or, when was the last nappy — you can say latest nappy. "
            "For stats, say: how many feeds today, or nappies last seven days. "
            "If you don’t specify a period, I’ll use the last seven days. "
            "To undo, say: delete last feed, or delete last number one."
        )
        return handler_input.response_builder.speak(speak).ask("What would you like to do?").response

class FallbackHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.FallbackIntent")(handler_input)
    def handle(self, handler_input):
        speak = "Sorry, I didn’t get that. You can say, log a feed, add a number one, or ask for stats."
        return handler_input.response_builder.speak(speak).ask("What would you like to do?").response

class SessionEndedHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("SessionEndedRequest")(handler_input)
    def handle(self, handler_input):
        return handler_input.response_builder.response

class LogFeedIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("LogFeedIntent")(handler_input)
    def handle(self, handler_input):
        conf = intent_confirmed(handler_input)
        feed_type = (get_slot_value(handler_input, "feed_type") or "").lower() or None
        notes = normalize_notes(get_slot_value(handler_input, "notes"))

        if not feed_type or feed_type not in ("bottle", "breast"):
            prompt = "Bottle or breast?"
            return handler_input.response_builder.speak(prompt).ask(prompt)\
                .add_directive(ElicitSlotDirective(slot_to_elicit="feed_type")).response

        # Ask for notes before confirmation if we have the type but no notes yet.
        if conf is None and notes is None:
            prompt = "Do you have any notes to add? You can say no."
            return handler_input.response_builder.speak(prompt).ask(prompt)\
                .add_directive(ElicitSlotDirective(slot_to_elicit="notes")).response

        if feed_type == "bottle":
            volume_ml = parse_volume(get_slot_value(handler_input, "volume_value"),
                                     get_slot_value(handler_input, "volume_unit"))
            if conf is None:
                summary = "You're about to log a bottle feed"
                if volume_ml is not None:
                    summary += f", {volume_ml} millilitres"
                if notes:
                    summary += f", notes: {notes}"
                summary += ". Shall I save it?"
                return handler_input.response_builder.speak(summary).ask("Do you want me to save it?")\
                    .add_directive(ConfirmIntentDirective()).response
            if conf is False:
                return handler_input.response_builder.speak("Okay, not saved.").response

            payload = {"type": "bottle", "volume_ml": volume_ml, "notes": notes, "ts": None}
            try:
                _http("POST", "/log/feedevent", payload)
                lines = ["Saved bottle"]
                if volume_ml is not None: lines.append(f"Volume: {volume_ml} ml")
                if notes: lines.append(f"Notes: {notes}")
                handler_input.response_builder.set_card(SimpleCard(title="Baby Log", content="\n".join(lines)))
                return handler_input.response_builder.speak("Saved your bottle feed.").response
            except Exception:
                return handler_input.response_builder.speak("Sorry, I couldn't reach the baby log API.").response

        # breast
        side = (get_slot_value(handler_input, "side") or "").lower() or None
        duration_min = parse_duration(get_slot_value(handler_input, "duration_value"),
                                      get_slot_value(handler_input, "duration_unit"))
        if not side or side not in ("left", "right"):
            prompt = "Left or right side?"
            return handler_input.response_builder.speak(prompt).ask(prompt)\
                .add_directive(ElicitSlotDirective(slot_to_elicit="side")).response

        # Ask for notes before confirmation once side is known.
        if conf is None and notes is None:
            prompt = "Do you have any notes to add? You can say no."
            return handler_input.response_builder.speak(prompt).ask(prompt)\
                .add_directive(ElicitSlotDirective(slot_to_elicit="notes")).response

        if conf is None:
            summary = f"You're about to log a breast feed on the {side} side"
            if duration_min is not None:
                summary += f" for {duration_min} minutes"
            notes = normalize_notes(get_slot_value(handler_input, "notes"))
            if notes:
                summary += f", notes: {notes}"
            summary += ". Shall I save it?"
            return handler_input.response_builder.speak(summary).ask("Do you want me to save it?")\
                .add_directive(ConfirmIntentDirective()).response

        if conf is False:
            return handler_input.response_builder.speak("Okay, not saved.").response

        payload = {"type": "breast", "side": side, "duration_min": duration_min, "notes": notes, "ts": None}
        try:
            _http("POST", "/log/feedevent", payload)
            lines = ["Saved breast feed", f"Side: {side}"]
            if duration_min is not None: lines.append(f"Duration: {duration_min} min")
            if notes: lines.append(f"Notes: {notes}")
            handler_input.response_builder.set_card(SimpleCard(title="Baby Log", content="\n".join(lines)))
            return handler_input.response_builder.speak("Saved your breast feed.").response
        except Exception:
            return handler_input.response_builder.speak("Sorry, I couldn't reach the baby log API.").response

class LogBottleFeedIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("LogBottleFeedIntent")(handler_input)
    def handle(self, handler_input):
        conf = intent_confirmed(handler_input)
        notes = normalize_notes(get_slot_value(handler_input, "notes"))
        volume_value = get_slot_value(handler_input, "volume_value")
        volume_unit = get_slot_value(handler_input, "volume_unit")
        volume_ml = parse_volume(volume_value, volume_unit)

        # Ask for notes once we have enough info, before confirmation.
        if conf is None and volume_ml is not None and notes is None:
            prompt = "Do you have any notes to add? You can say no."
            return handler_input.response_builder.speak(prompt).ask(prompt)\
                .add_directive(ElicitSlotDirective(slot_to_elicit="notes")).response

        if conf is None:
            summary = "You're about to log a bottle feed"
            if volume_ml is not None:
                summary += f", {volume_ml} millilitres"
            if notes:
                summary += f", notes: {notes}"
            summary += ". Shall I save it?"
            return handler_input.response_builder.speak(summary).ask("Do you want me to save it?")\
                .add_directive(ConfirmIntentDirective()).response

        if conf is False:
            return handler_input.response_builder.speak("Okay, I won't save it.").response

        payload = {"type": "bottle", "volume_ml": volume_ml, "notes": notes, "ts": None}
        try:
            _http("POST", "/log/feedevent", payload)
            lines = ["Saved bottle"]
            if volume_ml is not None: lines.append(f"Volume: {volume_ml} ml")
            if notes: lines.append(f"Notes: {notes}")
            handler_input.response_builder.set_card(SimpleCard(title="Baby Log", content="\n".join(lines)))
            return handler_input.response_builder.speak("Saved your bottle feed.").response
        except Exception:
            return handler_input.response_builder.speak("Sorry, I couldn't reach the baby log API.").response

class LogBreastFeedIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("LogBreastFeedIntent")(handler_input)
    def handle(self, handler_input):
        side = (get_slot_value(handler_input, "side") or "").lower() or None
        duration_min = parse_duration(get_slot_value(handler_input, "duration_value"),
                                      get_slot_value(handler_input, "duration_unit"))
        notes = normalize_notes(get_slot_value(handler_input, "notes"))

        if not side or side not in ("left", "right"):
            prompt = "Left or right side?"
            return handler_input.response_builder.speak(prompt).ask(prompt)\
                .add_directive(ElicitSlotDirective(slot_to_elicit="side")).response

        conf = intent_confirmed(handler_input)

        # Ask for notes before confirmation.
        if conf is None and notes is None:
            prompt = "Do you have any notes to add? You can say no."
            return handler_input.response_builder.speak(prompt).ask(prompt)\
                .add_directive(ElicitSlotDirective(slot_to_elicit="notes")).response

        if conf is None:
            summary = f"You're about to log a breast feed on the {side} side"
            if duration_min is not None:
                summary += f" for {duration_min} minutes"
            if notes:
                summary += f", notes: {notes}"
            summary += ". Shall I save it?"
            return handler_input.response_builder.speak(summary).ask("Do you want me to save it?")\
                .add_directive(ConfirmIntentDirective()).response

        if conf is False:
            return handler_input.response_builder.speak("Okay, not saved.").response

        payload = {"type": "breast", "side": side, "duration_min": duration_min, "notes": notes, "ts": None}
        try:
            _http("POST", "/log/feedevent", payload)
            lines = ["Saved breast feed", f"Side: {side}"]
            if duration_min is not None: lines.append(f"Duration: {duration_min} min")
            if notes: lines.append(f"Notes: {notes}")
            handler_input.response_builder.set_card(SimpleCard(title="Baby Log", content="\n".join(lines)))
            return handler_input.response_builder.speak("Saved your breast feed.").response
        except Exception:
            return handler_input.response_builder.speak("Sorry, I couldn't reach the baby log API.").response

class LogNappyIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("LogNappyIntent")(handler_input)
    def handle(self, handler_input):
        raw = get_slot_value(handler_input, "type")
        rid = get_slot_resolution_id(handler_input, "type")
        norm = normalise_nappy(raw, rid)
        notes = normalize_notes(get_slot_value(handler_input, "notes"))

        if not norm:
            prompt = "Got it — a nappy event. Was it a number one or a number two?" if mentions_both_types(raw) \
                     else "Was it a number one or a number two?"
            return handler_input.response_builder.speak(prompt).ask(prompt)\
                .add_directive(ElicitSlotDirective(slot_to_elicit="type")).response

        conf = intent_confirmed(handler_input)

        # Ask for notes before confirmation.
        if conf is None and notes is None:
            prompt = "Do you have any notes to add? You can say no."
            return handler_input.response_builder.speak(prompt).ask(prompt)\
                .add_directive(ElicitSlotDirective(slot_to_elicit="notes")).response

        if conf is None:
            label = say_nappy_type(norm)
            summary = f"You're about to log a nappy event: {label}."
            if notes:
                summary += f" Notes: {notes}."
            summary += " Shall I save it?"
            return handler_input.response_builder.speak(summary).ask("Do you want me to save it?")\
                .add_directive(ConfirmIntentDirective()).response

        if conf is False:
            return handler_input.response_builder.speak("Okay, not saved.").response

        payload = {"type": norm, "notes": notes, "ts": None}
        try:
            _http("POST", "/log/nappyevent", payload)
            lines = [f"Saved nappy: {say_nappy_type(norm)}"]
            if notes: lines.append(f"Notes: {notes}")
            handler_input.response_builder.set_card(SimpleCard(title="Baby Log", content="\n".join(lines)))
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

class LastNappyIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("LastNappyIntent")(handler_input)
    def handle(self, handler_input):
        raw = get_slot_value(handler_input, "type")
        rid = get_slot_resolution_id(handler_input, "type")
        norm = normalise_nappy(raw, rid)
        q = f"?type={norm}" if norm in ("pee", "poo") else ""
        try:
            last = _http("GET", f"/last/nappyevent{q}")
            human = last.get("human") or last.get("ts") or "recently"
            data = last.get("data", {})
            typ = data.get("type")
            typ_said = say_nappy_type(typ)
            speak = f"Last nappy was {typ_said} at {human}."
            return handler_input.response_builder.speak(speak).response
        except Exception:
            return handler_input.response_builder.speak("Sorry, I couldn't fetch the last nappy.").response

class StatsIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("StatsIntent")(handler_input)
    def handle(self, handler_input):
        period_id = resolve_period_id(handler_input)
        try:
            q = urllib.parse.quote(period_id)
            stats = _http("GET", f"/stats/feedevents?period={q}")
            count = stats.get("count", 0)
            spoken = stats.get("period") or period_id_to_spoken(period_id)
            return handler_input.response_builder.speak(f"{count} feeds {spoken}.").response
        except Exception:
            return handler_input.response_builder.speak("Sorry, I couldn't get stats right now.").response

class StatsNappyIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("StatsNappyIntent")(handler_input)
    def handle(self, handler_input):
        period_id = resolve_period_id(handler_input)
        raw = get_slot_value(handler_input, "type")
        rid = get_slot_resolution_id(handler_input, "type")
        norm = normalise_nappy(raw, rid)
        try:
            qp = f"period={urllib.parse.quote(period_id)}"
            if norm in ("pee", "poo"):
                qp += f"&type={norm}"
            stats = _http("GET", f"/stats/nappyevents?{qp}")
            count = stats.get("count", 0)
            spoken = stats.get("period") or period_id_to_spoken(period_id)
            noun = f"{say_nappy_type(norm)} nappies" if norm in ("pee", "poo") else "nappies"
            return handler_input.response_builder.speak(f"{count} {noun} {spoken}.").response
        except Exception:
            return handler_input.response_builder.speak("Sorry, I couldn't get nappy stats right now.").response

class StatsOverviewIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("StatsOverviewIntent")(handler_input)
    def handle(self, handler_input):
        period_id = resolve_period_id(handler_input)
        try:
            feed_stats = _http("GET", f"/stats/feedevents?period={urllib.parse.quote(period_id)}")
            nappy_stats = _http("GET", f"/stats/nappyevents?period={urllib.parse.quote(period_id)}")
            last_feed = _http("GET", "/last/feedevent")
            last_nappy = _http("GET", "/last/nappyevent")

            f_cnt = feed_stats.get("count", 0)
            n_cnt = nappy_stats.get("count", 0)

            lf_h = last_feed.get("human") or last_feed.get("ts") or "recently"
            ln_h = last_nappy.get("human") or last_nappy.get("ts") or "recently"
            ln_typ = say_nappy_type(last_nappy.get("data", {}).get("type"))

            period_spoken = feed_stats.get("period") or period_id_to_spoken(period_id)
            summary = (
                f"{f_cnt} feeds and {n_cnt} nappies {period_spoken}. "
                f"Last feed was at {lf_h}. Last nappy was {ln_typ} at {ln_h}."
            )
            return handler_input.response_builder.speak(summary).response
        except Exception:
            return handler_input.response_builder.speak("Sorry, I couldn't get the overview right now.").response

class DeleteLastFeedIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("DeleteLastFeedIntent")(handler_input)
    def handle(self, handler_input):
        conf = intent_confirmed(handler_input)
        if conf is None:
            speak = "You're about to delete the last feed. Shall I do that?"
            return handler_input.response_builder.speak(speak).ask("Do you want me to delete it?")\
                .add_directive(ConfirmIntentDirective()).response
        if conf is False:
            return handler_input.response_builder.speak("Okay, I won't delete it.").response
        try:
            _http("DELETE", "/last/feedevent")
            handler_input.response_builder.set_card(SimpleCard(title="Baby Log", content="Deleted last feed"))
            return handler_input.response_builder.speak("Deleted the last feed.").response
        except Exception:
            return handler_input.response_builder.speak("Sorry, I couldn't delete the last feed.").response

class DeleteLastNappyIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("DeleteLastNappyIntent")(handler_input)
    def handle(self, handler_input):
        raw = get_slot_value(handler_input, "type")
        rid = get_slot_resolution_id(handler_input, "type")
        norm = normalise_nappy(raw, rid)

        type_clause = f" {say_nappy_type(norm)}" if norm in ("pee", "poo") else ""
        conf = intent_confirmed(handler_input)
        if conf is None:
            speak = f"You're about to delete the last{type_clause} nappy. Shall I do that?"
            return handler_input.response_builder.speak(speak).ask("Do you want me to delete it?")\
                .add_directive(ConfirmIntentDirective()).response
        if conf is False:
            return handler_input.response_builder.speak("Okay, I won't delete it.").response

        q = f"?type={norm}" if norm in ("pee", "poo") else ""
        try:
            _http("DELETE", f"/last/nappyevent{q}")
            msg = f"Deleted last{type_clause} nappy".strip()
            handler_input.response_builder.set_card(SimpleCard(title="Baby Log", content=msg))
            return handler_input.response_builder.speak("Deleted the last nappy.").response
        except Exception:
            return handler_input.response_builder.speak("Sorry, I couldn't delete the last nappy.").response

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
    LastNappyIntentHandler(),
    StatsIntentHandler(),
    StatsNappyIntentHandler(),
    StatsOverviewIntentHandler(),
    DeleteLastFeedIntentHandler(),
    DeleteLastNappyIntentHandler(),
):
    sb.add_request_handler(h)

lambda_handler = sb.lambda_handler()
