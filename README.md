# BabyLog

BabyLog is a self‑hosted service for **logging baby activities** via a secure, versioned REST API — and controlling it hands‑free with **Alexa**.  
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

### 1) Prerequisites
- Docker + Docker Compose
- A `.env` file at the repo root with your secrets:

```env
# --- Postgres ---
DB_USER=baby
DB_PASSWORD=change_me
DB_NAME=babylog

# --- API ---
API_KEY=change_me_api_key
DATABASE_URL=postgresql://baby:change_me@db:5432/babylog

# Lambda (optional)
BABYLOG_BASE_URL=https://babylog-api.<your-domain>.com
HTTP_RETRIES=3
HTTP_TIMEOUT_S=6

# Optional: enable dangerous admin reset route in API (for testing only)
RESET_ENABLED=0
```

> **Note:** In tests, the API uses an in‑memory SQLite (via `TESTING=1`). For dev/prod, it uses Postgres from `DATABASE_URL`.

### 2) Build & run
```bash
make build
make up
```
This starts:
- **db** (PostgreSQL)
- **api** (FastAPI on `:5080`)
- **adminer** (web UI on `:5081`)
- **metabase** (web UI on `:5000`)

Verify:
```bash
curl http://localhost:5080/v1/health
# -> {"status":"ok"}
```

### 3) Run tests
- **API tests**
  ```bash
  make test
  # or a clean rebuild of images
  make test-clean
  ```
- **Alexa unit tests (offline)**
  ```bash
  make lambda-test
  # or clean
  make lambda-test-clean
  ```

### 4) Export OpenAPI
```bash
make openapi
# writes specs/openapi.json
```

### 5) Wipe database ⚠️
Use this when you want to clear **all data** but keep the schema (e.g., reset dev/test DB).  
It truncates every table in the `public` schema and resets identity sequences.

```bash
make wipe-data
```
You’ll be prompted:
```
⚠️  This will DELETE ALL DATA in database 'babylog'. Type YES to continue:
```
Confirm by typing **YES** to proceed.

**Example output:**
```
Truncating all tables in babylog...
✅  All tables truncated successfully.
```
To skip the prompt, run non-interactively:
```bash
yes YES | make wipe-data
```
**Warning:** This action is irreversible. It does **not** affect schema, migrations, or user accounts, but removes all event data.

### 6) Reset database (safe sequence)
If you want a clean slate without fully tearing down Postgres, add this to your Makefile:

```makefile
reset-db:
	-$(COMPOSE) stop api adminer metabase
	$(COMPOSE) up -d db
	$(COMPOSE) exec -T db sh -lc 'until pg_isready -U "$$DB_USER" -d "$$DB_NAME" >/dev/null 2>&1; do sleep 1; done'
	@$(MAKE) wipe-data
	$(COMPOSE) up -d api adminer metabase
	@echo "✅ Database reset and containers restarted."
```

Then run:
```bash
make reset-db
```

This:
1. Stops API/UI containers  
2. Ensures DB is running and healthy  
3. Truncates all tables via `make wipe-data`  
4. Brings API/UI back up  

If you later add more services (e.g. `worker`), just include them in the `stop` and `up -d` lines.

---

## API Overview (v1)

*(unchanged content above this section omitted for brevity)*

---

## Alexa Integration

Hands-free logging and queries with the included **Lambda** handler and **interaction model**.

### Files
- `alexa-integration/lambda_function.py` — the handler (pure Python, minimal deps)
- `alexa-integration/models/interaction-model.json` — the custom model
- `alexa-integration/tests/` — unit tests (offline)
- `alexa-integration/events/` — optional sample events

### Lambda environment variables
- `BABYLOG_BASE_URL` — e.g. `https://babylog-api.example.com`
- `API_KEY` — same key the API expects
- `HTTP_TIMEOUT_S` (default `6`)
- `HTTP_RETRIES` (default `1`)

---

## Using Alexa (example interactions)

**Start**
- “**open baby log**”  
- “**help**” → overview + examples

**Log an event (unified)**
- “**log a feed**” → Alexa: *“Do you want to add any notes?”* → you: “no” → Alexa confirms & saves.  
- “**log a feeding with 120 ml bottle**” *(Alexa will capture as notes; structure handled server-side)*  
- “**log a nappy**” → Alexa: *“Do you want to add any notes?”* → you: “messy diaper” → Alexa confirms & saves.  
- “**add a nappy with leaky**” → Alexa confirms & saves.

> Tip: “**feed**” and “**feeding**” both work (the model maps “feed” → `feeding`).

**Latest event**
- “**when was the last feed**”  
- “**latest nappy**”

**Delete (undo)**
- “**delete last feed**” → Alexa asks to confirm → say “yes”  
- “**delete last nappy**” → confirm → saved

**Stats**
- “**how many feeds today**”  
- “**how many nappies in the last seven days**”  
- “**stats last week**” *(counts all events)*  
- “**feeding stats today**” *(type-filtered)*

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

- **Adminer** at `http://localhost:5081` — quick look into tables and rows.
- **Metabase** at `http://localhost:5000` — connect it to the `db` service (`host: db`, `port: 5432`) and build dashboards.
  - Save a question like “Events per day” or filter by `{type}`.

---

## Reverse Proxy (optional)

If you expose the API, you can use **Nginx Proxy Manager**:
- Domain: `babylog-api.<your-domain>` → Forward Host: `babylog-api` (container name), Port: `5080`
- Enable SSL (Let’s Encrypt), force HTTPS, enable HTTP/2 + HSTS
- Keep server auth at the API level with your `API_KEY`

---

## Makefile Cheatsheet

- `make build` / `make build-clean` — build images
- `make up` / `make down` — start/stop the stack
- `make logs` — tail API logs
- `make test` / `make test-clean` — API tests
- `make lambda-test` / `make lambda-test-clean` — Alexa tests (offline)
- `make wipe-data` — Truncate **all** tables in the DB (schema preserved). Prompts for YES.
- `make reset-db` — Safely reset DB **without** taking down the DB container:
  - Stops API/UI, ensures DB is healthy, runs `wipe-data`, then brings API/UI back up.
- `make openapi` — export `specs/openapi.json`

---

## Repository Layout

```
├── babylog-api
│   ├── app
│   │   ├── adapters/         # DB engine, session, SQLAlchemy models & repos
│   │   ├── api/              # FastAPI routes (v1), deps (auth, DB session)
│   │   ├── domain/           # Pydantic schemas
│   │   └── services/         # Stats & helpers
│   ├── scripts/              # openapi export, truncate_all.sql, etc.
│   └── tests/                # pytest suite for API
├── alexa-integration
│   ├── lambda_function.py
│   ├── models/interaction-model.json
│   ├── events/
│   └── tests/
└── specs/
    └── openapi.json
```

---

## Security Notes

- Keep **API_KEY** secret; rotate periodically.
- Prefer exposing only the API; keep Adminer/Metabase behind a VPN or private network.
- The reset endpoint is feature-flagged. Leave `RESET_ENABLED=0` in prod.

---

## Troubleshooting

- **401 Unauthorized** — Missing or wrong `x-api-key`.
- **Alexa doesn’t save / persistent model warning** — Rebuild the skill model; verify `notes` samples exist; check Lambda CloudWatch logs.
- **OpenAPI export fails** — Ensure the API image builds and `app.main:app` loads without startup errors.
- **Tests hang** — On ARM, ensure Docker images are built for ARM64 (see Makefile’s `DOCKER_DEFAULT_PLATFORM`).
