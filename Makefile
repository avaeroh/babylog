# --- Load .env so $(DB_USER) / $(DB_NAME) are available to Make ---
ifneq (,$(wildcard .env))
include .env
export
endif

# Use docker-compose v1 (change to `docker compose` if you’ve upgraded to v2)
COMPOSE ?= docker-compose

.PHONY: help build build-clean test test-clean up down logs wipe-data reset-db openapi

help:
	@echo "make build        - Build API and API-Tests images"
	@echo "make build-clean  - Fresh build (no cache, pull bases)"
	@echo "make test         - Build api + api-tests, then run tests"
	@echo "make test-clean   - Fresh build then run tests"
	@echo "make up           - Start api + db"
	@echo "make down         - Stop stack"
	@echo "make logs         - Tail API logs"
	@echo "make wipe-data    - TRUNCATE feeds & nappyevents (with prompt)"
	@echo "make reset-db     - DROP/CREATE database (with prompt)"
	@echo "make openapi      - Export OpenAPI spec to babylog-api/openapi.json"

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

wipe-data:
	@read -p "⚠️  This will TRUNCATE feeds & nappyevents. Type YES to continue: " confirm && \
	if [ "$$confirm" = "YES" ]; then \
		$(COMPOSE) exec -T db psql -v ON_ERROR_STOP=1 -U $(DB_USER) -d $(DB_NAME) \
		  -c "TRUNCATE TABLE public.feeds, public.nappyevents RESTART IDENTITY CASCADE;" && \
		echo "✅ Tables truncated."; \
	else \
		echo "Cancelled."; \
	fi

openapi-spec:
	$(COMPOSE) build api
	$(COMPOSE) run --rm -T api \
	  python -c "import json; from app.main import app; print(json.dumps(app.openapi(), indent=2))" \
	  > specs/openapi.json
	@echo "Wrote specs/openapi.json"

#### LAMBDA #####
lambda-build:
	$(COMPOSE) build lambda-tests

lambda-test: lambda-build
	# Fast unit tests (no network)
	$(COMPOSE) run --rm -e RUN_LAMBDA_ITESTS=0 lambda-tests

lambda-test-clean:
	$(COMPOSE) build --no-cache --pull lambda-tests
	$(COMPOSE) run --rm -e RUN_LAMBDA_ITESTS=0 lambda-tests

# Produces specs/lambda.zip with:
#   - lambda_function.py at ZIP root
#   - ask_sdk_core and transitive deps at ZIP root
# Set Lambda Handler to: lambda_function.lambda_handler
# Produces specs/lambda.zip with:
#   - lambda_function.py at ZIP root
#   - ask_sdk_core, ask_sdk_model, ask_sdk_runtime (and deps) at ZIP root
# Set Lambda Handler to: lambda_function.lambda_handler
lambda-zip:
	@docker run --rm \
	  -e PIP_ROOT_USER_ACTION=ignore \
	  -v "$$PWD":/work -w /work python:3.11-slim /bin/sh -lc '\
	    set -e; \
	    rm -rf build_lambda && mkdir -p build_lambda; \
	    python -m pip install --upgrade pip --no-cache-dir -q; \
	    pip install --no-cache-dir -q --target build_lambda \
	      ask-sdk-core==1.19.0 ask-sdk-model ask-sdk-runtime; \
	    cp alexa-integration/lambda_function.py build_lambda/; \
	    python -c "import os,zipfile; dst=\"specs/lambda.zip\"; os.makedirs(os.path.dirname(dst),exist_ok=True); z=zipfile.ZipFile(dst,\"w\",zipfile.ZIP_DEFLATED); import os; [z.write(os.path.join(r,f), os.path.relpath(os.path.join(r,f),\"build_lambda\")) for r,_,fs in os.walk(\"build_lambda\") for f in fs]; z.close(); print(\"Wrote\", dst)"; \
	  '
	@echo "✅ Built specs/lambda.zip"

lambda-clean:
	@rm -rf build_lambda specs/lambda.zip
	@echo "🧹 Cleaned lambda artifacts"