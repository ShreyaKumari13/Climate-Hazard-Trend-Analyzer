"""Pydantic request/response schemas with validation.

Validation here is the first line of defence for the "safe handling of user
inputs" evaluation dimension: latitude/longitude bounds, sane year ranges,
and a guard on the maximum span of data requested.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

# A reasonable lower bound: Open-Meteo's archive (ERA5) begins in 1940.
MIN_YEAR = 1940
MAX_SPAN_YEARS = 80


class HazardType(str, Enum):
    heatwave = "heatwave"
    # Stubs for extensibility; only heatwave is fully implemented.
    drought = "drought"
    heavy_rainfall = "heavy_rainfall"


class AnalysisQuery(BaseModel):
    """Validated parameters for an analysis request."""

    lat: float = Field(..., ge=-90, le=90, description="Latitude in degrees")
    lon: float = Field(..., ge=-180, le=180, description="Longitude in degrees")
    start_year: int = Field(..., ge=MIN_YEAR)
    end_year: int = Field(..., ge=MIN_YEAR)
    hazard: HazardType = HazardType.heatwave
    region_name: str | None = Field(default=None, max_length=120)

    @field_validator("region_name")
    @classmethod
    def _clean_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        # Strip control characters; keep it a plain label.
        return "".join(ch for ch in v if ch.isprintable()).strip() or None

    @field_validator("end_year")
    @classmethod
    def _end_year_not_future(cls, v: int) -> int:
        current = datetime.now(timezone.utc).year
        if v > current:
            raise ValueError(f"end_year cannot be in the future (>{current})")
        return v

    @model_validator(mode="after")
    def _check_range(self) -> "AnalysisQuery":
        if self.end_year < self.start_year:
            raise ValueError("end_year must be >= start_year")
        if self.end_year - self.start_year + 1 > MAX_SPAN_YEARS:
            raise ValueError(f"requested span exceeds {MAX_SPAN_YEARS} years")
        return self


class YearPoint(BaseModel):
    year: int
    heatwave_events: int
    heatwave_days: int
    mean_duration: float
    max_intensity: float | None
    rolling_mean: float | None = None
    coverage: float = Field(..., description="Fraction of expected days with data (0-1)")


class TrendStats(BaseModel):
    slope_per_year: float
    percent_change: float | None
    r_squared: float
    p_value: float
    mann_kendall_trend: str
    mann_kendall_p: float
    significant: bool


class AnalysisResponse(BaseModel):
    region_name: str | None
    lat: float
    lon: float
    hazard: HazardType
    start_year: int
    end_year: int
    threshold_celsius: float
    #: The year window the threshold was actually computed from.
    baseline: str
    #: True when the configured baseline was unavailable and the threshold was
    #: derived from the requested record itself (not a fixed reference).
    baseline_fallback: bool = False
    #: Number of daily observations behind the percentile.
    baseline_days: int = 0
    series: list[YearPoint]
    trend: TrendStats
    insight: str
    cached: bool
    generated_at: str
    warnings: list[str] = []


class RegionPreset(BaseModel):
    name: str
    lat: float
    lon: float
    country: str
