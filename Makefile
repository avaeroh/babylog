# --- Load .env so $(DB_USER) / $(DB_NAME) are available to Make ---
ifneq (,$(wildcard .env))
include .env
export
endif

COMPOSE ?= docker-compose
export DOCKER_DEFAULT_PLATFORM := linux/arm64

.PHONY: help build build-clean test test-clean up down logs wipe-data \
        openapi-spec openapi lambda-build lambda-test lambda-test-clean \
        lambda-zip-aws lambda-zip-aws-list lambda-zip-aws-verify lambda-zip-aws-clean

help:
	@echo "make build                 - Build API and API-Tests images"
	@echo "make build-clean           - Fresh build (no cache, pull bases)"
	@echo "make test                  - Build api + api-tests, then run tests"
	@echo "make test-clean            - Clean build then run tests"
	@echo "make up                    - Start api + db"
	@echo "make down                  - Stop stack"
	@echo "make logs                  - Tail API logs"
	@echo "make wipe-data             - ⚠️  Truncate ALL tables (dangerous!)"
	@echo "make openapi               - Export OpenAPI spec to specs/openapi.json"
	@echo ""
	@echo "Lambda:"
	@echo "make lambda-test           - Run Alexa unit tests (offline)"
	@echo "make lambda-test-clean     - Clean rebuild + run Lambda tests"
	@echo "make lambda-zip-aws        - Build specs/lambda.zip for AWS"
	@echo "make lambda-zip-aws-clean  - Remove build artifacts"

# ---------- App targets ----------
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

# ---------- DB wipe ----------
# Truncates every table in the connected Postgres DB.
# Safe schema-only approach — keeps tables but removes rows and resets sequences.
wipe-data:
	@read -p "⚠️  This will DELETE ALL DATA in database '$(DB_NAME)'. Type YES to continue: " confirm && \
	if [ "$$confirm" = "YES" ]; then \
	  echo "Truncating all tables in $(DB_NAME)..."; \
	  $(COMPOSE) exec -T db psql -U $(DB_USER) -d $(DB_NAME) -v ON_ERROR_STOP=1 -c \
	    "DO $$ BEGIN EXECUTE (SELECT string_agg(format('TRUNCATE TABLE %%I.%%I RESTART IDENTITY CASCADE;', schemaname, tablename), ' ') FROM pg_tables WHERE schemaname='public'); END $$;"; \
	  echo "✅ All tables truncated."; \
	else \
	  echo "Cancelled."; \
	fi

# --- OpenAPI export ---
openapi-spec:
	$(COMPOSE) build api
	$(COMPOSE) run --rm -T api \
	  python -c "import json; from app.main import app; print(json.dumps(app.openapi(), indent=2))" \
	  > specs/openapi.json
	@echo "Wrote specs/openapi.json"

openapi: openapi-spec

# --- Lambda tests ---
lambda-build:
	$(COMPOSE) build lambda-tests

lambda-test: lambda-build
	$(COMPOSE) run --rm -e RUN_LAMBDA_ITESTS=0 lambda-tests

lambda-test-clean:
	$(COMPOSE) build --no-cache --pull lambda-tests
	$(COMPOSE) run --rm -e RUN_LAMBDA_ITESTS=0 lambda-tests

lambda-zip-aws:
	@echo "Building AWS Lambda ZIP (pure Python)..."
	@docker run --rm --platform=linux/arm64/v8 \
	  -e PIP_ROOT_USER_ACTION=ignore -e DEBIAN_FRONTEND=noninteractive \
	  -v "$$PWD":/work -w /work python:3.11-slim /bin/sh -c ' \
	    set -e; \
	    rm -rf build_lambda; mkdir -p build_lambda specs; \
	    python -m pip install --upgrade pip -q; \
	    pip install --no-cache-dir -q --target build_lambda \
	      --no-binary charset-normalizer \
	      ask-sdk-core==1.19.0 ask-sdk-model==1.49.0 ask-sdk-runtime==1.19.0; \
	    cp alexa-integration/lambda_function.py build_lambda/; \
	    find build_lambda -name __pycache__ -type d -prune -exec rm -rf {} +; \
	    find build_lambda -name "*.pyc" -delete; \
	    find build_lambda -name "*.dist-info" -type d -prune -exec rm -rf {} +; \
	    find build_lambda -name "*.so" -delete || true; \
	    apt-get update -y >/dev/null && apt-get install -y zip >/dev/null; \
	    cd build_lambda && zip -qr ../specs/lambda.zip .; \
	    echo "Wrote specs/lambda.zip" \
	  '
	@echo "✅ Built specs/lambda.zip"
