"""A small curated set of region presets for the frontend dropdown.

Intentionally compact — users can also enter custom lat/lon or use the map.
Chosen to span climates where heatwave trends are interesting to inspect.
"""
from __future__ import annotations

from .models import RegionPreset

REGION_PRESETS: list[RegionPreset] = [
    RegionPreset(name="Phoenix, USA", lat=33.4484, lon=-112.0740, country="USA"),
    RegionPreset(name="Delhi, India", lat=28.6139, lon=77.2090, country="India"),
    RegionPreset(name="Seville, Spain", lat=37.3891, lon=-5.9845, country="Spain"),
    RegionPreset(name="Athens, Greece", lat=37.9838, lon=23.7275, country="Greece"),
    RegionPreset(name="Cairo, Egypt", lat=30.0444, lon=31.2357, country="Egypt"),
    RegionPreset(name="Sydney, Australia", lat=-33.8688, lon=151.2093, country="Australia"),
    RegionPreset(name="Paris, France", lat=48.8566, lon=2.3522, country="France"),
    RegionPreset(name="London, UK", lat=51.5074, lon=-0.1278, country="UK"),
    RegionPreset(name="Tokyo, Japan", lat=35.6762, lon=139.6503, country="Japan"),
    RegionPreset(name="Los Angeles, USA", lat=34.0522, lon=-118.2437, country="USA"),
    RegionPreset(name="Mumbai, India", lat=19.0760, lon=72.8777, country="India"),
    RegionPreset(name="São Paulo, Brazil", lat=-23.5505, lon=-46.6333, country="Brazil"),
]
