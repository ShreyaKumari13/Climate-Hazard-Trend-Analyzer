"""Climate hazard detection logic.

Heatwave definition (per the brief):
    A heatwave is a run of 3+ consecutive days where the daily maximum
    temperature exceeds the region's 95th percentile of daily max temp,
    computed over a fixed climatological baseline (default 1991-2020).

Design notes / documented assumptions:
  * The percentile threshold is computed from the *baseline* window so that
    the "hotness" bar is fixed and trends across the full record are
    measured against a stable reference (rather than a moving target).
  * Real-world data has gaps. A single missing day inside an otherwise
    qualifying run does NOT break the run (we treat an isolated gap as
    non-informative); two or more consecutive missing days do break it.
  * Days with missing tmax are excluded from the percentile computation and
    from the consecutive-day count, but tracked via per-year ``coverage``
    so the frontend/README can be honest about data completeness.

All functions here are pure (no I/O) so the climate logic is unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class HeatwaveEvent:
    start_date: str
    end_date: str
    duration: int
    peak_intensity: float  # max (°C above threshold) during the event


@dataclass
class YearSummary:
    year: int
    events: list[HeatwaveEvent] = field(default_factory=list)
    days_present: int = 0
    days_expected: int = 365

    @property
    def event_count(self) -> int:
        return len(self.events)

    @property
    def heatwave_days(self) -> int:
        return sum(e.duration for e in self.events)

    @property
    def mean_duration(self) -> float:
        return float(np.mean([e.duration for e in self.events])) if self.events else 0.0

    @property
    def max_intensity(self) -> float | None:
        return max((e.peak_intensity for e in self.events), default=None)

    @property
    def coverage(self) -> float:
        if self.days_expected == 0:
            return 0.0
        return round(min(1.0, self.days_present / self.days_expected), 3)


#: Minimum valid observations (~1 year) required to trust the baseline window.
MIN_BASELINE_DAYS = 365


@dataclass
class ThresholdResult:
    """The percentile threshold plus provenance, so callers can be honest."""

    value: float
    #: The year window the threshold was ACTUALLY computed from, e.g. "1991-2020".
    baseline_label: str
    #: Number of valid daily observations behind the percentile.
    n_days: int
    #: True when the requested baseline window was unusable and we fell back
    #: to the record itself — the threshold is then NOT comparable across
    #: differently-scoped requests.
    fallback: bool


def compute_threshold(
    dates: list[str],
    tmax: list[float | None],
    baseline_start: int,
    baseline_end: int,
    percentile: float = 95.0,
) -> ThresholdResult | None:
    """Return the percentile threshold of daily max temp over the baseline window.

    The caller is responsible for supplying a series that actually spans the
    baseline window (see ``services.cache``, which widens the upstream fetch to
    guarantee it). If fewer than ``MIN_BASELINE_DAYS`` valid baseline
    observations are present we fall back to the full record and say so via
    ``ThresholdResult.fallback`` — a fallback threshold is self-referential and
    must not be presented as a fixed climatological reference.
    """
    baseline_vals = [
        t
        for d, t in zip(dates, tmax)
        if t is not None and baseline_start <= _year_of(d) <= baseline_end
    ]

    if len(baseline_vals) >= MIN_BASELINE_DAYS:
        return ThresholdResult(
            value=float(np.percentile(baseline_vals, percentile)),
            baseline_label=f"{baseline_start}-{baseline_end}",
            n_days=len(baseline_vals),
            fallback=False,
        )

    # Fallback: use whatever record we have, and label it truthfully.
    all_vals = [t for t in tmax if t is not None]
    if not all_vals:
        return None
    present_years = [_year_of(d) for d, t in zip(dates, tmax) if t is not None]
    return ThresholdResult(
        value=float(np.percentile(all_vals, percentile)),
        baseline_label=f"{min(present_years)}-{max(present_years)}",
        n_days=len(all_vals),
        fallback=True,
    )


def detect_heatwaves(
    dates: list[str],
    tmax: list[float | None],
    threshold: float,
    min_days: int = 3,
) -> list[HeatwaveEvent]:
    """Detect heatwave events across the full series.

    A run is extended across a single isolated missing day; two consecutive
    missing days (or a below-threshold day) terminate it.
    """
    events: list[HeatwaveEvent] = []
    run_start: int | None = None
    run_last_hot: int | None = None  # index of last confirmed hot day
    run_intensity = 0.0
    consecutive_gaps = 0

    def _flush(end_idx: int) -> None:
        nonlocal run_start, run_last_hot, run_intensity
        if run_start is not None and run_last_hot is not None:
            duration = _count_hot_days(tmax, threshold, run_start, run_last_hot)
            if duration >= min_days:
                events.append(
                    HeatwaveEvent(
                        start_date=dates[run_start],
                        end_date=dates[run_last_hot],
                        duration=duration,
                        peak_intensity=round(run_intensity, 2),
                    )
                )
        run_start = None
        run_last_hot = None
        run_intensity = 0.0

    for i, t in enumerate(tmax):
        if t is None:
            # Missing day: tolerate a single gap inside a run.
            if run_start is not None:
                consecutive_gaps += 1
                if consecutive_gaps >= 2:
                    _flush(i)
                    consecutive_gaps = 0
            continue

        if t > threshold:
            consecutive_gaps = 0
            if run_start is None:
                run_start = i
            run_last_hot = i
            run_intensity = max(run_intensity, t - threshold)
        else:
            _flush(i)
            consecutive_gaps = 0

    _flush(len(tmax))
    return events


def summarize_by_year(
    dates: list[str],
    tmax: list[float | None],
    events: list[HeatwaveEvent],
) -> list[YearSummary]:
    """Aggregate detected events per calendar year, tracking data coverage."""
    years = sorted({_year_of(d) for d in dates})
    summaries = {y: YearSummary(year=y, days_expected=_days_in_year(y)) for y in years}

    for d, t in zip(dates, tmax):
        if t is not None:
            summaries[_year_of(d)].days_present += 1

    for ev in events:
        # Attribute an event to the year of its start date.
        summaries[_year_of(ev.start_date)].events.append(ev)

    return [summaries[y] for y in years]


# --- helpers ---------------------------------------------------------------

def _year_of(date_str: str) -> int:
    return int(date_str[:4])


def _days_in_year(year: int) -> int:
    leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
    return 366 if leap else 365


def _count_hot_days(
    tmax: list[float | None], threshold: float, start: int, end: int
) -> int:
    """Count only genuinely-hot days in [start, end] (gaps don't count)."""
    return sum(
        1
        for t in tmax[start : end + 1]
        if t is not None and t > threshold
    )
