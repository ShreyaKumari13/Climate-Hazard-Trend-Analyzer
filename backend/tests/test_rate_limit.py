"""Rate limiting must actually be enforced.

This guards a real regression: slowapi's ``SlowAPIMiddleware`` resolves the
endpoint by scanning ``app.routes`` for a ``.endpoint`` attribute, which stopped
finding ``include_router`` routes once Starlette began wrapping them in an
``_IncludedRouter``. The limits were parsed and silently never applied. We now
use ``@limiter.limit`` decorators instead; these tests prove the limit bites.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.rate_limit import limiter


def _limit_count() -> int:
    """The configured number of requests allowed per window."""
    return int(get_settings().rate_limit.split("/")[0])


@pytest.fixture(autouse=True)
def _reset_limiter():
    """Each test starts from a clean bucket."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.mark.parametrize("path", ["/", "/api/health", "/api/regions"])
def test_endpoint_is_rate_limited(path):
    limit = _limit_count()
    with TestClient(app) as client:
        codes = [client.get(path).status_code for _ in range(limit + 5)]

    assert codes[:limit] == [200] * limit, "requests within the limit must succeed"
    assert codes[limit:] == [429] * 5, f"{path} did not return 429 past the limit"


def test_limit_response_is_the_standard_429_body():
    with TestClient(app) as client:
        for _ in range(_limit_count()):
            client.get("/api/health")
        blocked = client.get("/api/health")

    assert blocked.status_code == 429
    assert "rate limit" in blocked.text.lower()
