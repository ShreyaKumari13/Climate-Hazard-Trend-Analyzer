"""Cache-key construction and the orchestration of fetch -> compute -> store.

Keeps the router thin: it calls ``run_analysis`` and gets back a fully-formed
response dict plus a ``cached`` flag.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from .. import db
from ..config import get_settings
from ..models import MIN_YEAR, AnalysisQuery, HazardType
from . import hazards, trends
from .weather import DailySeries, fetch_daily


@dataclass(frozen=True)
class HazardSpec:
    """Everything that differs between hazards, in one place.

    Adding a hazard means adding a row here plus an enum member - the fetch,
    caching, aggregation and trend layers are hazard-agnostic.
    """

    #: Which daily variable the rule is applied to.
    variable: str
    #: "above" (heat, rainfall) or "below" (dry days).
    direction: str
    #: How per-event intensity is measured.
    intensity: str
    #: Unit of the threshold, for display.
    unit: str
    #: Noun used in the generated insight sentence.
    metric_label: str
    #: Human-readable statement of the rule, surfaced in the API response.
    definition: str


def _hazard_spec(hazard: HazardType, settings) -> HazardSpec:
    if hazard is HazardType.heatwave:
        return HazardSpec(
            variable="tmax",
            direction="above",
            intensity="excess",
            unit="°C",
            metric_label="heatwave days",
            definition=(
                f"{settings.heatwave_min_days}+ consecutive days with daily maximum "
                f"temperature above the {settings.heatwave_percentile:.0f}th percentile "
                f"of the {settings.baseline_start}-{settings.baseline_end} baseline."
            ),
        )
    if hazard is HazardType.heavy_rainfall:
        return HazardSpec(
            variable="precipitation",
            direction="above",
            intensity="peak",
            unit="mm",
            metric_label="heavy-rainfall days",
            definition=(
                f"Days with precipitation above the {settings.rainfall_percentile:.0f}th "
                f"percentile of wet-day (>= {hazards.WET_DAY_MM:.0f} mm) precipitation in "
                f"the {settings.baseline_start}-{settings.baseline_end} baseline "
                "(ETCCDI R95p, 'very wet days')."
            ),
        )
    if hazard is HazardType.drought:
        return HazardSpec(
            variable="precipitation",
            direction="below",
            intensity="none",
            unit="mm",
            metric_label="drought days",
            definition=(
                f"{settings.drought_min_days}+ consecutive dry days, where a dry day has "
                f"less than {settings.dry_day_mm:.0f} mm of precipitation "
                "(ETCCDI CDD, consecutive dry days)."
            ),
        )
    raise ValueError(f"unsupported hazard: {hazard}")


def _min_days(hazard: HazardType, settings) -> int:
    return {
        HazardType.heatwave: settings.heatwave_min_days,
        HazardType.heavy_rainfall: settings.rainfall_min_days,
        HazardType.drought: settings.drought_min_days,
    }[hazard]


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
        "rain_pct": settings.rainfall_percentile,
        "rain_min_days": settings.rainfall_min_days,
        "dry_mm": settings.dry_day_mm,
        "drought_min_days": settings.drought_min_days,
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
    _spec_var = _hazard_spec(q.hazard, settings).variable
    _vals = getattr(series, _spec_var)
    req_missing = sum(1 for i in req_idx if _vals[i] is None)
    if req_missing:
        frac = req_missing / max(1, len(req_idx))
        label = "max-temperature" if _spec_var == "tmax" else "precipitation"
        warnings.append(
            f"{req_missing} of {len(req_idx)} days "
            f"({frac:.1%}) had missing {label} data."
        )

    spec = _hazard_spec(q.hazard, settings)
    values = getattr(series, spec.variable)

    if q.hazard is HazardType.heatwave:
        threshold = hazards.compute_threshold(
            series.dates, values,
            settings.baseline_start, settings.baseline_end,
            settings.heatwave_percentile,
        )
    elif q.hazard is HazardType.heavy_rainfall:
        # Percentile over WET days only: including dry days would pull the
        # percentile toward zero in arid climates and label light showers as
        # extreme. This is the ETCCDI R95p convention.
        threshold = hazards.compute_threshold(
            series.dates, values,
            settings.baseline_start, settings.baseline_end,
            settings.rainfall_percentile,
            include=lambda v: v >= hazards.WET_DAY_MM,
        )
    else:  # drought - a fixed WMO dry-day cutoff, not a percentile
        threshold = hazards.fixed_threshold(
            series.dates, values,
            value=settings.dry_day_mm,
            label=f"fixed {settings.dry_day_mm:.0f} mm/day (WMO dry-day definition)",
        )

    if threshold is None:
        raise ValueError(
            f"No valid {spec.variable} data available for this location/range."
        )

    if threshold.fallback:
        warnings.append(
            f"The {settings.baseline_start}-{settings.baseline_end} baseline was "
            f"unavailable for this location, so the threshold was derived from the "
            f"{threshold.baseline_label} record itself. Thresholds computed this way "
            "are not comparable with other regions or time ranges."
        )

    events = hazards.detect_events(
        series.dates, values, threshold.value,
        min_days=_min_days(q.hazard, settings),
        direction=spec.direction,
        intensity=spec.intensity,
    )
    year_summaries = hazards.summarize_by_year(series.dates, values, events)

    # Restrict the reported series to the requested window: the fetch above is
    # deliberately wider (it covers the baseline), so trim it back here.
    year_summaries = [
        ys for ys in year_summaries if q.start_year <= ys.year <= q.end_year
    ]

    years = [ys.year for ys in year_summaries]
    day_counts = [float(ys.hazard_days) for ys in year_summaries]
    roll = trends.rolling_mean(day_counts, window=5)
    trend = trends.analyze_trend(years, day_counts)
    insight = trends.build_insight(
        q.region_name, q.start_year, trend, metric_label=spec.metric_label
    )

    series_out = []
    for ys, rm in zip(year_summaries, roll):
        if ys.coverage < 0.5:
            warnings.append(f"Year {ys.year} has low data coverage ({ys.coverage:.0%}).")
        series_out.append({
            "year": ys.year,
            "events": ys.event_count,
            "hazard_days": ys.hazard_days,
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
        "threshold": round(threshold.value, 2),
        "threshold_unit": spec.unit,
        "hazard_definition": spec.definition,
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
