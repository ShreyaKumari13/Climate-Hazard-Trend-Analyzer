"""MongoDB (NoSQL) connection via Motor, with a graceful in-memory fallback.

The brief requires a NoSQL store. In production (Render) we connect to
MongoDB Atlas. For local development without a Mongo instance, the app falls
back to a simple in-process dict cache so it still runs — this is logged
loudly on startup and reported via /api/health so it's never silent.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from .config import get_settings

logger = logging.getLogger(__name__)

_client: Any = None
_db: Any = None
_mem_store: dict[str, dict] = {}  # fallback: key -> {"doc":..., "expires_at":...}
_using_fallback = False


async def connect() -> None:
    """Establish the Mongo connection (or fall back to in-memory)."""
    global _client, _db, _using_fallback
    settings = get_settings()

    if not settings.mongodb_uri:
        _using_fallback = True
        logger.warning(
            "MONGODB_URI not set — using IN-MEMORY cache fallback. "
            "Set MONGODB_URI (MongoDB Atlas) for persistent NoSQL caching."
        )
        return

    try:
        from motor.motor_asyncio import AsyncIOMotorClient

        _client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
        # Force a round-trip so we fail fast if the URI/network is wrong.
        await _client.admin.command("ping")
        _db = _client[settings.mongodb_db]
        await _ensure_indexes()
        logger.info("Connected to MongoDB database '%s'", settings.mongodb_db)
    except Exception as exc:  # noqa: BLE001 - degrade gracefully on any connect error
        _using_fallback = True
        logger.warning(
            "Could not connect to MongoDB (%s) — using IN-MEMORY cache fallback.", exc
        )


async def _ensure_indexes() -> None:
    # TTL indexes so cached docs expire automatically.
    await _db.analysis_cache.create_index("expires_at", expireAfterSeconds=0)
    await _db.raw_weather.create_index("expires_at", expireAfterSeconds=0)
    await _db.analysis_cache.create_index("key", unique=True)
    await _db.raw_weather.create_index("key", unique=True)


async def close() -> None:
    if _client is not None:
        _client.close()


def using_fallback() -> bool:
    return _using_fallback


async def get_doc(collection: str, key: str) -> dict | None:
    """Fetch a cached doc by key, honoring TTL in the fallback store."""
    if _using_fallback:
        entry = _mem_store.get(f"{collection}:{key}")
        if not entry:
            return None
        if entry["expires_at"] < time.time():
            _mem_store.pop(f"{collection}:{key}", None)
            return None
        return entry["doc"]

    return await _db[collection].find_one({"key": key})


async def put_doc(collection: str, key: str, doc: dict, ttl_seconds: int) -> None:
    """Upsert a cached doc with a TTL."""
    if _using_fallback:
        _mem_store[f"{collection}:{key}"] = {
            "doc": doc,
            "expires_at": time.time() + ttl_seconds,
        }
        return

    import datetime as _dt

    record = dict(doc)
    record["key"] = key
    record["expires_at"] = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(seconds=ttl_seconds)
    await _db[collection].update_one({"key": key}, {"$set": record}, upsert=True)
