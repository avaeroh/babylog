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
- **Makefile** — one-liners for build, test, and packaging
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

# Lambda
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
✅ All tables truncated.
```
To skip the prompt, run non-interactively:
```bash
yes YES | make wipe-data
```
**Warning:** This action is irreversible. It does **not** affect schema, migrations, or user accounts, but removes all event data.

---

## API Overview (v1)
... (remaining README unchanged) ...
