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

### 3. Configure Metabase
- Visit `<babylog-api-host>:5000`
- Complete initial Metabase setup (create admin user)
- Add a new database:
  - Type: PostgreSQL
  - Host: `db`
  - Port: `5432`
  - Database name: your `${DB_NAME}`
  - Username: your `${DB_USER}`
  - Password: your `${DB_PASSWORD}`
- Mark fields (`ts` as DateTime, `type` as Category, etc.) so charts work properly

### 4. Verify API health
```bash
curl http://<babylog-api-host>:5080/health
```

### 5. Run tests
```bash
make test
```

### 6. Export the API spec
To generate an `openapi.json` file on your host:
```bash
make openapi
```

---

## Makefile Overview

The included `Makefile` provides convenience commands:

- `make build` — build the API and test images  
- `make up` — start API + DB services  
- `make down` — stop all services  
- `make logs` — follow API logs  
- `make test` — run the test suite in container  
- `make wipe-data` — truncate all activity tables (with confirmation prompt)  
- `make openapi` — export the OpenAPI spec (`openapi.json`)  

---

## API Overview

Endpoints require `x-api-key: ${API_KEY}` header unless noted.

- `GET /health` — Health check (no key required)
- `POST /log/feedevent` — Log a feed event (breast/bottle, side, duration, volume, notes, ts optional)
- `POST /log/nappyevent` — Log a nappy event (pee/poo, description, ts optional)
- `GET /last/feedevent` — Retrieve latest feed event
- `DELETE /last/feedevent` — Delete latest feed event
- `GET /last/nappyevent[?type=pee|poo]` — Retrieve latest nappy event (optional filter)  
- `DELETE /last/nappyevent[?type=pee|poo]` — Delete latest nappy event (optional filter)  
- `GET /stats/feedevents?period=Nh|Nd` — Aggregate feed events counts/durations/volumes over period  
- `GET /stats/nappyevents?period=Nh|Nd[&type=pee|poo]` — Aggregate nappy events over period  

---

## Example Usage

```bash
# Log a feed
curl -X POST http://<babylog-api-host>:5080/log/feedevent   -H "x-api-key: ${API_KEY}" -H "Content-Type: application/json"   -d '{"type":"breast","side":"left","duration_min":20}'

# Log a nappy event
curl -X POST http://<babylog-api-host>:5080/log/nappyevent   -H "x-api-key: ${API_KEY}" -H "Content-Type: application/json"   -d '{"type":"poo","notes":"yellow mushy"}'

# Retrieve last feed
curl -H "x-api-key: ${API_KEY}" http://<babylog-api-host>:5080/last/feedevent

# Stats over last 24 hours
curl -H "x-api-key: ${API_KEY}"   "http://<babylog-api-host>:5080/stats/feedevents?period=24h"
```

---

## Repository Layout

```
├── babylog-api
│   ├── app
│   │   ├── adapters    # DB engine, session, ORM models and repositories (Postgres/SQLite)
│   │   ├── api         # FastAPI routes and dependencies (auth, DB session)
│   │   ├── domain      # Pydantic models and repository interface definitions
│   │   └── services    # Business logic, stats, human-readable helpers
│   ├── scripts         # Utility scripts (e.g., export OpenAPI spec)
│   └── tests           # Pytest test suite (runs with SQLite in-memory)
└── specs               # Exported API specs (e.g., openapi.json)
```
