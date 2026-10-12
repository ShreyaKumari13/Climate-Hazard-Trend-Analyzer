"""FastAPI application entrypoint.

Wires together CORS, per-IP rate limiting, the DB connection lifecycle, and
the analysis router.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from . import db
from .config import get_settings
from .rate_limit import limiter
from .routers import analysis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    yield
    await db.close()


app = FastAPI(
    title="Climate Hazard Trend Analyzer",
    description="Analyzes historical weather data and visualizes climate-hazard trends.",
    version="1.0.0",
    lifespan=lifespan,
)

# Limits are enforced by the ``@limiter.limit`` decorators on each endpoint
# (see app/rate_limit.py for why the middleware is deliberately not used).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

allow_all = "*" in settings.allowed_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if allow_all else settings.allowed_origins,
    allow_credentials=not allow_all,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(analysis.router)


@app.get("/")
@limiter.limit(settings.rate_limit)
async def root(request: Request) -> dict:
    return {
        "name": "Climate Hazard Trend Analyzer API",
        "docs": "/docs",
        "endpoints": ["/api/health", "/api/regions", "/api/analyze", "/api/export"],
    }


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Never leak internal/upstream error details to the client.
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
