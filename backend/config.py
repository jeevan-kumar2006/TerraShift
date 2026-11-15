"""Centralized configuration for TerraShift (India-Exclusive Earth System Trend Detective).

Only allowed constants live here:
- Statistical alpha (0.05)
- India geographical bounding box
- Official API base URLs and Gemini model identifier
- Canonical dataset IDs / short-names and physical units
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = REPO_ROOT / "data"
BOUNDARIES_DIR = DATA_DIR / "boundaries"
CACHE_FILE = BACKEND_DIR / "cases_cache.json"
SATELLITE_CACHE_DIR = DATA_DIR / "processed" / "satellite_cache"

# Statistical significance threshold
STATISTICAL_ALPHA: float = 0.05
MIN_GRID_CELLS_WARNING: int = 3

# Exclusive India geographical bounding box (Survey of India domain)
INDIA_BOUNDS: dict[str, float] = {
    "lat_min": 6.0,
    "lat_max": 37.5,
    "lon_min": 68.0,
    "lon_max": 97.5,
}

# External API Base URLs
NASA_POWER_POINT_URL: str = "https://power.larc.nasa.gov/api/temporal/monthly/point"
NASA_POWER_REGIONAL_URL: str = "https://power.larc.nasa.gov/api/temporal/monthly/regional"
NASA_CMR_COLLECTIONS_URL: str = "https://cmr.earthdata.nasa.gov/search/collections.json"
NASA_CMR_GRANULES_URL: str = "https://cmr.earthdata.nasa.gov/search/granules.json"
NASA_APPEEARS_PRODUCTS_URL: str = "https://appeears.earthdatacloud.nasa.gov/api/v1/product"
NASA_GIOVANNI_BASE_URL: str = "https://giovanni.gsfc.nasa.gov/giovanni/"
GEMINI_API_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/models"

# Single configured stable Gemini model (overridable via GEMINI_MODEL env var)
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"

# Maximum offline fallback radius (km)
MAX_FALLBACK_RADIUS_KM: float = float(os.environ.get("MAX_FALLBACK_RADIUS_KM", "500.0"))

# Canonical dataset IDs and physical units
DATASET_UNITS: dict[str, str] = {
    "T2M": "°C",
    "PRECTOTCORR": "mm/day",
    "GWETROOT": "fraction (0–1)",
    "GWETPROF": "fraction (0–1)",
    "QV2M": "g/kg",
    "MOD13C2": "NDVI (-0.2 to 1.0)",
    "GPM_3IMERGM": "mm/month",
    "OMNO2d": "10^15 molec/cm²",
    "MOD11C3": "°C",
}
