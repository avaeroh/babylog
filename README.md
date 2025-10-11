# BabyLog

BabyLog is a self-hosted service for **logging baby activities** via a secure, versioned REST API — and controlling it hands-free with **Alexa**.  
The API stores events (e.g. `feeding`, `nappy`) in a single, flexible model with optional `notes`, `tags`, and `metadata` so you can adapt over time without breaking clients.

It also ships with **Adminer** (DB admin) and **Metabase** (dashboards) for quick inspection and analysis.

---

## What’s included

- **babylog-api** — FastAPI service, PostgreSQL-backed  
- **alexa-integration** — Alexa Skill handler (AWS Lambda) + interaction model + unit tests  
- **Adminer** — lightweight UI to query your DB  
- **Metabase** — build charts and dashboards over your data  
- **Makefile** — one-liners for build, test, packaging, and safe DB reset  
- **Docker Compose** — spins up everything locally or on a server  

---

## Quickstart

*(content unchanged up to Alexa section)*

---

## Alexa Integration

Hands-free logging and queries with the included **Lambda** handler and **interaction model**.

### Talking to Alexa — example interactions

> The model uses **one unified intent** for logging (`LogEventIntent`) with slot elicitation:
> - Alexa will **ask for the event type** (“feeding or nappy?”) if you don’t include it.
> - Alexa may **offer to add notes** after confirming the type.

**Start & Help**
- You: “**open baby log**”  
  Alexa: “Welcome to Baby Log. What would you like to do?”
- You: “**help**”  
  Alexa: “You can say: log a feeding, add a nappy, ask ‘latest feeding’, or ‘how many nappies last seven days’.”

**Log a feeding (no details given)**
- You: “**log an event**”  
  Alexa: “What type of event would you like to log — feeding or nappy?”  
  You: “**feeding**”  
  Alexa: “Any notes to add?”  
  You: “**120 ml bottle**” *(or say “no”)*  
  Alexa: “Saved your feeding.” *(your Lambda hits `POST /v1/event/feeding` with notes if provided)*

**Log a nappy with a quick note**
- You: “**log a nappy**”  
  Alexa: “Any notes to add?”  
  You: “**leaky**”  
  Alexa: “Saved your nappy.”

**Ask for the latest of a type**
- You: “**when was the last feeding**”  
  Alexa: “Last feeding was 2 hours 15 minutes ago.” *(calls `GET /v1/event/feeding/last`)*

**Delete last of a type (Alexa confirms)**
- You: “**delete last nappy**”  
  Alexa: “You’re about to delete the last nappy. Shall I do that?”  
  You: “**yes**”  
  Alexa: “Deleted the last nappy.” *(calls `DELETE /v1/event/nappy/last`)*

**Stats**
- You: “**how many nappies last seven days**”  
  Alexa: “12 nappies in the last seven days.” *(calls `GET /v1/stats/events?period=7d&type=nappy`)*

> **Tip:** You can also be direct: “**log a feeding**”, “**add a nappy**”, “**how many feedings today**”.

---

### Understanding the “notes” slot warning

When you build the Alexa model, you may see this warning:

> **The slot "notes" in intent "LogEventIntent" is not referenced in any slot or intent sample.**

This is **expected** and harmless. It happens because:
- `notes` uses the special `AMAZON.SearchQuery` type, meant for free-form dictation.
- Amazon doesn’t allow phrase slots (`SearchQuery`) to appear in the same utterance as other slots.
- Therefore, you can’t include `{notes}` in any sample alongside `{event_type}`, and Alexa flags it as “unreferenced.”

Your skill will still build and work correctly — the slot is filled later when your Lambda elicits it (“Any notes to add?”).

If you want to silence the warning, add a “notes-only” utterance, e.g.:
```json
"samples": ["note {notes}", "notes {notes}"]
```
This references the slot without violating Alexa’s rules.

---

## Adminer & Metabase
*(rest of README unchanged)*
