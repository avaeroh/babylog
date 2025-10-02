# ===== Base =====
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PYTHONPATH=/app
WORKDIR /app

# System deps for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
 && rm -rf /var/lib/apt/lists/*

# ===== Deps (runtime) =====
FROM base AS deps
COPY requirements.txt .
RUN pip install -r requirements.txt

# ===== Production image =====
FROM deps AS prod
ENV PYTHONPATH=/app
COPY app ./app
COPY scripts ./scripts
EXPOSE 5080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5080"]

# ===== Test image (adds pytest + test-only deps) =====
FROM deps AS test
ENV PYTHONPATH=/app
RUN pip install pytest httpx
COPY app ./app
COPY tests ./tests
CMD ["python", "-m", "pytest", "-q"]
