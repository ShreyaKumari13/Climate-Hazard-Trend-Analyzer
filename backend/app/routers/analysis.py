"""API routes: health, region presets, analyze, and export."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import ValidationError

from ..export import to_csv, to_pdf
from ..models import AnalysisQuery, AnalysisResponse, HazardType, RegionPreset
from ..rate_limit import DEFAULT_LIMIT, limiter
from ..regions import REGION_PRESETS
from ..services.cache import run_analysis
from ..services.weather import WeatherAPIError
from .. import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.get("/health")
@limiter.limit(DEFAULT_LIMIT)
async def health(request: Request) -> dict:
    return {
        "status": "ok",
        "cache_backend": "in-memory-fallback" if db.using_fallback() else "mongodb",
    }


@router.get("/regions", response_model=list[RegionPreset])
@limiter.limit(DEFAULT_LIMIT)
async def regions(request: Request) -> list[RegionPreset]:
    return REGION_PRESETS


def _build_query(
    lat: float, lon: float, start_year: int, end_year: int,
    hazard: HazardType, region_name: str | None,
) -> AnalysisQuery:
    try:
        return AnalysisQuery(
            lat=lat, lon=lon, start_year=start_year, end_year=end_year,
            hazard=hazard, region_name=region_name,
        )
    except ValidationError as exc:
        # Surface a concise message rather than the full Pydantic dump.
        msgs = "; ".join(e["msg"].replace("Value error, ", "") for e in exc.errors())
        raise HTTPException(status_code=422, detail=msgs) from exc


async def _analyze(q: AnalysisQuery) -> dict:
    if q.hazard is not HazardType.heatwave:
        raise HTTPException(
            status_code=501,
            detail=f"Hazard '{q.hazard.value}' is not yet implemented. Use 'heatwave'.",
        )
    try:
        return await run_analysis(q)
    except WeatherAPIError as exc:
        logger.error("Upstream weather error: %s", exc)
        raise HTTPException(status_code=502, detail="Weather data provider is unavailable. Please try again.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/analyze", response_model=AnalysisResponse)
@limiter.limit(DEFAULT_LIMIT)
async def analyze(
    request: Request,
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    start_year: int = Query(...),
    end_year: int = Query(...),
    hazard: HazardType = HazardType.heatwave,
    region_name: str | None = Query(default=None),
) -> dict:
    q = _build_query(lat, lon, start_year, end_year, hazard, region_name)
    return await _analyze(q)


def _safe_filename_label(raw: str) -> str:
    """Reduce a user-supplied label to characters safe in a filename header.

    ``Content-Disposition`` quotes the filename, so an unescaped quote in
    ``region_name`` would terminate the value early. Allow-list rather than
    escape: anything outside [A-Za-z0-9._-] becomes an underscore.
    """
    cleaned = "".join(
        ch if (ch.isascii() and (ch.isalnum() or ch in "._-")) else "_" for ch in raw
    ).strip("._-")
    return (cleaned or "export")[:60]


@router.get("/export")
@limiter.limit(DEFAULT_LIMIT)
async def export(
    request: Request,
    format: str = Query("csv", pattern="^(csv|pdf)$"),
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    start_year: int = Query(...),
    end_year: int = Query(...),
    hazard: HazardType = HazardType.heatwave,
    region_name: str | None = Query(default=None),
) -> Response:
    q = _build_query(lat, lon, start_year, end_year, hazard, region_name)
    result = await _analyze(q)
    label = _safe_filename_label(q.region_name or f"{q.lat}_{q.lon}")

    if format == "csv":
        return Response(
            content=to_csv(result),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{label}_heatwave.csv"'},
        )

    try:
        pdf_bytes = to_pdf(result)
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{label}_heatwave.pdf"'},
    )
