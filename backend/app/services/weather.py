"""Open-Meteo historical archive client.

Open-Meteo's archive API (ERA5 reanalysis) is free, keyless, and covers
daily data from 1940 to the near-present — which makes it a clean fit for a
keyless Render deployment. This module wraps it with timeout, retry/backoff,
and normalisation of the noisy real-world response (gaps/nulls).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import dataclass

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)

#: ERA5 reanalysis lands in the archive with a lag of roughly five days.
#: Requesting a date beyond it makes Open-Meteo reject the whole call with a
#: 400, so we clamp the end date instead of asking for data that cannot exist.
ARCHIVE_LAG_DAYS = 5


@dataclass
class DailySeries:
    """Normalised daily series for a location.

    dates/tmax are aligned index-for-index. Missing values from upstream are
    preserved as ``None`` in ``tmax`` so downstream logic can reason about
    coverage rather than silently dropping days.
    """

    dates: list[str]
    tmax: list[float | None]
    tmin: list[float | None]
    precipitation: list[float | None]

    @property
    def missing_count(self) -> int:
        return sum(1 for v in self.tmax if v is None)


class WeatherAPIError(RuntimeError):
    """Raised when the upstream weather API cannot be reached or returns bad data."""


class NonRetryableWeatherError(WeatherAPIError):
    """A 4xx from upstream: our request was bad, so retrying will not help."""


async def fetch_daily(
    lat: float, lon: float, start_year: int, end_year: int
) -> DailySeries:
    """Fetch daily tmax/tmin/precip for a location across a span of years.

    Retries with exponential backoff on transient network/5xx errors.
    """
    settings = get_settings()

    start_date = dt.date(start_year, 1, 1)
    latest_available = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(
        days=ARCHIVE_LAG_DAYS
    )
    end_date = min(dt.date(end_year, 12, 31), latest_available)
    if end_date < start_date:
        raise WeatherAPIError(
            f"no archived data exists yet for {start_year} "
            f"(archive currently ends {latest_available.isoformat()})"
        )

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
        "timezone": "UTC",
        # Be explicit about units rather than relying on the provider default.
        "temperature_unit": "celsius",
        "precipitation_unit": "mm",
    }

    last_exc: Exception | None = None
    for attempt in range(1, settings.http_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
                resp = await client.get(settings.open_meteo_url, params=params)

            # 5xx and 429 are transient - worth a retry.
            if resp.status_code >= 500:
                raise WeatherAPIError(f"upstream {resp.status_code}")
            if resp.status_code == 429:
                raise WeatherAPIError("upstream rate limited (429)")

            # Any other 4xx means we sent a bad request. Retrying cannot help
            # and only delays the response while hammering the provider.
            if resp.status_code >= 400:
                detail = _upstream_reason(resp)
                logger.error(
                    "Open-Meteo rejected the request (%s): %s", resp.status_code, detail
                )
                raise NonRetryableWeatherError(
                    f"upstream rejected the request ({resp.status_code}): {detail}"
                )

            return _parse(resp.json())
        except NonRetryableWeatherError:
            raise
        except (httpx.HTTPError, WeatherAPIError) as exc:
            last_exc = exc
            if attempt >= settings.http_retries:
                break
            wait = min(2 ** attempt, 10)
            logger.warning(
                "Open-Meteo fetch failed (attempt %s/%s): %s; retrying in %ss",
                attempt, settings.http_retries, exc, wait,
            )
            await asyncio.sleep(wait)

    raise WeatherAPIError(
        f"failed to fetch weather data after {settings.http_retries} attempts: {last_exc}"
    )


def _upstream_reason(resp: httpx.Response) -> str:
    """Pull Open-Meteo's own error message out of the body, if present."""
    try:
        return str(resp.json().get("reason", resp.text[:200]))
    except Exception:  # noqa: BLE001 - body may not be JSON
        return resp.text[:200]


def _parse(payload: dict) -> DailySeries:
    daily = payload.get("daily")
    if not daily or "time" not in daily:
        raise WeatherAPIError("unexpected response shape from upstream (no daily data)")

    dates = daily.get("time", [])
    tmax = daily.get("temperature_2m_max", [None] * len(dates))
    tmin = daily.get("temperature_2m_min", [None] * len(dates))
    precip = daily.get("precipitation_sum", [None] * len(dates))

    # Defensive: align lengths in case upstream truncates one array.
    n = len(dates)
    def _pad(arr: list) -> list:
        return (arr + [None] * n)[:n]

    return DailySeries(
        dates=dates,
        tmax=_pad(tmax),
        tmin=_pad(tmin),
        precipitation=_pad(precip),
    )
