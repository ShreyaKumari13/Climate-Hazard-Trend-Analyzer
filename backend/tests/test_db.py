"""Tests for the MongoDB cache layer.

The production path talks to MongoDB Atlas, which isn't available in CI, so we
exercise the same code against a Motor-compatible in-memory mock. This covers
the branch that the in-memory fallback would otherwise hide: index creation,
upsert semantics under the unique ``key`` index, and the ``expires_at`` field
that the TTL index depends on.
"""
from __future__ import annotations

import datetime as dt

import pytest
from mongomock_motor import AsyncMongoMockClient

from app import db


@pytest.fixture
async def mongo_db():
    """Point the db module at a mock Mongo, then restore the fallback."""
    client = AsyncMongoMockClient()
    db._client = client
    db._db = client["climate_hazard_test"]
    db._using_fallback = False
    await db._ensure_indexes()
    yield db._db
    db._client = None
    db._db = None
    db._using_fallback = True


async def test_round_trip(mongo_db):
    await db.put_doc("analysis_cache", "k1", {"response": {"insight": "hello"}}, 60)
    got = await db.get_doc("analysis_cache", "k1")
    assert got is not None
    assert got["response"]["insight"] == "hello"


async def test_miss_returns_none(mongo_db):
    assert await db.get_doc("analysis_cache", "absent") is None


async def test_upsert_updates_in_place(mongo_db):
    """The unique index on ``key`` means a re-write must update, not duplicate."""
    await db.put_doc("analysis_cache", "k1", {"response": {"v": 1}}, 60)
    await db.put_doc("analysis_cache", "k1", {"response": {"v": 2}}, 60)

    assert await mongo_db.analysis_cache.count_documents({"key": "k1"}) == 1
    got = await db.get_doc("analysis_cache", "k1")
    assert got["response"]["v"] == 2


async def test_expires_at_is_a_datetime(mongo_db):
    """The TTL index only reaps documents whose expires_at is a real date."""
    await db.put_doc("analysis_cache", "k1", {"response": {}}, ttl_seconds=60)
    raw = await mongo_db.analysis_cache.find_one({"key": "k1"})
    assert isinstance(raw["expires_at"], dt.datetime)


async def test_mongo_id_never_reaches_the_response_payload(mongo_db):
    """``_id`` is not JSON-serialisable, so it must stay out of the cached body."""
    await db.put_doc("analysis_cache", "k1", {"response": {"insight": "x"}}, 60)
    got = await db.get_doc("analysis_cache", "k1")
    assert "_id" not in got["response"]


# --- fallback store --------------------------------------------------------

async def test_fallback_store_honours_ttl():
    db._using_fallback = True
    db._mem_store.clear()

    await db.put_doc("analysis_cache", "k", {"response": {}}, ttl_seconds=-1)
    assert await db.get_doc("analysis_cache", "k") is None  # already expired

    await db.put_doc("analysis_cache", "k", {"response": {"v": 1}}, ttl_seconds=60)
    got = await db.get_doc("analysis_cache", "k")
    assert got["response"]["v"] == 1
