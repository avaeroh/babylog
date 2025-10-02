# lambda_function.py
import json, os, time, urllib.request, urllib.error, urllib.parse
from typing import Any, Dict, Optional, Tuple

from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestHandler
from ask_sdk_core.utils import is_request_type, is_intent_name
from ask_sdk_model import Response

BASE = os.environ["BABYLOG_BASE_URL"].rstrip("/")
API_KEY = os.environ["API_KEY"]
TIMEOUT_S = float(os.environ.get("HTTP_TIMEOUT_S", "6"))
RETRY = int(os.environ.get("HTTP_RETRIES", "1"))

OZ_TO_ML = 29.5735

# ---------- HTTP ----------
def _http(method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = f"{BASE}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
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

    # Dict-shaped slot (as in our tests / some simulator payloads)
    if isinstance(slot, dict):
        return slot.get("value")

    # ASK SDK object; also handle odd cases safely
    val = getattr(slot, "value", None)
    return val


def parse_volume(volume_value: Optional[str], volume_unit: Optional[str]) -> Optional[int]:
    """Return millilitres as int, or None if not provided."""
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
    minutes = int(round(v * 60)) if unit_id in ("h", "hour", "hours", "hr", "hrs") else int(round(v))
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
    def can_handle(self, hi): return is_request_type("LaunchRequest")(hi)
    def handle(self, hi):
        speak = "Welcome to Baby Log. You can say, log a bottle, log a breast feed, or, log a pee or poo nappy."
        return hi.response_builder.speak(speak).ask("What would you like to do?").response

class LogBottleFeedIntentHandler(AbstractRequestHandler):
    def can_handle(self, hi): return is_intent_name("LogBottleFeedIntent")(hi)
    def handle(self, hi):
        # If Alexa hasn't asked for confirmation yet, the Dialog Model will do it.
        conf = intent_confirmed(hi)
        notes = get_slot(hi, "notes")
        volume_value = get_slot(hi, "volume_value")
        volume_unit = get_slot(hi, "volume_unit")
        volume_ml = parse_volume(volume_value, volume_unit)

        if conf is None:
            # Let Alexa ask the confirmation using the dialog model prompt.
            summary = summarise_bottle(volume_ml, notes)
            return hi.response_builder.speak(f"{summary}. Do you want me to save it?").ask("Shall I save it?").add_directive(
                {"type":"Dialog.ConfirmIntent"}
            ).response

        if conf is False:
            return hi.response_builder.speak("Okay, I won't save it.").response

        # CONFIRMED → POST
        payload = {"type": "bottle", "volume_ml": volume_ml, "notes": notes, "ts": None}
        try:
            _http("POST", "/feeds", payload)
            speak = "Saved your bottle feed."
            return hi.response_builder.speak(speak).response
        except Exception:
            return hi.response_builder.speak("Sorry, I couldn't reach the baby log API.").response

class LogBreastFeedIntentHandler(AbstractRequestHandler):
    def can_handle(self, hi): return is_intent_name("LogBreastFeedIntent")(hi)
    def handle(self, hi):
        side = (get_slot(hi, "side") or "").lower() or None
        duration_min = parse_duration(get_slot(hi, "duration_value"), get_slot(hi, "duration_unit"))
        notes = get_slot(hi, "notes")

        # Ensure side is present (dialog model should elicit; re-check defensively)
        if not side or side not in ("left", "right"):
            prompt = "Left or right side?"
            return hi.response_builder.speak(prompt).ask(prompt).add_directive(
                {"type":"Dialog.ElicitSlot","slotToElicit":"side"}
            ).response

        conf = intent_confirmed(hi)
        if conf is None:
            summary = summarise_breast(side, duration_min, notes)
            return hi.response_builder.speak(f"{summary}. Do you want me to save it?").ask("Shall I save it?").add_directive(
                {"type":"Dialog.ConfirmIntent"}
            ).response

        if conf is False:
            return hi.response_builder.speak("Okay, not saved.").response

        payload = {"type": "breast", "side": side, "duration_min": duration_min, "notes": notes, "ts": None}
        try:
            _http("POST", "/feeds", payload)
            return hi.response_builder.speak("Saved your breast feed.").response
        except Exception:
            return hi.response_builder.speak("Sorry, I couldn't reach the baby log API.").response

class LogNappyIntentHandler(AbstractRequestHandler):
    def can_handle(self, hi): return is_intent_name("LogNappyIntent")(hi)
    def handle(self, hi):
        nappy_type = (get_slot(hi, "type") or "").lower()
        notes = get_slot(hi, "notes")
        if not nappy_type:
            return hi.response_builder.speak("Was it pee, or poo?").ask("Pee or poo?").add_directive(
                {"type":"Dialog.ElicitSlot","slotToElicit":"type"}
            ).response

        # Normalise “number one/two” → pee/poo
        if "two" in nappy_type or "2" in nappy_type or "poo" in nappy_type or "poop" in nappy_type:
            norm = "poo"
        else:
            norm = "pee"

        conf = intent_confirmed(hi)
        if conf is None:
            summary = summarise_nappy(norm, notes)
            return hi.response_builder.speak(f"{summary}. Shall I save it?").ask("Do you want me to save it?").add_directive(
                {"type":"Dialog.ConfirmIntent"}
            ).response

        if conf is False:
            return hi.response_builder.speak("Okay, not saved.").response

        payload = {"type": norm, "notes": notes, "ts": None}
        try:
            _http("POST", "/nappies", payload)
            return hi.response_builder.speak("Saved your nappy event.").response
        except Exception:
            return hi.response_builder.speak("Sorry, I couldn't reach the baby log API.").response

class LastFeedIntentHandler(AbstractRequestHandler):
    def can_handle(self, hi): return is_intent_name("LastFeedIntent")(hi)
    def handle(self, hi):
        try:
            last = _http("GET", "/feeds/last")
            human = last.get("human") or last.get("ts") or "recently"
            data = last.get("data", {})
            typ = data.get("type", "feed")
            extra = ""
            if typ == "bottle" and "volume_ml" in data:
                extra = f", {data['volume_ml']} millilitres"
            if typ == "breast" and data.get("side"):
                extra = f", {data['side']} side"
            speak = f"Last feed was {typ}{extra} at {human}."
            return hi.response_builder.speak(speak).response
        except Exception:
            return hi.response_builder.speak("Sorry, I couldn't fetch the last feed.").response

class StatsIntentHandler(AbstractRequestHandler):
    def can_handle(self, hi): return is_intent_name("StatsIntent")(hi)
    def handle(self, hi):
        period = get_slot(hi, "period") or "today"
        try:
            stats = _http("GET", f"/stats?period={urllib.parse.quote(period)}")
            count = stats.get("count", 0)
            per = stats.get("period", period)
            return hi.response_builder.speak(f"{count} events {per}.").response
        except Exception:
            return hi.response_builder.speak("Sorry, I couldn't get stats right now.").response

sb = SkillBuilder()
for h in [LaunchHandler(), LogBottleFeedIntentHandler(), LogBreastFeedIntentHandler(),
          LogNappyIntentHandler(), LastFeedIntentHandler(), StatsIntentHandler()]:
    sb.add_request_handler(h)

lambda_handler = sb.lambda_handler()
