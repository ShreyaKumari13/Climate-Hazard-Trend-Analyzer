"""Climate hazard detection logic.

Three hazards share one detection engine: find runs of consecutive days on the
wrong side of a threshold, where the threshold comes from a fixed
climatological baseline. Only the variable, the comparison direction and the
run length differ.

Definitions follow the ETCCDI climate-index conventions where one exists, so
the rules are standard rather than invented:

  Heatwave        3+ consecutive days with daily max temperature above the
                  95th percentile of baseline daily max temperature.
                  (The brief's definition; close to the WSDI index, which
                  uses 6 days and a day-of-year percentile.)

  Heavy rainfall  Days with precipitation above the 95th percentile of
                  baseline *wet-day* precipitation - ETCCDI's "very wet days"
                  (R95p). Percentiles are taken over wet days only (>= 1 mm);
                  including dry days would drag the percentile toward zero in
                  arid climates and make almost any shower a "heavy" event.

  Drought         15+ consecutive dry days (< 1 mm), i.e. ETCCDI's CDD
                  (Consecutive Dry Days) spell index. A fixed 1 mm cutoff is
                  the WMO convention for a dry day, so no percentile is
                  involved. CDD is used in preference to SPI because SPI needs
                  a fitted gamma distribution over monthly aggregates, which
                  is a different (and much heavier) pipeline.

Design notes / documented assumptions:
  * Thresholds are computed from the *baseline* window so the bar is fixed and
    trends are measured against a stable reference, not a moving target. The
    caller must supply a series that spans the baseline (see services.cache,
    which widens the upstream fetch to guarantee it).
  * Real-world data has gaps. A single missing day inside an otherwise
    qualifying run does NOT break the run (an isolated gap is treated as
    non-informative); two or more consecutive missing days do break it.
  * Missing days are excluded from the percentile, excluded from the run
    length, and tracked via per-year ``coverage`` so the API can be honest
    about data completeness.

All functions here are pure (no I/O) so the climate logic is unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

import numpy as np

#: WMO convention: a "wet day" has at least 1 mm of precipitation.
WET_DAY_MM = 1.0

#: Minimum valid observations (~1 year) required to trust the baseline window.
MIN_BASELINE_DAYS = 365

Direction = Literal["above", "below"]
IntensityMode = Literal["excess", "peak", "none"]


@dataclass
class HazardEvent:
    start_date: str
    end_date: str
    duration: int
    #: Meaning depends on the hazard - see ``IntensityMode``. ``None`` when the
    #: hazard has no meaningful per-event intensity (drought, where duration
    #: *is* the severity measure).
    peak_intensity: float | None


#: Back-compat alias: the heatwave-only name used before the engine was shared.
HeatwaveEvent = HazardEvent


@dataclass
class YearSummary:
    year: int
    events: list[HazardEvent] = field(default_factory=list)
    days_present: int = 0
    days_expected: int = 365

    @property
    def event_count(self) -> int:
        return len(self.events)

    @property
    def hazard_days(self) -> int:
        return sum(e.duration for e in self.events)

    @property
    def mean_duration(self) -> float:
        return float(np.mean([e.duration for e in self.events])) if self.events else 0.0

    @property
    def max_intensity(self) -> float | None:
        vals = [e.peak_intensity for e in self.events if e.peak_intensity is not None]
        return max(vals, default=None)

    @property
    def coverage(self) -> float:
        if self.days_expected == 0:
            return 0.0
        return round(min(1.0, self.days_present / self.days_expected), 3)


@dataclass
class ThresholdResult:
    """The threshold plus provenance, so callers can be honest."""

    value: float
    #: The year window the threshold was ACTUALLY computed from, e.g.
    #: "1991-2020", or a label like "fixed 1 mm/day" for non-percentile rules.
    baseline_label: str
    #: Number of valid daily observations behind the threshold.
    n_days: int
    #: True when the requested baseline window was unusable and we fell back
    #: to the record itself - the threshold is then NOT comparable across
    #: differently-scoped requests.
    fallback: bool


def compute_threshold(
    dates: list[str],
    values: list[float | None],
    baseline_start: int,
    baseline_end: int,
    percentile: float = 95.0,
    include: Callable[[float], bool] | None = None,
) -> ThresholdResult | None:
    """Percentile of ``values`` over the baseline window.

    ``include`` optionally restricts which days enter the percentile - used by
    heavy rainfall to consider wet days only.

    If fewer than ``MIN_BASELINE_DAYS`` valid baseline observations are present
    we fall back to the full record and flag it via ``ThresholdResult.fallback``
    - a fallback threshold is self-referential and must not be presented as a
    fixed climatological reference.
    """
    def _ok(v: float | None) -> bool:
        return v is not None and (include is None or include(v))

    baseline_vals = [
        v
        for d, v in zip(dates, values)
        if _ok(v) and baseline_start <= _year_of(d) <= baseline_end
    ]

    # Wet-day percentiles legitimately have far fewer than 365 samples, so the
    # minimum only applies to unfiltered series.
    minimum = MIN_BASELINE_DAYS if include is None else 30

    if len(baseline_vals) >= minimum:
        return ThresholdResult(
            value=float(np.percentile(baseline_vals, percentile)),
            baseline_label=f"{baseline_start}-{baseline_end}",
            n_days=len(baseline_vals),
            fallback=False,
        )

    all_vals = [v for v in values if _ok(v)]
    if not all_vals:
        return None
    present_years = [_year_of(d) for d, v in zip(dates, values) if _ok(v)]
    return ThresholdResult(
        value=float(np.percentile(all_vals, percentile)),
        baseline_label=f"{min(present_years)}-{max(present_years)}",
        n_days=len(all_vals),
        fallback=True,
    )


def fixed_threshold(
    dates: list[str],
    values: list[float | None],
    value: float,
    label: str,
) -> ThresholdResult:
    """A threshold that is defined by convention rather than by percentile.

    Used for drought, where a dry day is "< 1 mm" by WMO convention. There is
    no baseline to fall back from, so ``fallback`` is always False.
    """
    return ThresholdResult(
        value=value,
        baseline_label=label,
        n_days=sum(1 for v in values if v is not None),
        fallback=False,
    )


def detect_events(
    dates: list[str],
    values: list[float | None],
    threshold: float,
    min_days: int,
    direction: Direction = "above",
    intensity: IntensityMode = "excess",
) -> list[HazardEvent]:
    """Find runs of ``min_days``+ consecutive days past ``threshold``.

    A run is extended across a single isolated missing day; two consecutive
    missing days (or one qualifying-failure day) terminate it.
    """
    events: list[HazardEvent] = []
    run_start: int | None = None
    run_last: int | None = None  # index of the last confirmed qualifying day
    run_peak: float | None = None
    consecutive_gaps = 0

    def _qualifies(v: float) -> bool:
        return v > threshold if direction == "above" else v < threshold

    def _intensity_of(v: float) -> float | None:
        if intensity == "excess":
            return abs(v - threshold)
        if intensity == "peak":
            return v
        return None

    def _flush() -> None:
        nonlocal run_start, run_last, run_peak
        if run_start is not None and run_last is not None:
            duration = _count_qualifying(
                values, threshold, run_start, run_last, direction
            )
            if duration >= min_days:
                events.append(
                    HazardEvent(
                        start_date=dates[run_start],
                        end_date=dates[run_last],
                        duration=duration,
                        peak_intensity=None if run_peak is None else round(run_peak, 2),
                    )
                )
        run_start = None
        run_last = None
        run_peak = None

    for i, v in enumerate(values):
        if v is None:
            # Missing day: tolerate a single gap inside a run.
            if run_start is not None:
                consecutive_gaps += 1
                if consecutive_gaps >= 2:
                    _flush()
                    consecutive_gaps = 0
            continue

        if _qualifies(v):
            consecutive_gaps = 0
            if run_start is None:
                run_start = i
            run_last = i
            got = _intensity_of(v)
            if got is not None:
                run_peak = got if run_peak is None else max(run_peak, got)
        else:
            _flush()
            consecutive_gaps = 0

    _flush()
    return events


def detect_heatwaves(
    dates: list[str],
    tmax: list[float | None],
    threshold: float,
    min_days: int = 3,
) -> list[HazardEvent]:
    """Heatwave detection: runs of days above the temperature threshold."""
    return detect_events(
        dates, tmax, threshold, min_days, direction="above", intensity="excess"
    )


def summarize_by_year(
    dates: list[str],
    values: list[float | None],
    events: list[HazardEvent],
) -> list[YearSummary]:
    """Aggregate detected events per calendar year, tracking data coverage."""
    years = sorted({_year_of(d) for d in dates})
    summaries = {y: YearSummary(year=y, days_expected=_days_in_year(y)) for y in years}

    for d, v in zip(dates, values):
        if v is not None:
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


def _count_qualifying(
    values: list[float | None],
    threshold: float,
    start: int,
    end: int,
    direction: Direction,
) -> int:
    """Count only genuinely-qualifying days in [start, end] (gaps don't count)."""
    def ok(v: float | None) -> bool:
        if v is None:
            return False
        return v > threshold if direction == "above" else v < threshold

    return sum(1 for v in values[start : end + 1] if ok(v))
