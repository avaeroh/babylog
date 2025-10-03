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

### What’s included
- **Interaction model:** `alexa-integration/models/interaction-model.json`
- **Lambda handler:** `alexa-integration/lambda_function.py`
- **Unit tests:** `alexa-integration/tests/*` (+ sample events in `alexa-integration/events/`)

### Behaviour & dialogs
- **Nappy events:** user can say **“pee” / “number one”** or **“poo” / “number two”**. Notes are prompted but optional. **Timestamps are set server-side** (API computes UTC now).
- **Feeding events:**
  - **Type is required** and implicit in intent (`LogBottleFeedIntent` vs `LogBreastFeedIntent`).
  - If **breast**, Alexa **elicits side** (**left/right**) if not said.
  - **Notes** are prompted but optional.
  - **Quantities are optional**:
    - Bottle: supports **ml** and **ounces** (automatic oz→ml conversion).
    - Breast: supports **minutes** and **hours** (automatic hours→minutes conversion).
- **Playback/confirmation:** before writing, Alexa **confirms** and only POSTs after a “Yes”.

### Deploying the Lambda (manual upload)
1) **Zip the handler:**
   ```bash
   cd alexa-integration && zip -r ../specs/lambda.zip lambda_function.py
   ```
2) In AWS Lambda (Python 3.11), set **Handler** to `lambda_function.lambda_handler` and **upload** `specs/lambda.zip`.
3) Set environment variables:
   - `BABYLOG_BASE_URL = https://babylog-api.<your-domain>.com`
   - `API_KEY = <your api key>`
   - (optional) `HTTP_TIMEOUT_S = 6`, `HTTP_RETRIES = 1`
4) In the **Alexa Developer Console**:
   - Paste the interaction model JSON and **Build** the model.
   - Set the skill **Endpoint** to your Lambda ARN.
5) Test in the Alexa simulator:
   - “open baby log”  
   - “log a bottle” → *Alexa confirms → say ‘yes’*  
   - “log a left side breast feed for fifteen minutes”  
   - “log a number two nappy with messy”  
   - “what was the last feed”

> You can also smoke-test the Lambda in-console by pasting one of the sample events from `alexa-integration/events`.

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

All modifying routes require an API key. The Lambda uses **`Authorization: Bearer <API_KEY>`**; you may also support `X-API-Key` if enabled in your FastAPI deps.

- `GET /health` — Health check (no key required)
- `POST /feeds` — Log a feed event (body: `FeedEventIn`)
  - `{"type":"bottle","volume_ml":120,"notes":"…","ts":null}`
  - `{"type":"breast","side":"left","duration_min":15,"notes":"…","ts":null}`
- `POST /nappies` — Log a nappy event (body: `NappyEventIn`)
  - `{"type":"pee","notes":"…","ts":null}` or `{"type":"poo","notes":"…","ts":null}`
- `GET /feeds/last` — Latest feed event (returns `LastOut` with `human` and `data`)
- `GET /stats?period=today|this%20week|last%2024%20hours` — Period stats (returns `StatsOut`)

> The server normalises timestamps to **UTC**; sending `ts: null` means “use server time now”.

### Example Usage
```bash
# Log a 4oz bottle (Lambda does oz→ml conversion; shown here as ml)
curl -X POST https://babylog-api.<your-domain>.com/feeds   -H "Authorization: Bearer ${API_KEY}" -H "Content-Type: application/json"   -d '{"type":"bottle","volume_ml":118,"notes":"expressed","ts":null}'

# Log a left-side breast feed for 15 minutes
curl -X POST https://babylog-api.<your-domain>.com/feeds   -H "Authorization: Bearer ${API_KEY}" -H "Content-Type: application/json"   -d '{"type":"breast","side":"left","duration_min":15,"ts":null}'

# Log a poo nappy with note
curl -X POST https://babylog-api.<your-domain>.com/nappies   -H "Authorization: Bearer ${API_KEY}" -H "Content-Type: application/json"   -d '{"type":"poo","notes":"messy","ts":null}'

# Latest feed
curl -H "Authorization: Bearer ${API_KEY}" https://babylog-api.<your-domain>.com/feeds/last

# Stats (today)
curl -H "Authorization: Bearer ${API_KEY}" "https://babylog-api.<your-domain>.com/stats?period=today"
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

---

Happy logging 👶🍼
