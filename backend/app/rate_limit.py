"""Per-IP rate limiting.

The limiter lives in its own module so that both ``main`` (which registers the
error handler) and the routers (which decorate their endpoints) can import it
without a circular import.

Why decorators and not ``SlowAPIMiddleware``:
    slowapi's middleware resolves the matched endpoint by scanning
    ``app.routes`` for an object exposing ``.endpoint``. Since Starlette 1.7 /
    FastAPI 0.143, routes added via ``include_router`` are kept behind an
    ``_IncludedRouter`` wrapper rather than being flattened into ``app.routes``,
    so that scan returns ``None`` for every ``/api/*`` path. slowapi reads a
    ``None`` handler as "exempt" and waves the request through — the configured
    limits are parsed but never consulted.

    Applying ``@limiter.limit(...)`` per endpoint skips that lookup entirely and
    is version-independent, so the limit is actually enforced.

Note: every decorated endpoint must accept a ``request: Request`` argument —
slowapi reads the client address off it.
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import get_settings

settings = get_settings()

limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit])

#: Convenience alias so routers read ``@limiter.limit(DEFAULT_LIMIT)``.
DEFAULT_LIMIT = settings.rate_limit
