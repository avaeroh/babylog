# BabyLog

BabyLog is a self-hosted service for **logging and accessing baby activities** — including feeds and nappy events (pee/poo) — via a secure REST API.  
It is designed to be called by external services like Alexa, Home Assistant, or custom UIs, so you can log and retrieve baby care information hands-free or from a dashboard.

## Why Adminer and Metabase?

- **Adminer** is included for quick, direct inspection of the PostgreSQL database (useful for debugging and verifying records).
- **Metabase** is included to build dashboards and charts over your data. Metabase must be configured manually the first time (point it at your BabyLog database, set field types, etc.), after which it will let you visualize trends like number of feeds per day or time between nappy events.

---

## Getting Started

### 1. Prerequisites
- Docker and Docker Compose installed
- A `.env` file at the repo root with your Postgres and API secrets, for example:

```env
DB_USER=baby
DB_PASSWORD=change_me
DB_NAME=babylog
API_KEY=change_me_api_key
```

### 2. Build and start the stack
```bash
make build
make up
```
This starts:
- **db**: PostgreSQL with your BabyLog schema  
- **api**: FastAPI server at `<babylog-api-host>:5080`  
- **adminer**: Adminer at `<babylog-api-host>:5081`  
- **metabase**: Metabase at `<babylog-api-host>:5000`

### 3. Reverse proxy (Nginx Proxy Manager)
If you expose the API publicly, configure **Nginx Proxy Manager** to route `babylog-api.<your-domain>.com` → the `babylog-api` container:

- **Domain Names:** `babylog-api.<your-domain>.com`
- **Scheme:** `http`
- **Forward Hostname / IP:** `babylog-api` (service name on the shared Docker network)
- **Forward Port:** `5080`
- **Block Common Exploits:** ✓, **Websockets:** ✓
- **SSL:** Request Let’s Encrypt cert → **Force SSL** ✓, **HTTP/2** ✓, **HSTS** ✓

> Advanced tab is optional. CORS is not needed for Alexa. Keep auth at the API level using your `API_KEY`.

### 4. Verify API health
```bash
curl http://<babylog-api-host>:5080/health
```

### 5. Run tests
- **API tests:**
  ```bash
  make test
  ```
- **Alexa unit tests (no network):**
  ```bash
  make lambda-test
  # or a clean rebuild:
  make lambda-test-clean
  ```

### 6. Export the API spec
To generate an OpenAPI spec file on your host:
```bash
make openapi   # or: make openapi-spec (depending on your Makefile target)
```

---

## Alexa Integration

BabyLog ships with an Alexa Skill implementation so you can log and query events hands‑free.

### What’s included
- **Interaction model:** `alexa-integration/models/interaction-model.json`
- **Lambda handler:** `alexa-integration/lambda_function.py`
- **Sample events:** `alexa-integration/events/`
- **Unit tests:** `alexa-integration/tests/*`

### One‑time setup

1) **Create the Lambda (EU‑West / Ireland).**  
   - Runtime: **Python 3.11**  
   - Handler: **`lambda_function.lambda_handler`**  
   - Upload a deployment ZIP that contains `lambda_function.py` and Python deps at the ZIP root (or use the AWS code editor to paste the file).

2) **Configure Lambda environment variables.**
   - `BABYLOG_BASE_URL` — e.g. `https://babylog-api.<your-domain>.com`
   - `API_KEY` — your API key
   - *(optional)* `HTTP_TIMEOUT_S` (default `6`), `HTTP_RETRIES` (default `1`)
   - *(optional admin)* `BABYLOG_CLEAR_PATH` (default `/admin/clear`) and `BABYLOG_CLEAR_METHOD` (default `POST`) if you expose a “clear all data” endpoint

3) **Create the Alexa Skill (EU marketplace) and link Lambda.**
   - In the **Alexa Developer Console → Build → Interaction Model**, paste the JSON from `alexa-integration/models/interaction-model.json` and **Build Model**.
   - In **Endpoint**, choose **AWS Lambda ARN** and paste your Lambda’s **EU (Ireland)** ARN in the *Default Region* field.
   - Save.

4) **Test.**
   - Open the **Test** tab for the skill and set test mode to **Development**.  
   - Try: “**open baby log**”.

> **Note on packaging:** If you prefer zipping locally, ensure your ZIP root contains `lambda_function.py` and the pure‑Python ASK SDK (`ask_sdk_core`, `ask_sdk_runtime`, `ask_sdk_model`) — no compiled `.so` files. The handler in this repo avoids heavy deps.

### How to use (voice examples)

**Start**
- “**open baby log**” → *Alexa:* **Welcome to Baby Log.** (reprompt: *Say help to hear what I can do.*)
- “**help**” → tips + examples

**Log a nappy**
- “**add a poo**” / “**add a number two**” / “**log a pee nappy**”  
  → Alexa summarises and asks **“Do you want me to save it?”** → say **“Yes”** to commit.
- Optional notes: “**add a poo with leaky**”

**Log a feed**
- “**log a bottle 120 millilitres**”
- “**log a breast feed left for ten minutes**”  
  If side or duration is missing, Alexa will ask: “**Left or right side?**” etc., then confirm before saving.
- Generic: “**log a feed**” → Alexa asks **“Bottle or breast?”**

**Latest entries**
- “**when was the last feed**”
- “**when was the last poo**” / “**last pee nappy**”

**Statistics**
- “**how many feeds today**”
- “**how many nappies in the last seven days**”
- “**how many poos yesterday**”

**Delete (undo) the last item**
- “**delete the last feed**”
- “**delete the last nappy**” / “**delete the last poo nappy**”

**Clear all data (dangerous)**
- “**clear all data**” → Alexa: “**This will remove all data. Are you sure? Say Yes to confirm.**” → say **“Yes”** to proceed.
  - Requires that your API exposes an admin clear route (see environment variables above). If not configured, Alexa will say it isn’t supported.

### What Alexa does behind the scenes

- **Nappy logging** → `POST /log/nappyevent` with `{"type":"pee"|"poo","notes":..., "ts":null}`  
- **Feed logging** → `POST /log/feedevent` (`bottle` uses `volume_ml`, `breast` uses `side` and/or `duration_min`)  
- **Latest** → `GET /last/feedevent` or `GET /last/nappyevent[?type=pee|poo]`  
- **Stats** → `GET /stats/feedevents?period=...` or `GET /stats/nappyevents?period=...&type=...`  
- **Delete** → `DELETE /last/feedevent` or `DELETE /last/nappyevent[?type=...]`  
- **Clear all** → calls `{BABYLOG_BASE_URL}{BABYLOG_CLEAR_PATH}` with `x-api-key` (if configured)

All writes send `ts: null` so **the server timestamps in UTC “now”**.

### Tips for better recognition

- The model understands synonyms for nappies (e.g., **“number one”/“number two”**, **“poop/poo”**, **“wee/pee”**).  
- If Alexa asks for missing details (e.g., breast **side**), just answer the question — you don’t need to start over.
- If Alexa is unsure, she’ll say she didn’t catch that and suggest saying **help**.

### Troubleshooting

- **“The requested skill did not provide a valid response”**  
  Check CloudWatch logs for the Lambda. Common issues: wrong `BABYLOG_BASE_URL`, unreachable host, or missing `API_KEY`.
- **Wrong region / no response**  
  Make sure your skill’s **Endpoint → Default Region** uses the **EU (Ireland)** Lambda ARN.
- **Skill asks for info I already gave**  
  Try rephrasing using the model’s phrasings above. If it persists, rebuild the model in the Developer Console and try again.
- **Clear all data says unsupported**  
  Add the admin endpoint to your API and set `BABYLOG_CLEAR_PATH` / `BABYLOG_CLEAR_METHOD` in Lambda env vars.

---

## Makefile Overview

Convenience commands:
- `make build` — build the API and test images  
- `make up` — start API + DB services  
- `make down` — stop all services  
- `make logs` — follow API logs  
- `make test` — run the API test suite  
- `make lambda-test` — run Alexa unit tests (offline)  
- `make lambda-test-clean` — rebuild test image then run Alexa unit tests  
- `make wipe-data` — truncate activity tables (with confirmation prompt)  
- `make openapi` — export the OpenAPI spec (`openapi.json`)  
  - *or*: `make openapi-spec` if that’s your defined target

---

## API Overview

All modifying routes require an API key. The Lambda sends the key as **`x-api-key`**.

- `GET /health` — Health check (no key required)
- `POST /log/feedevent` — Log a feed event (body: `FeedEventIn`)
  - Bottle: `{"type":"bottle","volume_ml":120,"notes":"…","ts":null}`
  - Breast: `{"type":"breast","side":"left","duration_min":15,"notes":"…","ts":null}`
- `POST /log/nappyevent` — Log a nappy event (body: `NappyEventIn`)
  - `{"type":"pee","notes":"…","ts":null}` or `{"type":"poo","notes":"…","ts":null}`
- `GET /last/feedevent` — Latest feed (returns `LastOut` with `human` and `data`)
- `GET /last/nappyevent[?type=pee|poo]` — Latest nappy
- `DELETE /last/feedevent` — Delete last feed
- `DELETE /last/nappyevent[?type=...]` — Delete last nappy (optionally filtered by type)
- `GET /stats/feedevents?period=...` — Feed stats
- `GET /stats/nappyevents?period=...&type=...` — Nappy stats

> The server normalises timestamps to **UTC**; sending `ts: null` means “use server time now”.

### Example Usage
```bash
# Log a 4oz bottle (Lambda converts oz → ml in normal voice use; shown here as ml)
curl -X POST https://babylog-api.<your-domain>.com/log/feedevent \
  -H "x-api-key: ${API_KEY}" -H "Content-Type: application/json" \
  -d '{"type":"bottle","volume_ml":118,"notes":"expressed","ts":null}'

# Log a left-side breast feed for 15 minutes
curl -X POST https://babylog-api.<your-domain>.com/log/feedevent \
  -H "x-api-key: ${API_KEY}" -H "Content-Type: application/json" \
  -d '{"type":"breast","side":"left","duration_min":15,"ts":null}'

# Log a poo nappy with note
curl -X POST https://babylog-api.<your-domain>.com/log/nappyevent \
  -H "x-api-key: ${API_KEY}" -H "Content-Type: application/json" \
  -d '{"type":"poo","notes":"messy","ts":null}'

# Latest feed
curl -H "x-api-key: ${API_KEY}" https://babylog-api.<your-domain>.com/last/feedevent

# Stats (today)
curl -H "x-api-key: ${API_KEY}" "https://babylog-api.<your-domain>.com/stats/feedevents?period=today"
```

---

## Repository Layout

```
├── babylog-api
│   ├── app
│   │   ├── adapters      # DB engine/session and repositories
│   │   ├── api           # FastAPI routes + deps (API key check, DB session)
│   │   ├── domain        # Pydantic models (FeedEventIn, NappyEventIn, LastOut, StatsOut)
│   │   └── services      # Business logic (stats, human-readable helpers)
│   ├── scripts           # Utility scripts (e.g., export_openapi.py)
│   └── tests             # Pytest API tests
├── alexa-integration
│   ├── lambda_function.py
│   ├── models/interaction-model.json
│   ├── events/           # Sample Alexa events for console testing
│   ├── tests/            # Unit tests for Lambda (offline)
│   └── Dockerfile.tests
└── specs
    └── openapi.json      # Exported API spec (and lambda.zip when you package the handler)
```

---

## Security Notes

- **API key required** for all modifying routes. Keep it secret and rotate periodically.
- Prefer exposing **only the API** publicly. If you expose Home Assistant, protect it further (e.g., NPM Access Lists, VPN, or Cloudflare Access).
- Keep Nginx timeouts modest and payload sizes small (`client_max_body_size` ~2MB is fine for this API).

---

## Troubleshooting

- **Alexa says it saved, but nothing appears in DB** → Check NPM access logs for `babylog-api.<your-domain>.com` and API logs. Likely an auth or proxy routing issue.
- **Lambda times out** → Verify `BABYLOG_BASE_URL`, DNS, and NPM SSL. Increase Lambda timeout to ~8–10s if needed.
- **Unit tests can’t import `lambda_function`** → ensure `lambda-tests` service sets `PYTHONPATH=/app` and `alexa-integration/lambda_function.py` exists.
- **Metabase can’t connect** → DB host should be `db`, port `5432` (inside Docker network).
