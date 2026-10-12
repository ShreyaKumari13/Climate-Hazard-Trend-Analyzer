"""Tests for trend math (regression + Mann-Kendall + insight)."""
from __future__ import annotations

from app.services import trends


def test_regression_positive_slope():
    years = list(range(2000, 2020))
    values = [float(i) for i in range(20)]  # perfectly increasing
    slope, intercept, r2, p = trends.linear_regression(years, values)
    assert slope > 0
    assert round(r2, 3) == 1.0
    assert p < 0.05


def test_regression_flat_series():
    years = list(range(2000, 2020))
    values = [5.0] * 20
    slope, intercept, r2, p = trends.linear_regression(years, values)
    assert abs(slope) < 1e-9
    assert p == 1.0


def test_mann_kendall_increasing():
    values = [float(i) for i in range(15)]
    trend, p = trends.mann_kendall(values)
    assert trend == "increasing"
    assert p < 0.05


def test_mann_kendall_no_trend():
    values = [5, 4, 6, 5, 5, 4, 6, 5, 5, 6, 4, 5]
    trend, p = trends.mann_kendall(values)
    assert trend == "no significant trend"


def test_analyze_trend_percent_change():
    years = list(range(2000, 2011))
    values = [float(i + 1) for i in range(11)]  # 1..11
    result = trends.analyze_trend(years, values)
    assert result.slope_per_year > 0
    assert result.percent_change is not None
    assert result.significant is True


def test_build_insight_mentions_region_and_significance():
    years = list(range(1990, 2021))
    values = [float(i) for i in range(31)]
    result = trends.analyze_trend(years, values)
    insight = trends.build_insight("Phoenix", 1990, result)
    assert "Phoenix" in insight
    assert "increased" in insight
