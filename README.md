# BabyLog

A self-hosted backend (FastAPI + PostgreSQL) for logging baby activities — feeds and nappy events — with a simple, secure HTTP API, plus Adminer and Metabase for viewing and analyzing data. Designed to run on a Raspberry Pi (Docker), and to be integrated later with Alexa/Home Assistant flows (e.g., “baby log save …”, “baby log info …”).

---

## ✨ What this repo does

- **Logs baby activities**:
  - **Feeds** (breast/bottle, side, duration, volume, notes).
  - **Nappy events** (pee/poo with free-text description).
- **Retrieves info**:
  - Latest feed / latest nappy event (optionally filter by type).
  - Aggregated stats over a time window (e.g., last 24h / last 7d).
- **Allows corrections**:
  - Delete the latest feed.
  - Delete the latest nappy event (optionally just the latest `pee` or `poo`).
- **Exposes a clean API** with a simple header-based API key.
- **Provides a UI** to view and explore data:
  - **Adminer**: quick DB browser.
  - **Metabase**: friendly dashboards/charts.
- **Tested**: fast, hermetic unit tests (SQLite in-memory).

---

## 🧰 Tech overview

- **API**: FastAPI (Python 3.11)
- **DB**: PostgreSQL (production), SQLite (tests)
- **ORM**: SQLAlchemy 2.x
- **Auth**: static `x-api-key` header
- **Container orchestration**: Docker Compose
- **Visualisation**: Metabase
- **DB Admin**: Adminer

The API uses FastAPI’s **lifespan** startup to auto-create tables on boot (v1 bootstrap).

---

## 🚀 Step-by-step setup

### 1) Prerequisites
- Docker & Docker Compose
- Raspberry Pi or any Linux host
- Optional reverse proxy network for nginx:  
  ```bash
  docker network create proxy
  ```

### 2) Create `.env`
Create a `.env` at the repo root (same folder as `docker-compose.yml`):
```env
# Database
DB_USER=baby
DB_PASSWORD=change_me
DB_NAME=babylog

# API
API_KEY=CHANGE_ME_API_KEY
```

### 3) Start the stack
Using Makefile targets:
```bash
make build       # builds API + test images
make up          # runs API + DB (detached)
make logs        # follow API logs
```
Or with Compose directly:
```bash
docker-compose up -d db api adminer metabase
```

### 4) Health-check the API
```bash
curl -s http://localhost:5080/health
# -> {"status":"ok"}
```

### 5) Run tests
Fast (cached):
```bash
make test
```

### 6) Adminer & Metabase (local defaults)
- **Adminer**: <http://localhost:5081>  
  Use your Postgres credentials from `.env`.
- **Metabase**: <http://localhost:5000>  
  First-run wizard stores its app data in `/srv/babylog/metabase` (mapped volume).

> If you run behind nginx, ensure your API container is attached to the `proxy` network (already configured in `docker-compose.yml`).

---

## 📂 Repository layout

```
.
├─ babylog-api/
│  ├─ app/
│  │  ├─ api/
│  │  │  └─ routes.py        # FastAPI route handlers
│  │  ├─ adapters/
│  │  │  ├─ db.py            # engine/session setup (Postgres or SQLite for tests)
│  │  │  └─ repositories.py  # SQLAlchemy ORM models + repositories
│  │  ├─ domain/
│  │  │  ├─ models.py        # Pydantic schemas
│  │  │  └─ ports.py         # repository interfaces (protocols)
│  │  ├─ services/
│  │  │  └─ stats.py         # period parsing, human_delta, stats helpers
│  │  ├─ api/
│  │  │  └─ deps.py          # API-key auth, DB session dependency
│  │  └─ main.py             # FastAPI app (lifespan startup)
│  ├─ tests/                 # pytest unit tests
│  ├─ Dockerfile             # multi-stage build (prod + tests)
│  └─ requirements.txt
├─ docker-compose.yml        # services stack
├─ Makefile                  # convenience commands
└─ .env                      # environment variables (you create this)
```

---

## 🧩 Docker Compose services

### `db` (PostgreSQL)
- Stores all feed and nappy events.
- Credentials and DB name from `.env`.
- Health-checked via `pg_isready`.

### `api` (FastAPI)
- Exposes the BabyLog HTTP API on container port **5080** (reachable via the `proxy` network for nginx).
- On startup, initializes tables if they don’t exist.
- Requires `x-api-key: ${API_KEY}` header for protected endpoints.

### `adminer`
- Lightweight DB admin UI at `http://localhost:5081`.
- Useful for quick inspection/editing during development.

### `metabase`
- Analytics & dashboards at `http://localhost:5000`.
- Uses a local file store to save Metabase application data (not your Postgres data).

---

## 🔐 Authentication

Protected endpoints require an API key via header:
```
x-api-key: YOUR_API_KEY
```
Set `API_KEY` in your `.env` and keep it secret.

---

## 📡 API overview (current)

**Public**
- `GET /health` → `{"status":"ok"}`

**Writes**
- `POST /log/feed`
  ```json
  {
    "ts": "2025-10-02T10:10:00Z",     // optional; defaults to server time
    "type": "breast" | "bottle",
    "side": "left" | "right",         // optional
    "duration_min": 20,               // optional
    "volume_ml": 60,                  // optional
    "notes": "latched well"           // optional
  }
  ```
- `POST /log/nappyevent`
  ```json
  {
    "ts": "2025-10-02T10:12:00Z",     // optional; defaults to server time
    "type": "pee" | "poo",
    "description": "mushy, yellow"
  }
  ```

**Deletes**
- `DELETE /last/feed` → 204 (deletes most recently inserted feed)
- `DELETE /last/nappyevent[?type=pee|poo]` → 204 (deletes latest matching)

**Reads**
- `GET /last/feed` → latest feed (with a human “x ago” string)
- `GET /last/nappyevent[?type=pee|poo]` → latest nappy event
- `GET /stats/feeds?period=24h|7d` → counts + totals (volume/duration)
- `GET /stats/nappyevents?period=24h|7d[&type=pee|poo]` → counts

> Tie-breaking for “latest” uses an `id DESC` strategy for **deletes** (undo semantics), and timestamp-based results can use `ts DESC, id DESC` if you prefer “latest by event time” in reads.

---

## 🧪 Example usage

```bash
# Health
curl -s http://localhost:5080/health

# Log a breast feed
curl -s -X POST http://localhost:5080/log/feed \
  -H "x-api-key: ${API_KEY}" -H "Content-Type: application/json" \
  -d '{"type":"breast","side":"left","duration_min":20,"notes":"latched"}'

# Log a nappy event (poo)
curl -s -X POST http://localhost:5080/log/nappyevent \
  -H "x-api-key: ${API_KEY}" -H "Content-Type: application/json" \
  -d '{"type":"poo","description":"yellow mushy"}'

# Get last events
curl -s -H "x-api-key: ${API_KEY}" http://localhost:5080/last/feed
curl -s -H "x-api-key: ${API_KEY}" "http://localhost:5080/last/nappyevent?type=pee"

# Stats over last 24 hours
curl -s -H "x-api-key: ${API_KEY}" "http://localhost:5080/stats/feeds?period=24h"
curl -s -H "x-api-key: ${API_KEY}" "http://localhost:5080/stats/nappyevents?period=24h&type=poo"

# Undo last mistakes
curl -s -X DELETE -H "x-api-key: ${API_KEY}" http://localhost:5080/last/feed
curl -s -X DELETE -H "x-api-key: ${API_KEY}" "http://localhost:5080/last/nappyevent?type=pee"
```

---

## 🔭 Roadmap / Notes

- Alexa skill / Home Assistant integration layer (intents → API calls).
- Alerting rules (e.g., notify if no feed for N hours).
- Fine-grained auth (per-device or per-skill keys).
- Pagination & history endpoints.
- Optional soft-delete & audit logs.

---

## 🧯 Troubleshooting

- **Tests fail with “no such table”**: ensure tests run with `TESTING=1` (Compose sets this for `api-tests`) so SQLite in-memory is used and tables are created on lifespan startup. Use `make test-clean` if caching interferes.
- **API 401s**: add `x-api-key` header with the value from `.env`.
- **Containers can’t talk to nginx**: confirm `proxy` network exists and that `api`, `adminer`, and `metabase` are attached to it.
- **Metabase tables not visible**: verify DB creds and that tables exist (`feeds`, `nappyevents`). You can log a few events first.
