"""Trend analysis for annual hazard series.

Three complementary views, all honest about uncertainty:

  * Rolling average      - smooths year-to-year noise for the chart.
  * Linear regression    - slope + R^2 + p-value (parametric).
  * Mann-Kendall test    - non-parametric trend test, robust to outliers and
                           non-normal data; the preferred significance signal
                           for short, noisy climate series.

Implemented with numpy + math.erf only (no scipy) so the stats are
self-contained and dependency-light. The regression p-value uses a normal
approximation of the t-distribution, which is accurate for the ~30-year
series this tool targets (documented assumption).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class TrendResult:
    slope_per_year: float
    intercept: float
    r_squared: float
    p_value: float
    percent_change: float | None
    mann_kendall_trend: str
    mann_kendall_p: float
    significant: bool


def rolling_mean(values: list[float], window: int = 5) -> list[float | None]:
    """Centered rolling mean; edges where the window doesn't fit are None."""
    n = len(values)
    out: list[float | None] = [None] * n
    if window <= 1 or n < window:
        return out
    half = window // 2
    arr = np.asarray(values, dtype=float)
    for i in range(half, n - half):
        out[i] = round(float(arr[i - half : i + half + 1].mean()), 3)
    return out


def _normal_sf(z: float) -> float:
    """Two-sided survival probability for a standard normal |z|."""
    return math.erfc(abs(z) / math.sqrt(2))


def linear_regression(years: list[int], values: list[float]) -> tuple[float, float, float, float]:
    """Return (slope, intercept, r_squared, p_value) via ordinary least squares."""
    x = np.asarray(years, dtype=float)
    y = np.asarray(values, dtype=float)
    n = len(x)
    if n < 3 or np.allclose(x, x[0]):
        return 0.0, float(y.mean()) if n else 0.0, 0.0, 1.0

    x_mean, y_mean = x.mean(), y.mean()
    sxx = float(((x - x_mean) ** 2).sum())
    sxy = float(((x - x_mean) * (y - y_mean)).sum())
    slope = sxy / sxx if sxx else 0.0
    intercept = y_mean - slope * x_mean

    y_pred = slope * x + intercept
    ss_res = float(((y - y_pred) ** 2).sum())
    ss_tot = float(((y - y_mean) ** 2).sum())
    r_squared = 1 - ss_res / ss_tot if ss_tot else 0.0

    # Standard error of the slope -> t statistic -> normal-approx p-value.
    if n > 2 and ss_res > 0 and sxx > 0:
        se = math.sqrt((ss_res / (n - 2)) / sxx)
        t_stat = slope / se if se else 0.0
        p_value = _normal_sf(t_stat)
    else:
        p_value = 0.0 if slope != 0 else 1.0

    return slope, intercept, r_squared, p_value


def mann_kendall(values: list[float]) -> tuple[str, float]:
    """Mann-Kendall trend test. Returns (trend_label, two_sided_p_value).

    Uses the normal approximation of S with a tie correction, which is
    standard for n >= ~10.
    """
    n = len(values)
    if n < 4:
        return "insufficient data", 1.0

    x = np.asarray(values, dtype=float)
    s = 0
    for i in range(n - 1):
        s += int(np.sign(x[i + 1 :] - x[i]).sum())

    # Variance with tie correction.
    _, counts = np.unique(x, return_counts=True)
    tie_term = sum(c * (c - 1) * (2 * c + 5) for c in counts)
    var_s = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0

    if var_s <= 0:
        return "no trend", 1.0

    if s > 0:
        z = (s - 1) / math.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / math.sqrt(var_s)
    else:
        z = 0.0

    p = _normal_sf(z)
    if p < 0.05:
        trend = "increasing" if s > 0 else "decreasing"
    else:
        trend = "no significant trend"
    return trend, round(p, 4)


def analyze_trend(years: list[int], values: list[float]) -> TrendResult:
    """Full trend analysis combining regression and Mann-Kendall."""
    slope, intercept, r2, p_value = linear_regression(years, values)
    mk_trend, mk_p = mann_kendall(values)

    # Honest percent change: compare fitted values at the endpoints, not the
    # raw (noisy) first/last observations. Undefined if the fitted start ~0.
    percent_change: float | None = None
    if years:
        fitted_start = slope * years[0] + intercept
        fitted_end = slope * years[-1] + intercept
        if abs(fitted_start) > 1e-6:
            percent_change = round((fitted_end - fitted_start) / abs(fitted_start) * 100, 1)

    significant = mk_p < 0.05 and p_value < 0.05
    return TrendResult(
        slope_per_year=round(slope, 4),
        intercept=round(intercept, 4),
        r_squared=round(r2, 3),
        p_value=round(p_value, 4),
        percent_change=percent_change,
        mann_kendall_trend=mk_trend,
        mann_kendall_p=mk_p,
        significant=significant,
    )


def build_insight(
    region_name: str | None,
    start_year: int,
    trend: TrendResult,
    metric_label: str = "heatwave days",
) -> str:
    """Generate an honest, human-readable headline insight."""
    where = f"in {region_name}" if region_name else "in this region"

    if trend.mann_kendall_trend == "insufficient data":
        return f"Not enough data to assess a reliable trend {where}."

    direction = trend.mann_kendall_trend
    if direction == "no significant trend":
        return (
            f"{metric_label.capitalize()} show no statistically significant trend "
            f"{where} since {start_year} (Mann-Kendall p={trend.mann_kendall_p})."
        )

    if trend.percent_change is not None:
        magnitude = f"by about {abs(trend.percent_change):.0f}%"
    else:
        magnitude = f"by about {abs(trend.slope_per_year):.2f} days/year"

    verb = "increased" if direction == "increasing" else "decreased"
    confidence = "statistically significant" if trend.significant else "suggestive but not conclusive"
    return (
        f"{metric_label.capitalize()} have {verb} {magnitude} {where} since {start_year} "
        f"({confidence}; Mann-Kendall p={trend.mann_kendall_p}, R²={trend.r_squared})."
    )
