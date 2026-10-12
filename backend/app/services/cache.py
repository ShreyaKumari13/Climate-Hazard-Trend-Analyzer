"""Cache-key construction and the orchestration of fetch -> compute -> store.

Keeps the router thin: it calls ``run_analysis`` and gets back a fully-formed
response dict plus a ``cached`` flag.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from .. import db
from ..config import get_settings
from ..models import MIN_YEAR, AnalysisQuery
from . import hazards, trends
from .weather import DailySeries, fetch_daily


def _analysis_key(q: AnalysisQuery) -> str:
    settings = get_settings()
    payload = {
        "lat": round(q.lat, 4),
        "lon": round(q.lon, 4),
        "start": q.start_year,
        "end": q.end_year,
        "hazard": q.hazard.value,
        "pct": settings.heatwave_percentile,
        "min_days": settings.heatwave_min_days,
        "baseline": [settings.baseline_start, settings.baseline_end],
    }
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def _raw_key(lat: float, lon: float, start_year: int, end_year: int) -> str:
    raw = f"{round(lat,4)}:{round(lon,4)}:{start_year}:{end_year}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def _get_raw(lat: float, lon: float, start_year: int, end_year: int) -> DailySeries:
    """Fetch daily data, caching the raw upstream pull in Mongo."""
    settings = get_settings()
    key = _raw_key(lat, lon, start_year, end_year)
    cached = await db.get_doc("raw_weather", key)
    if cached and "series" in cached:
        s = cached["series"]
        return DailySeries(
            dates=s["dates"], tmax=s["tmax"], tmin=s["tmin"],
            precipitation=s["precipitation"],
        )

    series = await fetch_daily(lat, lon, start_year, end_year)
    await db.put_doc(
        "raw_weather",
        key,
        {"series": {
            "dates": series.dates, "tmax": series.tmax,
            "tmin": series.tmin, "precipitation": series.precipitation,
        }},
        ttl_seconds=settings.raw_cache_ttl,
    )
    return series


async def run_analysis(q: AnalysisQuery) -> dict:
    """Return the analysis response dict, using cache where possible."""
    settings = get_settings()
    key = _analysis_key(q)

    cached = await db.get_doc("analysis_cache", key)
    if cached and "response" in cached:
        resp = dict(cached["response"])
        resp["cached"] = True
        return resp

    warnings: list[str] = []

    # Fetch a span that covers BOTH the requested window and the climatological
    # baseline, so the percentile threshold is a genuinely fixed reference
    # rather than one derived from the very years whose trend we measure.
    # The widened span is shared across requests for the same point, so it also
    # improves the cache hit rate rather than costing us extra upstream calls.
    this_year = datetime.now(timezone.utc).year
    fetch_start = max(MIN_YEAR, min(q.start_year, settings.baseline_start))
    fetch_end = max(q.end_year, min(settings.baseline_end, this_year))
    series = await _get_raw(q.lat, q.lon, fetch_start, fetch_end)

    # Report coverage for the window the USER asked about, not the widened pull.
    req_idx = [
        i for i, d in enumerate(series.dates)
        if q.start_year <= int(d[:4]) <= q.end_year
    ]
    req_missing = sum(1 for i in req_idx if series.tmax[i] is None)
    if req_missing:
        frac = req_missing / max(1, len(req_idx))
        warnings.append(
            f"{req_missing} of {len(req_idx)} days "
            f"({frac:.1%}) had missing max-temperature data."
        )

    threshold = hazards.compute_threshold(
        series.dates, series.tmax,
        settings.baseline_start, settings.baseline_end,
        settings.heatwave_percentile,
    )
    if threshold is None:
        raise ValueError("No valid temperature data available for this location/range.")

    if threshold.fallback:
        warnings.append(
            f"The {settings.baseline_start}-{settings.baseline_end} baseline was "
            f"unavailable for this location, so the {settings.heatwave_percentile:.0f}th-"
            f"percentile threshold was derived from the {threshold.baseline_label} "
            "record itself. Thresholds computed this way are not comparable with "
            "other regions or time ranges."
        )

    events = hazards.detect_heatwaves(
        series.dates, series.tmax, threshold.value, settings.heatwave_min_days
    )
    year_summaries = hazards.summarize_by_year(series.dates, series.tmax, events)

    # Restrict the reported series to the requested window: the fetch above is
    # deliberately wider (it covers the baseline), so trim it back here.
    year_summaries = [
        ys for ys in year_summaries if q.start_year <= ys.year <= q.end_year
    ]

    years = [ys.year for ys in year_summaries]
    day_counts = [float(ys.heatwave_days) for ys in year_summaries]
    roll = trends.rolling_mean(day_counts, window=5)
    trend = trends.analyze_trend(years, day_counts)
    insight = trends.build_insight(q.region_name, q.start_year, trend)

    series_out = []
    for ys, rm in zip(year_summaries, roll):
        if ys.coverage < 0.5:
            warnings.append(f"Year {ys.year} has low data coverage ({ys.coverage:.0%}).")
        series_out.append({
            "year": ys.year,
            "heatwave_events": ys.event_count,
            "heatwave_days": ys.heatwave_days,
            "mean_duration": round(ys.mean_duration, 2),
            "max_intensity": ys.max_intensity,
            "rolling_mean": rm,
            "coverage": ys.coverage,
        })

    # An incomplete final year understates its hazard count and drags the
    # fitted trend down, so say so explicitly rather than letting it pass.
    if series_out and series_out[-1]["coverage"] < 0.99:
        last = series_out[-1]
        warnings.append(
            f"{last['year']} is incomplete ({last['coverage']:.0%} of the year has "
            "data), so its counts are partial and the trend through that year "
            "should be read with care."
        )

    response = {
        "region_name": q.region_name,
        "lat": q.lat,
        "lon": q.lon,
        "hazard": q.hazard.value,
        "start_year": q.start_year,
        "end_year": q.end_year,
        "threshold_celsius": round(threshold.value, 2),
        "baseline": threshold.baseline_label,
        "baseline_fallback": threshold.fallback,
        "baseline_days": threshold.n_days,
        "series": series_out,
        "trend": {
            "slope_per_year": trend.slope_per_year,
            "percent_change": trend.percent_change,
            "r_squared": trend.r_squared,
            "p_value": trend.p_value,
            "mann_kendall_trend": trend.mann_kendall_trend,
            "mann_kendall_p": trend.mann_kendall_p,
            "significant": trend.significant,
        },
        "insight": insight,
        "cached": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "warnings": sorted(set(warnings)),
    }

    await db.put_doc(
        "analysis_cache", key, {"response": response},
        ttl_seconds=settings.analysis_cache_ttl,
    )
    return response
