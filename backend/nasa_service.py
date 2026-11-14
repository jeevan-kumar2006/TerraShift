"""Hybrid NASA POWER, NASA CMR, AppEEARS, NOAA CDO, KNMI & CSA GeoMet data service."""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import httpx
import pandas as np_pd

CACHE_FILE = Path(__file__).resolve().parent / "cases_cache.json"
NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/monthly/point"
NASA_CMR_COLLECTIONS_URL = "https://cmr.earthdata.nasa.gov/search/collections.json"
NASA_APPEEARS_PRODUCTS_URL = "https://appeears.earthdatacloud.nasa.gov/api/v1/product"
CSA_GEOMET_CLIMATE_URL = "https://api.weather.gc.ca/collections/climate-monthly/items"
CSA_GEOMET_HYDRO_URL = "https://api.weather.gc.ca/collections/hydrometric-monthly-mean/items"
NOAA_CDO_STATIONS_URL = "https://www.ncei.noaa.gov/cdo-web/api/v2/stations"

# In-memory cache for AppEEARS catalog so repeated lookups are instant
_APPEEARS_CACHE: list[dict[str, Any]] | None = None

PARAMETER_METADATA: dict[str, dict[str, str]] = {
    "PRECTOTCORR": {
        "parameter_code": "PRECTOTCORR",
        "parameter_name": "Corrected Monthly Precipitation",
        "unit": "mm/day",
        "mission_source": "NASA GPM / MERRA-2 / Giovanni",
        "resolution": "0.5° × 0.625° MERRA-2 / GPM Grid",
        "plain_definition": "Average daily rain and snow water equivalent falling each month.",
        "question": "Where is rainfall accelerating?",
        "positive_label": "Wetting Trend",
        "negative_label": "Drying Trend",
    },
    "GWETROOT": {
        "parameter_code": "GWETROOT",
        "parameter_name": "Root-Zone Soil Moisture",
        "unit": "fraction (0–1)",
        "mission_source": "NASA GLDAS / SMAP / GES DISC Hydrology",
        "resolution": "0.5° × 0.625° GLDAS / MERRA-2 Grid",
        "plain_definition": "Fraction of water saturation in the top 100 cm of soil where plant roots draw moisture.",
        "question": "Where is drought worsening?",
        "positive_label": "Soil Wetting",
        "negative_label": "Soil Drying",
    },
    "GWETPROF": {
        "parameter_code": "GWETPROF",
        "parameter_name": "Total Profile Soil Wetness",
        "unit": "fraction (0–1)",
        "mission_source": "NASA MODIS NDVI / GLDAS / AppEEARS",
        "resolution": "0.5° × 0.625° GLDAS / MERRA-2 Grid",
        "plain_definition": "Deep soil moisture saturation from surface to bedrock supporting forest canopy health.",
        "question": "Where are forest canopies drying?",
        "positive_label": "Moisture Recovery",
        "negative_label": "Canopy Drying",
    },
    "T2M": {
        "parameter_code": "T2M",
        "parameter_name": "2-Meter Surface Air Temperature",
        "unit": "°C",
        "mission_source": "NASA MERRA-2 / AIRS / NOAA CDO / CSA GeoMet",
        "resolution": "0.5° × 0.625° MERRA-2 Grid",
        "plain_definition": "Monthly average air temperature at 2 meters above the Earth's surface.",
        "question": "Where is warming fastest?",
        "positive_label": "Warming Trend",
        "negative_label": "Cooling Trend",
    },
    "QV2M": {
        "parameter_code": "QV2M",
        "parameter_name": "2-Meter Specific Humidity",
        "unit": "g/kg",
        "mission_source": "NASA MERRA-2 Atmospheric Assimilation",
        "resolution": "0.5° × 0.625° MERRA-2 Grid",
        "plain_definition": "Mass of water vapor per kilogram of air near the surface, driving heat-stress and extreme downpours.",
        "question": "Where is atmospheric humidity rising?",
        "positive_label": "Humidifying",
        "negative_label": "Drying Air",
    },
    "PS": {
        "parameter_code": "PS",
        "parameter_name": "Surface Atmospheric Pressure",
        "unit": "kPa",
        "mission_source": "NASA MERRA-2 / KNMI Climate Explorer",
        "resolution": "0.5° × 0.625° MERRA-2 Grid",
        "plain_definition": "Atmospheric pressure at the surface reflecting shifting storm tracks and circulation cells.",
        "question": "Where are pressure systems shifting?",
        "positive_label": "Rising Pressure",
        "negative_label": "Falling Pressure",
    },
}

PRESET_CASE_SPECS: list[dict[str, Any]] = [
    {
        "case_id": "case_1_enso",
        "title": "Case 1: ENSO Rainfall Seesaw",
        "short_title": "ENSO Seesaw",
        "mechanism_teaser": "Pacific Walker Circulation shifts drive inverse rainfall anomalies between coastal Peru and Maritime Continent Indonesia.",
        "parameter": "PRECTOTCORR",
        "mission_label": "GPM / MERRA-2 / Giovanni",
        "primary_point": {"name": "Northern Peru Coast", "lat": -5.19, "lon": -80.63},
        "comparison_point": {"name": "East Kalimantan, Indonesia", "lat": -1.5, "lon": 116.5},
        "default_window": [1990, 2025],
        "data_source": "NASA POWER (MERRA-2 / GPM Assimilation)",
    },
    {
        "case_id": "case_2_dipole",
        "title": "Case 2: North American Hydrological Dipole",
        "short_title": "Hydrological Dipole",
        "mechanism_teaser": "Subtropical dry-belt expansion desiccates the Southwest while shifting storm tracks wet the Upper Midwest.",
        "parameter": "GWETROOT",
        "mission_label": "GLDAS / SMAP / GES DISC",
        "primary_point": {"name": "US Southwest / Colorado Basin", "lat": 34.5, "lon": -108.0},
        "comparison_point": {"name": "Upper Midwest Basin", "lat": 46.0, "lon": -94.0},
        "default_window": [1990, 2025],
        "data_source": "NASA POWER (MERRA-2 / GLDAS Land Hydrology)",
    },
    {
        "case_id": "case_3_arctic",
        "title": "Case 3: Polar Amplification vs Atlantic Cold Blob",
        "short_title": "Arctic Amplification",
        "mechanism_teaser": "Sea-ice albedo feedback drives rapid Svalbard warming (+0.8°C/dec) while subpolar Atlantic overturning resists warming.",
        "parameter": "T2M",
        "mission_label": "MERRA-2 / AIRS / KNMI",
        "primary_point": {"name": "Svalbard Archipelago", "lat": 78.22, "lon": 15.63},
        "comparison_point": {"name": "Subpolar North Atlantic", "lat": 54.0, "lon": -32.0},
        "default_window": [1990, 2025],
        "data_source": "NASA POWER (MERRA-2 Surface Air Temp)",
    },
    {
        "case_id": "case_4_amazon",
        "title": "Case 4: Amazon Canopy Moisture Stress",
        "short_title": "Amazon Canopy Stress",
        "mechanism_teaser": "Deforestation-edge moisture recycling loss dries the southeastern arc twice as fast as the intact central core.",
        "parameter": "GWETPROF",
        "mission_label": "MODIS NDVI / AppEEARS / GLDAS",
        "primary_point": {"name": "SE Amazon Deforestation Arc", "lat": -12.0, "lon": -55.0},
        "comparison_point": {"name": "Central Amazon Core", "lat": -2.0, "lon": -64.0},
        "default_window": [1990, 2025],
        "data_source": "NASA POWER (MERRA-2 Soil Profile / Canopy Context)",
    },
    {
        "case_id": "case_5_seawifs_coastal",
        "title": "Case 5: River-Plume Coastal Runoff vs Offshore Gyre",
        "short_title": "SeaWiFS Coastal Plume",
        "mechanism_teaser": "Mississippi River watershed discharge & coastal runoff pulses drive nutrient/chlorophyll seesaws against the oligotrophic Gulf Loop Current.",
        "parameter": "PRECTOTCORR",
        "mission_label": "SeaWiFS / MODIS-Aqua / GPM",
        "primary_point": {"name": "Mississippi River Delta Plume", "lat": 29.15, "lon": -89.25},
        "comparison_point": {"name": "Offshore Gulf Loop Current", "lat": 25.0, "lon": -90.0},
        "default_window": [1990, 2025],
        "data_source": "NASA POWER / SeaWiFS Coastal Reference (NTRS 20090042747)",
    },
    {
        "case_id": "case_6_csa_swot_rcm",
        "title": "Case 6: Canadian Cryosphere & Surface Water Shift",
        "short_title": "CSA SWOT & RCM Arctic",
        "mechanism_teaser": "RADARSAT Constellation (RCM) SAR & SWOT hydrology track rapid Mackenzie Delta permafrost/ice warming against the Great Lakes basin.",
        "parameter": "T2M",
        "mission_label": "CSA RCM SAR / SWOT / Geo.ca",
        "primary_point": {"name": "Mackenzie Delta / Beaufort Coast, NT", "lat": 68.8, "lon": -134.4},
        "comparison_point": {"name": "Great Lakes / St. Lawrence Corridor", "lat": 44.2, "lon": -76.5},
        "default_window": [1990, 2025],
        "data_source": "NASA POWER + CSA GeoMet / SWOT / RCM Partner Context",
    },
]


def _load_cache() -> dict[str, Any]:
    """Load cases_cache.json safely, returning an empty structure if missing."""
    if not CACHE_FILE.exists():
        return {"cases": [], "live_cache": {}}
    try:
        with CACHE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"cases": [], "live_cache": {}}
        data.setdefault("cases", [])
        data.setdefault("live_cache", {})
        return data
    except (OSError, json.JSONDecodeError):
        return {"cases": [], "live_cache": {}}


def _save_cache_atomic(data: dict[str, Any]) -> None:
    """Persist cache atomically via temp file + os.replace."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".cases_cache_", suffix=".json", dir=str(CACHE_FILE.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, CACHE_FILE)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _make_cache_key(parameter: str, lat: float, lon: float) -> str:
    return f"{parameter.upper()}|{round(float(lat), 2):.2f}|{round(float(lon), 2):.2f}"


def compute_bounding_box(lat: float, lon: float) -> dict[str, float]:
    """Return the MERRA-2 0.5° × 0.625° grid cell bounding box around a coordinate."""
    return {
        "south": round(float(lat) - 0.25, 4),
        "north": round(float(lat) + 0.25, 4),
        "west": round(float(lon) - 0.3125, 4),
        "east": round(float(lon) + 0.3125, 4),
    }


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2.0 * r * math.asin(min(1.0, math.sqrt(a)))


def _parse_power_monthly_payload(raw_param_dict: dict[str, Any]) -> tuple[list[str], list[float]]:
    """Strip ANN/13 keys, parse YYYYMM into YYYY-MM, trim trailing -999s, and interpolate gaps."""
    records: list[tuple[str, float]] = []
    for k in sorted(raw_param_dict.keys()):
        if not isinstance(k, str) or len(k) != 6 or k.endswith("13"):
            continue
        month_num = int(k[4:6])
        if month_num < 1 or month_num > 12:
            continue
        ts = f"{k[:4]}-{k[4:6]}"
        val = raw_param_dict[k]
        if val is None:
            fv = float("nan")
        else:
            fv = float(val)
            if not math.isfinite(fv) or fv <= -990.0:
                fv = float("nan")
        records.append((ts, fv))

    while records and math.isnan(records[-1][1]):
        records.pop()
    while records and math.isnan(records[0][1]):
        records.pop(0)

    if not records:
        raise ValueError("NASA POWER returned no valid monthly observations for this coordinate.")

    ts_list = [r[0] for r in records]
    vals = np_pd.Series([r[1] for r in records], dtype=float).interpolate(method="linear", limit_direction="both")
    clean_vals = [round(float(v), 4) for v in vals.to_numpy()]
    return ts_list, clean_vals


def _slice_window(
    timestamps: list[str], values: list[float], start_year: int, end_year: int
) -> tuple[list[str], list[float]]:
    sliced_ts: list[str] = []
    sliced_vals: list[float] = []
    for ts, val in zip(timestamps, values):
        yr = int(ts[:4])
        if start_year <= yr <= end_year:
            sliced_ts.append(ts)
            sliced_vals.append(float(val))
    return sliced_ts, sliced_vals


def get_parameter_metadata(parameter: str) -> dict[str, str]:
    """Retrieve student-friendly metadata for a NASA parameter code."""
    code = parameter.upper()
    if code not in PARAMETER_METADATA:
        return {
            "parameter_code": code,
            "parameter_name": code,
            "unit": "units",
            "mission_source": "Multi-Agency Earth Observation",
            "resolution": "0.5° × 0.625° Grid / Point",
            "plain_definition": f"Monthly Earth observation time series for {code}.",
            "question": f"How is {code} changing?",
            "positive_label": "Increasing",
            "negative_label": "Decreasing",
        }
    return PARAMETER_METADATA[code]


def list_preset_cases() -> list[dict[str, Any]]:
    """Return lightweight metadata for the 6 curated Detective Case Files."""
    cache = _load_cache()
    by_id = {c["case_id"]: c for c in cache.get("cases", [])}
    out: list[dict[str, Any]] = []
    for spec in PRESET_CASE_SPECS:
        cached_case = by_id.get(spec["case_id"])
        meta = get_parameter_metadata(spec["parameter"])
        item = {
            "case_id": spec["case_id"],
            "title": spec["title"],
            "short_title": spec["short_title"],
            "mechanism_teaser": spec["mechanism_teaser"],
            "parameter": spec["parameter"],
            "parameter_name": meta["parameter_name"],
            "unit": meta["unit"],
            "mission_label": spec["mission_label"],
            "primary_point": spec["primary_point"],
            "comparison_point": spec["comparison_point"],
            "default_window": (cached_case or spec).get("default_window", [1990, 2025]),
            "data_source": spec["data_source"],
            "cached": cached_case is not None,
        }
        out.append(item)
    return out


def get_preset_case_series(case_id: str, start_year: int | None = None, end_year: int | None = None) -> dict[str, Any] | None:
    """Load pre-seeded case series from cases_cache.json without network access."""
    cache = _load_cache()
    for c in cache.get("cases", []):
        if c.get("case_id") == case_id:
            win = c.get("default_window", [1990, 2025])
            s_yr = start_year if start_year is not None else win[0]
            e_yr = end_year if end_year is not None else win[1]
            p_ts, p_vals = _slice_window(
                c["primary_series"]["timestamps"],
                c["primary_series"]["values"],
                s_yr,
                e_yr,
            )
            c_ts, c_vals = _slice_window(
                c["comparison_series"]["timestamps"],
                c["comparison_series"]["values"],
                s_yr,
                e_yr,
            )
            return {
                "case": c,
                "primary": {
                    "parameter": c["parameter"],
                    "lat": c["primary_point"]["lat"],
                    "lon": c["primary_point"]["lon"],
                    "bounding_box": compute_bounding_box(c["primary_point"]["lat"], c["primary_point"]["lon"]),
                    "timestamps": p_ts,
                    "values": p_vals,
                    "data_status": "cache",
                },
                "comparison": {
                    "parameter": c["parameter"],
                    "lat": c["comparison_point"]["lat"],
                    "lon": c["comparison_point"]["lon"],
                    "bounding_box": compute_bounding_box(c["comparison_point"]["lat"], c["comparison_point"]["lon"]),
                    "timestamps": c_ts,
                    "values": c_vals,
                    "data_status": "cache",
                },
            }
    return None


def _find_nearest_cached(
    cache: dict[str, Any], parameter: str, lat: float, lon: float, start_year: int, end_year: int
) -> dict[str, Any] | None:
    """Find nearest cached observation for parameter by Haversine distance."""
    param = parameter.upper()
    candidates: list[tuple[float, float, float, list[str], list[float], str]] = []

    for _, entry in cache.get("live_cache", {}).items():
        if entry.get("parameter", "").upper() == param and entry.get("timestamps"):
            e_lat = float(entry["lat"])
            e_lon = float(entry["lon"])
            dist = _haversine_km(lat, lon, e_lat, e_lon)
            candidates.append((dist, e_lat, e_lon, entry["timestamps"], entry["values"], f"cached ({e_lat:.2f}, {e_lon:.2f})"))

    for c in cache.get("cases", []):
        if c.get("parameter", "").upper() == param:
            for pt_key, ser_key in [("primary_point", "primary_series"), ("comparison_point", "comparison_series")]:
                pt = c.get(pt_key, {})
                ser = c.get(ser_key, {})
                if pt and ser.get("timestamps"):
                    e_lat = float(pt["lat"])
                    e_lon = float(pt["lon"])
                    dist = _haversine_km(lat, lon, e_lat, e_lon)
                    candidates.append((dist, e_lat, e_lon, ser["timestamps"], ser["values"], pt.get("name", "cached region")))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])
    dist, _, _, ts_all, vals_all, label = candidates[0]
    ts, vals = _slice_window(ts_all, vals_all, start_year, end_year)
    return {
        "parameter": param,
        "lat": round(lat, 4),
        "lon": round(lon, 4),
        "bounding_box": compute_bounding_box(lat, lon),
        "timestamps": ts,
        "values": vals,
        "data_status": "offline_fallback",
        "fallback_note": f"Offline fallback using nearest cached dataset: {label} ({dist:.0f} km away).",
    }


async def fetch_nasa_monthly(
    lat: float,
    lon: float,
    parameter: str,
    start_year: int = 1990,
    end_year: int = 2025,
) -> dict[str, Any]:
    """
    Fetch monthly NASA POWER observations for (lat, lon, parameter).
    Checks local cache first, queries NASA POWER API (1981-2025) on miss and caches atomically,
    and falls back to nearest cached coordinate if offline or rate-limited.
    """
    param = parameter.upper()
    cache = _load_cache()
    key = _make_cache_key(param, lat, lon)

    if key in cache.get("live_cache", {}):
        entry = cache["live_cache"][key]
        ts, vals = _slice_window(entry["timestamps"], entry["values"], start_year, end_year)
        if len(ts) >= 24:
            return {
                "parameter": param,
                "lat": round(float(lat), 4),
                "lon": round(float(lon), 4),
                "bounding_box": compute_bounding_box(lat, lon),
                "timestamps": ts,
                "values": vals,
                "data_status": "cache",
            }

    for c in cache.get("cases", []):
        if c.get("parameter", "").upper() == param:
            for pt_key, ser_key in [("primary_point", "primary_series"), ("comparison_point", "comparison_series")]:
                pt = c[pt_key]
                if _haversine_km(lat, lon, float(pt["lat"]), float(pt["lon"])) < 5.0:
                    ser = c[ser_key]
                    ts, vals = _slice_window(ser["timestamps"], ser["values"], start_year, end_year)
                    if len(ts) >= 24:
                        return {
                            "parameter": param,
                            "lat": round(float(lat), 4),
                            "lon": round(float(lon), 4),
                            "bounding_box": compute_bounding_box(lat, lon),
                            "timestamps": ts,
                            "values": vals,
                            "data_status": "cache",
                        }

    query_params = {
        "parameters": param,
        "community": "AG",
        "longitude": round(float(lon), 4),
        "latitude": round(float(lat), 4),
        "start": 1981,
        "end": 2025,
        "format": "JSON",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(NASA_POWER_URL, params=query_params)
            resp.raise_for_status()
            payload = resp.json()

        raw_param = payload["properties"]["parameter"][param]
        full_ts, full_vals = _parse_power_monthly_payload(raw_param)

        cache = _load_cache()
        cache["live_cache"][key] = {
            "parameter": param,
            "lat": round(float(lat), 4),
            "lon": round(float(lon), 4),
            "timestamps": full_ts,
            "values": full_vals,
        }
        _save_cache_atomic(cache)

        ts, vals = _slice_window(full_ts, full_vals, start_year, end_year)
        return {
            "parameter": param,
            "lat": round(float(lat), 4),
            "lon": round(float(lon), 4),
            "bounding_box": compute_bounding_box(lat, lon),
            "timestamps": ts,
            "values": vals,
            "data_status": "live",
        }
    except Exception as exc:
        fallback = _find_nearest_cached(cache, param, lat, lon, start_year, end_year)
        if fallback is not None and len(fallback["timestamps"]) >= 24:
            return fallback
        raise RuntimeError(f"NASA POWER API unavailable and no cached fallback found for {param}: {exc}") from exc


def build_partner_deep_links(
    lat: float,
    lon: float,
    parameter: str,
    start_year: int = 1990,
    end_year: int = 2025,
) -> list[dict[str, str]]:
    """Generate coordinate- and window-parameterized links to NASA, NOAA, KNMI, and CSA portals."""
    box = compute_bounding_box(lat, lon)
    bbox_str = f"{box['west']},{box['south']},{box['east']},{box['north']}"
    giovanni_var_map = {
        "PRECTOTCORR": "GPM_3IMERGM_07_precipitation",
        "GWETROOT": "GLDAS_NOAH025_M_2_1_SoilMoi0_100cm_inst",
        "GWETPROF": "MOD13C2_061_CMG_0_05_Deg_Monthly_NDVI",
        "T2M": "M2TMNXSLV_5_12_4_T2M",
        "QV2M": "M2TMNXSLV_5_12_4_QV2M",
        "PS": "M2TMNXSLV_5_12_4_PS",
    }
    g_var = giovanni_var_map.get(parameter.upper(), "M2TMNXSLV_5_12_4_T2M")
    giovanni_url = (
        f"https://giovanni.gsfc.nasa.gov/giovanni/#service=TmAvMp"
        f"&starttime={start_year}-01-01T00:00:00Z&endtime={end_year}-12-31T23:59:59Z"
        f"&bbox={bbox_str}&data={g_var}"
    )
    hydro_url = (
        f"https://disc.gsfc.nasa.gov/information/tools?title=Hydrology%20Time%20Series"
        f"#lat={lat:.2f}&lon={lon:.2f}&start={start_year}-01&end={end_year}-12"
    )

    return [
        {
            "id": "giovanni",
            "agency": "NASA GES DISC",
            "title": "NASA Giovanni Time-Series Portal",
            "category": "NASA Data & Resources",
            "description": f"Launch area-averaged monthly time series for bbox [{bbox_str}] ({g_var}).",
            "url": giovanni_url,
        },
        {
            "id": "hydrology_ts",
            "agency": "NASA GES DISC",
            "title": "Hydrology Time Series (Data Rods)",
            "category": "NASA Data & Resources",
            "description": f"Generate GLDAS/NLDAS soil moisture, runoff, and precipitation rods at ({lat:.2f}°, {lon:.2f}°).",
            "url": hydro_url,
        },
        {
            "id": "appeears",
            "agency": "NASA LP DAAC",
            "title": "NASA AppEEARS Geospatial Extractor",
            "category": "NASA Data & Resources",
            "description": "Access & transform MODIS NDVI, SMAP, and ECOSTRESS point/polygon time series.",
            "url": "https://appeears.earthdatacloud.nasa.gov/",
        },
        {
            "id": "noaa_cdo",
            "agency": "NOAA NCEI",
            "title": "Climate Data Online (CDO)",
            "category": "NASA Data & Resources",
            "description": "Historical global weather station archives (GSOM) & station mapping tool.",
            "url": "https://www.ncei.noaa.gov/cdo-web/",
        },
        {
            "id": "ntrs_seawifs",
            "agency": "NASA NTRS",
            "title": "SeaWiFS Coastal Chlorophyll Time-Series Study (PDF)",
            "category": "NASA Data & Resources",
            "description": "Reference study demonstrating satellite time-series creation and trend significance testing in river plumes.",
            "url": "https://ntrs.nasa.gov/api/citations/20090042747/downloads/20090042747.pdf",
        },
        {
            "id": "knmi_climexp",
            "agency": "KNMI Partner",
            "title": "KNMI Climate Explorer",
            "category": "Space Agency Partner Resources",
            "description": "Web-based climate anomaly, teleconnection correlation, and station analysis tool.",
            "url": "https://climexp.knmi.nl/",
        },
        {
            "id": "stats_methods_medium",
            "agency": "Methodology Guide",
            "title": "Statistical Test Methods for Time-Series Trends",
            "category": "Space Agency Partner Resources",
            "description": "Reference article on Mann-Kendall, Sen's slope, and parametric trend detection.",
            "url": "https://medium.com/@snp.kriss/statistical-test-methods-to-detect-trends-in-time-series-data-b361a0ec530b",
        },
        {
            "id": "statsig_guide",
            "agency": "Methodology Guide",
            "title": "Comprehensive Guide to Statistical Significance",
            "category": "Space Agency Partner Resources",
            "description": "Foundational guide to p-values, confidence intervals, alpha thresholds, and statistical power.",
            "url": "https://www.statsig.com/perspectives/a-comprehensive-guide-to-statistical-significance",
        },
        {
            "id": "csa_rcm",
            "agency": "CSA (Canada)",
            "title": "RADARSAT Constellation Mission (RCM) Open Data",
            "category": "CSA (Canadian Space Agency)",
            "description": "All-weather day/night SAR Earth observation for maritime ice, disaster management, and ecosystems.",
            "url": "https://donnees-data.asc-csa.gc.ca/en/dataset/rcm",
        },
        {
            "id": "csa_geoca",
            "agency": "CSA / Geo.ca",
            "title": "Geo.ca — Canada's Open Geospatial Information",
            "category": "CSA (Canadian Space Agency)",
            "description": "Definitive source for Canadian environmental monitoring, permafrost, and water datasets.",
            "url": "https://geo.ca/",
        },
        {
            "id": "csa_swot",
            "agency": "NASA / CNES / CSA",
            "title": "SWOT Mission (Surface Water & Ocean Topography)",
            "category": "CSA (Canadian Space Agency)",
            "description": "Surveys 90% of Earth's surface water, measuring elevation changes in rivers, lakes, and reservoirs.",
            "url": "https://www.asc-csa.gc.ca/eng/satellites/swot/",
        },
        {
            "id": "csa_ecosystems",
            "agency": "CSA (Canada)",
            "title": "Monitoring & Protecting Our Ecosystems from Space",
            "category": "CSA (Canadian Space Agency)",
            "description": "How satellite observations track deforestation, wetlands, agriculture, and coastal shifts.",
            "url": "https://www.asc-csa.gc.ca/eng/satellites/everyday-lives/monitoring-and-protecting-our-ecosystems-from-space.asp",
        },
        {
            "id": "csa_sar_tutorial",
            "agency": "CSA GitHub",
            "title": "Synthetic Aperture Radar (SAR) Python & QGIS Tutorial",
            "category": "CSA (Canadian Space Agency)",
            "description": "Practical Python workflows for accessing, processing, and visualizing RADARSAT SAR imagery.",
            "url": "https://github.com/asc-csa/Synthetic_Aperture_Radar_Tutorial",
        },
    ]


async def fetch_partner_intel(
    lat: float,
    lon: float,
    parameter: str,
    start_year: int = 1990,
    end_year: int = 2025,
) -> dict[str, Any]:
    """
    Query live public endpoints from NASA CMR (SWOT/SeaWiFS/MODIS/GPM), NASA AppEEARS,
    CSA Geo.ca / MSC GeoMet (Canadian climate & hydrometric stations), and NOAA CDO.
    Gracefully degrades if any individual external service times out.
    """
    global _APPEEARS_CACHE
    box = compute_bounding_box(lat, lon)
    bbox_str = f"{box['west']},{box['south']},{box['east']},{box['north']}"
    search_box = f"{round(lon - 2.5, 2)},{round(lat - 2.5, 2)},{round(lon + 2.5, 2)},{round(lat + 2.5, 2)}"

    cmr_collections: list[dict[str, str]] = []
    appeears_products: list[dict[str, str]] = []
    csa_stations: list[dict[str, Any]] = []
    noaa_status = "Set NOAA_CDO_TOKEN in env for live NCEI GSOM station queries (portal link active)."

    async with httpx.AsyncClient(timeout=4.5, follow_redirects=True) as client:
        # 1. NASA CMR Live Satellite Collections (including SWOT & SeaWiFS)
        cmr_task = client.get(
            NASA_CMR_COLLECTIONS_URL,
            params={"bounding_box": bbox_str, "page_size": 5},
        )
        swot_task = client.get(
            NASA_CMR_COLLECTIONS_URL,
            params={"keyword": "SWOT", "bounding_box": bbox_str, "page_size": 2},
        )
        # 2. CSA GeoMet Hydrometric & Climate stations in or near bounding box
        csa_hydro_task = client.get(
            CSA_GEOMET_HYDRO_URL,
            params={"f": "json", "bbox": search_box, "limit": 3},
        )
        csa_clim_task = client.get(
            CSA_GEOMET_CLIMATE_URL,
            params={"f": "json", "bbox": search_box, "limit": 3},
        )
        appeears_task = (
            client.get(NASA_APPEEARS_PRODUCTS_URL) if _APPEEARS_CACHE is None else None
        )

        results = await asyncio.gather(
            cmr_task,
            swot_task,
            csa_hydro_task,
            csa_clim_task,
            *( [appeears_task] if appeears_task is not None else [] ),
            return_exceptions=True,
        )

        # Parse CMR
        for res in (results[0], results[1]):
            if isinstance(res, httpx.Response) and res.status_code == 200:
                entries = res.json().get("feed", {}).get("entry", [])
                for e in entries:
                    short_name = e.get("short_name") or e.get("dataset_id", "NASA Dataset")
                    if not any(c["short_name"] == short_name for c in cmr_collections):
                        cmr_collections.append({
                            "short_name": short_name,
                            "title": e.get("title", short_name),
                            "data_center": e.get("data_center", "NASA EOSDIS"),
                            "summary": (e.get("summary") or "")[:160],
                        })

        # Parse CSA GeoMet Hydrometric & Climate features
        for kind, res in [("SWOT / Hydrometric Gauge", results[2]), ("CSA / MSC Climate Station", results[3])]:
            if isinstance(res, httpx.Response) and res.status_code == 200:
                feats = res.json().get("features", [])
                for f in feats[:2]:
                    props = f.get("properties", {})
                    st_name = (
                        props.get("STATION_NAME")
                        or props.get("CLIMATE_IDENTIFIER")
                        or props.get("STATION_NUMBER")
                        or "Canadian Station"
                    )
                    csa_stations.append({
                        "type": kind,
                        "station_name": str(st_name),
                        "station_id": str(props.get("STATION_NUMBER") or props.get("CLIMATE_IDENTIFIER") or ""),
                        "province": str(props.get("PROVINCE_CODE") or props.get("PROV_STATE_TERR_CODE") or "CA"),
                        "sample_date": str(props.get("LOCAL_DATE") or props.get("DATE") or ""),
                        "sample_metric": (
                            f"Level: {props.get('MONTHLY_MEAN_WATER_LEVEL')} m / Flow: {props.get('MONTHLY_MEAN_DISCHARGE')} m³/s"
                            if "Hydrometric" in kind
                            else f"Mean Temp: {props.get('MEAN_TEMPERATURE')} °C / Precip: {props.get('TOTAL_PRECIPITATION')} mm"
                        ),
                    })

        # Parse AppEEARS Catalog
        if appeears_task is not None and len(results) >= 5 and isinstance(results[4], httpx.Response):
            if results[4].status_code == 200 and isinstance(results[4].json(), list):
                _APPEEARS_CACHE = results[4].json()

        # Optional NOAA CDO v2 check if token present
        noaa_token = os.environ.get("NOAA_CDO_TOKEN", "").strip()
        if noaa_token:
            try:
                n_resp = await client.get(
                    NOAA_CDO_STATIONS_URL,
                    headers={"token": noaa_token},
                    params={"extent": f"{box['south']},{box['west']},{box['north']},{box['east']}", "limit": 3},
                )
                if n_resp.status_code == 200:
                    st_list = n_resp.json().get("results", [])
                    noaa_status = f"NOAA CDO Live: {len(st_list)} stations matched in grid cell."
            except Exception:
                noaa_status = "NOAA CDO token configured (station lookup fallback active)."

    # Filter AppEEARS catalog for relevant Earth observation products
    if _APPEEARS_CACHE:
        keywords = ("MOD13", "MOD11", "MOD16", "SPL3", "GPM", "SRTM", "ECO")
        for prod in _APPEEARS_CACHE:
            p_name = str(prod.get("Product", ""))
            if any(k in p_name for k in keywords):
                appeears_products.append({
                    "product_id": f"{p_name}.{prod.get('Version', '')}".strip("."),
                    "platform": str(prod.get("Platform", "NASA Satellite")),
                    "description": str(prod.get("Description", "")),
                    "resolution": str(prod.get("Resolution", "")),
                })
                if len(appeears_products) >= 5:
                    break

    if not appeears_products:
        appeears_products = [
            {
                "product_id": "MOD13A3.061",
                "platform": "Terra MODIS",
                "description": "Vegetation Indices Monthly L3 Global 1km SIN Grid (NDVI / EVI)",
                "resolution": "1000m",
            },
            {
                "product_id": "SPL3SMP_E.006",
                "platform": "SMAP",
                "description": "SMAP Enhanced L3 Radiometer Global Daily 9 km Soil Moisture",
                "resolution": "9000m",
            },
        ]

    if not cmr_collections:
        cmr_collections = [
            {
                "short_name": "SWOT_L2_HR_RiverSP_2.0",
                "title": "SWOT Level 2 River Single-Pass Vector Water Surface Elevation",
                "data_center": "NASA PO.DAAC / CSA / CNES",
                "summary": "High-resolution water surface elevation, slope, and discharge from the SWOT satellite.",
            },
            {
                "short_name": "SEAWIFS_L3m_CHL",
                "title": "SeaWiFS Level-3 Monthly Mapped Chlorophyll-a Concentration",
                "data_center": "NASA OB.DAAC",
                "summary": "Global and coastal river-plume ocean color chlorophyll time series (1997-2010).",
            },
        ]

    return {
        "coordinates": {"lat": lat, "lon": lon, "bounding_box": box},
        "cmr_collections": cmr_collections[:6],
        "appeears_products": appeears_products[:5],
        "csa_geomet_stations": csa_stations,
        "noaa_cdo_status": noaa_status,
        "deep_links": build_partner_deep_links(lat, lon, parameter, start_year, end_year),
    }


def parse_external_timeseries(
    raw_text: str,
    source_hint: str = "auto",
) -> tuple[list[str], list[float], dict[str, str]]:
    """
    Parse external monthly time series exported from:
    - NASA Giovanni CSV
    - GES DISC Hydrology Time Series ASCII/CSV
    - NASA AppEEARS Point CSV
    - KNMI Climate Explorer 13-column (.dat / .txt) or 2-column series
    - NOAA Climate Data Online (CDO) CSV
    Returns (timestamps_yyyy_mm, values, metadata_dict).
    """
    text = raw_text.strip()
    if not text:
        raise ValueError("Uploaded time-series file is empty.")

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    detected_source = source_hint if source_hint != "auto" else "External Satellite/Station Series"
    detected_param = "CUSTOM_IMPORT"
    detected_unit = "units"

    # Check if KNMI Climate Explorer 13-column format (YYYY val1 val2 ... val12)
    knmi_records: dict[str, float] = {}
    knmi_rows_matched = 0
    for ln in lines:
        if ln.startswith("#") or ln.startswith("%"):
            if "KNMI" in ln.upper():
                detected_source = "KNMI Climate Explorer"
            continue
        parts = ln.split()
        if len(parts) == 13 and re.match(r"^(18|19|20)\d{2}$", parts[0]):
            try:
                yr = int(parts[0])
                month_vals = [float(x) for x in parts[1:]]
                knmi_rows_matched += 1
                for m_idx, mv in enumerate(month_vals, start=1):
                    if math.isfinite(mv) and mv > -990.0 and abs(mv - 3e33) > 1e20:
                        knmi_records[f"{yr:04d}-{m_idx:02d}"] = mv
            except ValueError:
                pass

    if knmi_rows_matched >= 2 and len(knmi_records) >= 24:
        sorted_ts = sorted(knmi_records.keys())
        return (
            sorted_ts,
            [round(knmi_records[k], 4) for k in sorted_ts],
            {
                "parameter_code": "KNMI_SERIES",
                "parameter_name": "KNMI Climate Explorer Series",
                "unit": detected_unit,
                "mission_source": "KNMI Climate Explorer (Royal Netherlands Meteorological Institute)",
            },
        )

    # Otherwise parse Giovanni / GES DISC Hydrology / AppEEARS / NOAA CDO CSV or whitespace lines
    monthly_buckets: dict[str, list[float]] = {}
    date_pattern = re.compile(r"^((?:18|19|20)\d{2})[-/]?([01]\d)(?:[-/]\d{1,2})?")

    for ln in lines:
        if ln.startswith("#"):
            if "GIOVANNI" in ln.upper():
                detected_source = "NASA Giovanni"
            elif "HYDRO" in ln.upper() or "GLDAS" in ln.upper():
                detected_source = "NASA GES DISC Hydrology Time Series"
            continue
        if "giovanni" in ln.lower():
            detected_source = "NASA Giovanni"
        if "appeears" in ln.lower() or "mod13" in ln.lower():
            detected_source = "NASA AppEEARS"

        # Try CSV splitting first, then whitespace
        row = next(csv.reader(io.StringIO(ln))) if ("," in ln or "\t" in ln) else ln.split()
        if len(row) < 2:
            continue

        # Locate date cell and last valid numeric value cell
        ts_ym: str | None = None
        val_num: float | None = None
        for cell in row:
            c_str = cell.strip().strip('"')
            m = date_pattern.match(c_str)
            if m and ts_ym is None:
                yr_i, mo_i = int(m.group(1)), int(m.group(2))
                if 1 <= mo_i <= 12:
                    ts_ym = f"{yr_i:04d}-{mo_i:02d}"
                    continue
            if ts_ym is not None:
                try:
                    fv = float(c_str)
                    if math.isfinite(fv) and fv > -990.0:
                        val_num = fv
                except ValueError:
                    continue

        if ts_ym is not None and val_num is not None:
            monthly_buckets.setdefault(ts_ym, []).append(val_num)

    if len(monthly_buckets) < 24:
        raise ValueError(
            f"Parsed {len(monthly_buckets)} valid monthly rows; at least 24 months (YYYY-MM, value) are required for STL decomposition."
        )

    sorted_ts = sorted(monthly_buckets.keys())
    avg_vals = [round(sum(monthly_buckets[t]) / len(monthly_buckets[t]), 4) for t in sorted_ts]
    return (
        sorted_ts,
        avg_vals,
        {
            "parameter_code": detected_param,
            "parameter_name": f"Imported {detected_source} Series",
            "unit": detected_unit,
            "mission_source": detected_source,
        },
    )


async def seed_preset_cases() -> dict[str, Any]:
    """Fetch real 1981-2025 NASA POWER data for all 6 Detective Case Files and persist to cases_cache.json."""
    cache = _load_cache()
    seeded_cases: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=15.0) as client:
        for spec in PRESET_CASE_SPECS:
            param = spec["parameter"]
            p_pt = spec["primary_point"]
            c_pt = spec["comparison_point"]

            p_resp, c_resp = await asyncio.gather(
                client.get(
                    NASA_POWER_URL,
                    params={
                        "parameters": param,
                        "community": "AG",
                        "longitude": p_pt["lon"],
                        "latitude": p_pt["lat"],
                        "start": 1981,
                        "end": 2025,
                        "format": "JSON",
                    },
                ),
                client.get(
                    NASA_POWER_URL,
                    params={
                        "parameters": param,
                        "community": "AG",
                        "longitude": c_pt["lon"],
                        "latitude": c_pt["lat"],
                        "start": 1981,
                        "end": 2025,
                        "format": "JSON",
                    },
                ),
            )
            p_resp.raise_for_status()
            c_resp.raise_for_status()

            p_ts, p_vals = _parse_power_monthly_payload(p_resp.json()["properties"]["parameter"][param])
            c_ts, c_vals = _parse_power_monthly_payload(c_resp.json()["properties"]["parameter"][param])

            case_entry = {
                **spec,
                "primary_series": {"timestamps": p_ts, "values": p_vals},
                "comparison_series": {"timestamps": c_ts, "values": c_vals},
                "extra_series": None,
            }
            seeded_cases.append(case_entry)

            cache["live_cache"][_make_cache_key(param, p_pt["lat"], p_pt["lon"])] = {
                "parameter": param,
                "lat": p_pt["lat"],
                "lon": p_pt["lon"],
                "timestamps": p_ts,
                "values": p_vals,
            }
            cache["live_cache"][_make_cache_key(param, c_pt["lat"], c_pt["lon"])] = {
                "parameter": param,
                "lat": c_pt["lat"],
                "lon": c_pt["lon"],
                "timestamps": c_ts,
                "values": c_vals,
            }

    cache["cases"] = seeded_cases
    _save_cache_atomic(cache)
    return cache


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed TerraShift NASA POWER case cache.")
    parser.add_argument("--seed", action="store_true", help="Fetch and cache the 6 preset Detective Case Files.")
    args = parser.parse_args()
    if args.seed:
        result = asyncio.run(seed_preset_cases())
        print(f"Seeded {len(result['cases'])} Detective Case Files into {CACHE_FILE}")
