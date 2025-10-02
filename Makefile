# Use docker-compose v1 or v2 (adjust if you use `docker compose`)
COMPOSE ?= docker-compose

.PHONY: help build build-clean test test-clean up down logs

help:
	@echo "make build        - Build API and API-Tests images"
	@echo "make build-clean  - Fresh build (no cache, pull bases)"
	@echo "make test         - Build api + api-tests, then run tests"
	@echo "make test-clean   - Fresh build then run tests"
	@echo "make up           - Start api + db"
	@echo "make down         - Stop stack"
	@echo "make logs         - Tail API logs"

build:
	$(COMPOSE) build api api-tests

build-clean:
	$(COMPOSE) build --no-cache --pull api api-tests

test: build
	$(COMPOSE) run --rm api-tests

test-clean: build-clean
	$(COMPOSE) run --rm api-tests

up:
	$(COMPOSE) up -d api db

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f api

openapi:
	$(COMPOSE) build api
	$(COMPOSE) run --rm -T api \
	  python -c "import json; from app.main import app; print(json.dumps(app.openapi(), indent=2))" \
	  > babylog-api/openapi.json
	@echo "Wrote babylog-api/openapi.json"
