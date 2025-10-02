# app/main.py
from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.api.routes import router as api_router
from app.adapters.repositories import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    init_db()  # create tables if they don't exist (v1 bootstrap)
    # (If you need to warm caches, open clients, schedule jobs, do it here)
    yield
    # --- Shutdown ---
    # (Close clients, flush metrics, cancel jobs, etc., here if needed)


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# CORS (loosen in dev; restrict in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # e.g., ["https://babylog.example.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(ValueError)
async def handle_value_error(_: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})

# Routes
app.include_router(api_router)
