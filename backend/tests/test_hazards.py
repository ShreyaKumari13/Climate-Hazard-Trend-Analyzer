"""Tests for heatwave detection and yearly aggregation."""
from __future__ import annotations

from app.services import hazards


def _dates(start="2000-01-01", n=10):
    import datetime as dt
    d0 = dt.date.fromisoformat(start)
    return [(d0 + dt.timedelta(days=i)).isoformat() for i in range(n)]


def test_threshold_percentile():
    dates = _dates(n=400)
    # 400 days, values 0..399; 95th percentile is deterministic.
    tmax = [float(i) for i in range(400)]
    thr = hazards.compute_threshold(dates, tmax, 2000, 2001, percentile=95)
    assert thr is not None
    assert 370 < thr.value < 385  # ~95th percentile of 0..399
    assert thr.fallback is False
    assert thr.baseline_label == "2000-2001"


def test_threshold_uses_only_baseline_years_when_present():
    """The threshold must come from the baseline window, not the whole record."""
    import datetime as dt

    dates, tmax = [], []
    # 1991-1992: the baseline — mild (around 20 C).
    for year in (1991, 1992):
        for i in range(365):
            dates.append((dt.date(year, 1, 1) + dt.timedelta(days=i)).isoformat())
            tmax.append(20.0)
    # 2020: much hotter. It must NOT drag the threshold up.
    for i in range(365):
        dates.append((dt.date(2020, 1, 1) + dt.timedelta(days=i)).isoformat())
        tmax.append(50.0)

    thr = hazards.compute_threshold(dates, tmax, 1991, 1992, percentile=95)
    assert thr is not None
    assert thr.fallback is False
    assert thr.baseline_label == "1991-1992"
    assert thr.value == 20.0  # purely from the baseline years
    assert thr.n_days == 730


def test_threshold_flags_fallback_when_baseline_absent():
    """A record that misses the baseline window must be labelled honestly."""
    dates = _dates(start="1960-01-01", n=400)
    tmax = [float(i % 40) for i in range(400)]
    thr = hazards.compute_threshold(dates, tmax, 1991, 2020, percentile=95)
    assert thr is not None
    assert thr.fallback is True
    # Labelled with the window actually used, NOT the requested baseline.
    assert thr.baseline_label.startswith("1960")
    assert "1991-2020" != thr.baseline_label


def test_threshold_none_when_no_valid_data():
    dates = _dates(n=10)
    assert hazards.compute_threshold(dates, [None] * 10, 1991, 2020) is None


def test_detects_three_consecutive_hot_days():
    dates = _dates(n=6)
    # threshold 30: days 1-3 hot (31,32,33), rest cool.
    tmax = [20.0, 31.0, 32.0, 33.0, 20.0, 20.0]
    events = hazards.detect_heatwaves(dates, tmax, threshold=30.0, min_days=3)
    assert len(events) == 1
    assert events[0].duration == 3
    assert events[0].peak_intensity == 3.0  # 33 - 30


def test_two_hot_days_is_not_a_heatwave():
    dates = _dates(n=5)
    tmax = [31.0, 32.0, 20.0, 20.0, 20.0]
    events = hazards.detect_heatwaves(dates, tmax, threshold=30.0, min_days=3)
    assert events == []


def test_single_gap_does_not_break_run():
    dates = _dates(n=6)
    # hot, hot, MISSING, hot, hot -> should still be one event of 4 hot days.
    tmax = [31.0, 32.0, None, 33.0, 34.0, 20.0]
    events = hazards.detect_heatwaves(dates, tmax, threshold=30.0, min_days=3)
    assert len(events) == 1
    assert events[0].duration == 4  # 4 genuinely-hot days, gap not counted


def test_two_consecutive_gaps_break_run():
    dates = _dates(n=7)
    tmax = [31.0, 32.0, None, None, 33.0, 34.0, 20.0]
    events = hazards.detect_heatwaves(dates, tmax, threshold=30.0, min_days=3)
    # First run only has 2 hot days -> not an event. Second run 2 hot -> not an event.
    assert events == []


def test_summarize_by_year_and_coverage():
    # Two years, one heatwave in each.
    import datetime as dt
    dates, tmax = [], []
    for year in (2000, 2001):
        for i in range(10):
            dates.append((dt.date(year, 6, 1) + dt.timedelta(days=i)).isoformat())
            tmax.append(35.0 if i < 4 else 20.0)  # 4 hot days each year
    events = hazards.detect_heatwaves(dates, tmax, threshold=30.0, min_days=3)
    summaries = hazards.summarize_by_year(dates, tmax, events)
    assert len(summaries) == 2
    for s in summaries:
        assert s.event_count == 1
        assert s.heatwave_days == 4
        assert 0 < s.coverage < 0.1  # only 10 days of a full year present
