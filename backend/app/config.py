"""Application configuration, loaded from environment variables.

Keeping all tunables in one place makes the app easy to configure per
environment (local vs Render) without touching code.

Locally, values are read from a ``.env`` file beside the ``backend/`` root if
one exists (see ``.env.example``). Real environment variables always win, so
the hosted deployment is configured purely through Render's dashboard and
never depends on a file being present.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

try:
    from dotenv import load_dotenv

    # ``override=False``: a real env var beats the file, which is what we want
    # in production. Points at backend/.env regardless of the working directory.
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
except ImportError:  # pragma: no cover - python-dotenv is an explicit dependency
    pass


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings:
    """Runtime settings sourced from environment variables."""

    def __init__(self) -> None:
        # --- Database ---------------------------------------------------
        # If unset, the app runs with an in-memory cache fallback so it
        # still works locally without a Mongo instance (logged on startup).
        self.mongodb_uri: str | None = os.getenv("MONGODB_URI") or None
        self.mongodb_db: str = os.getenv("MONGODB_DB", "climate_hazard")

        # --- CORS -------------------------------------------------------
        # Comma-separated list of allowed origins. "*" allows all (dev only).
        self.allowed_origins: list[str] = _split_csv(
            os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
        )

        # --- Caching ----------------------------------------------------
        # TTL (seconds) for computed analysis results and raw weather pulls.
        self.analysis_cache_ttl: int = int(os.getenv("ANALYSIS_CACHE_TTL", str(60 * 60 * 24 * 7)))
        self.raw_cache_ttl: int = int(os.getenv("RAW_CACHE_TTL", str(60 * 60 * 24 * 30)))

        # --- Upstream weather API --------------------------------------
        self.open_meteo_url: str = os.getenv(
            "OPEN_METEO_URL", "https://archive-api.open-meteo.com/v1/archive"
        )
        self.http_timeout: float = float(os.getenv("HTTP_TIMEOUT", "30"))
        self.http_retries: int = int(os.getenv("HTTP_RETRIES", "3"))

        # --- Rate limiting ---------------------------------------------
        self.rate_limit: str = os.getenv("RATE_LIMIT", "30/minute")

        # --- Climate logic ---------------------------------------------
        # Baseline climatology window used to derive the percentile threshold.
        self.baseline_start: int = int(os.getenv("BASELINE_START", "1991"))
        self.baseline_end: int = int(os.getenv("BASELINE_END", "2020"))
        self.heatwave_percentile: float = float(os.getenv("HEATWAVE_PERCENTILE", "95"))
        self.heatwave_min_days: int = int(os.getenv("HEATWAVE_MIN_DAYS", "3"))

        # Heavy rainfall: ETCCDI R95p - days above the 95th percentile of
        # baseline WET-day precipitation. One such day is already an event.
        self.rainfall_percentile: float = float(os.getenv("RAINFALL_PERCENTILE", "95"))
        self.rainfall_min_days: int = int(os.getenv("RAINFALL_MIN_DAYS", "1"))

        # Drought: ETCCDI CDD - runs of consecutive dry days. A dry day is
        # < 1 mm (WMO convention), so this rule uses no percentile.
        self.dry_day_mm: float = float(os.getenv("DRY_DAY_MM", "1.0"))
        self.drought_min_days: int = int(os.getenv("DROUGHT_MIN_DAYS", "15"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
