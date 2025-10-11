# alexa-integration/tests/conftest.py
import os
import types
import pytest

# Ensure envs exist at import time for lambda_function
os.environ.setdefault("BABYLOG_BASE_URL", "https://babylog-api.example.com")
os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("HTTP_TIMEOUT_S", "3")
os.environ.setdefault("HTTP_RETRIES", "0")

class DummyRB:
    """Minimal ResponseBuilder stub the handlers can call."""
    def __init__(self):
        self.speech = None
        self.reprompt = None
        self.directives = []
        self.card = None

    def speak(self, text):
        self.speech = text
        return self

    def ask(self, text):
        self.reprompt = text
        return self

    def add_directive(self, d):
        # Store a simplified dict so tests don't need ASK model imports
        self.directives.append({"type": getattr(d, "type", d.__class__.__name__)})
        return self

    def set_card(self, card):
        title = getattr(card, "title", "") or ""
        content = getattr(card, "content", "") or ""
        self.card = {"title": title, "content": content}
        return self

    @property
    def response(self):
        return {
            "speech": self.speech,
            "reprompt": self.reprompt,
            "directives": self.directives,
            "card": self.card,
        }

def make_hi(intent_name: str, slots: dict | None = None, confirmation_status: str = "NONE"):
    """
    Build a minimal object graph with:
      handler_input.request_envelope.request.intent.name
      handler_input.request_envelope.request.intent.confirmation_status
      handler_input.request_envelope.request.intent.slots[...].value
      handler_input.response_builder
    """
    intent_ns = types.SimpleNamespace(
        name=intent_name,
        confirmation_status=confirmation_status,
        slots={}
    )
    for k, v in (slots or {}).items():
        intent_ns.slots[k] = types.SimpleNamespace(name=k, value=v, confirmationStatus="NONE")

    req = types.SimpleNamespace(type="IntentRequest", intent=intent_ns)
    env = types.SimpleNamespace(request=req)
    return types.SimpleNamespace(request_envelope=env, response_builder=DummyRB())
