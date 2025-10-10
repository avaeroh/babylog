# app/main.py
from __future__ import annotations
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.api.routes import router as api_router
from app.adapters.repositories import init_db
from app.adapters.db import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
log = logging.getLogger(__name__)

def wait_for_db(timeout_s: int = 30, interval_s: float = 1.0) -> None:
    """Block until DB is reachable (SELECT 1), or raise after timeout."""
    start = time.time()
    attempts = 0
    last_err = None
    while time.time() - start < timeout_s:
        attempts += 1
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            log.info("DB reachable after %s attempt(s)", attempts)
            return
        except SQLAlchemyError as e:
            last_err = e
            log.info("DB not ready yet (attempt %s): %s", attempts, repr(e))
            time.sleep(interval_s)
    log.error("DB still not reachable after %ss: %s", timeout_s, repr(last_err))
    raise last_err or RuntimeError("DB not reachable")

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        wait_for_db(timeout_s=45, interval_s=1.5)
        init_db()
        log.info("Startup complete")
    except Exception:
        logging.exception("Startup failed")
        raise
    yield
    log.info("Shutdown complete")

app = FastAPI(title=settings.app_name, lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(ValueError)
async def handle_value_error(_: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})

app.include_router(api_router)
