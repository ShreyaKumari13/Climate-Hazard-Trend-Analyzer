"""Tests for input validation (safe handling of user inputs)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import AnalysisQuery


def test_valid_query():
    q = AnalysisQuery(lat=33.4, lon=-112.0, start_year=1990, end_year=2020)
    assert q.hazard.value == "heatwave"


@pytest.mark.parametrize("lat,lon", [(91, 0), (-91, 0), (0, 181), (0, -181)])
def test_rejects_out_of_range_coords(lat, lon):
    with pytest.raises(ValidationError):
        AnalysisQuery(lat=lat, lon=lon, start_year=1990, end_year=2020)


def test_rejects_end_before_start():
    with pytest.raises(ValidationError):
        AnalysisQuery(lat=0, lon=0, start_year=2020, end_year=1990)


def test_rejects_future_end_year():
    with pytest.raises(ValidationError):
        AnalysisQuery(lat=0, lon=0, start_year=1990, end_year=2999)


def test_rejects_too_old_start_year():
    with pytest.raises(ValidationError):
        AnalysisQuery(lat=0, lon=0, start_year=1800, end_year=1900)


def test_rejects_excessive_span():
    with pytest.raises(ValidationError):
        AnalysisQuery(lat=0, lon=0, start_year=1940, end_year=2024)  # 85y span > 80 limit
