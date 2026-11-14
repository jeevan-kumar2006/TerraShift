"""Hybrid NASA POWER monthly data fetcher, parameter registry, and local cache manager."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pandas as pd

CACHE_FILE = Path(__file__).resolve().parent / "cases_cache.json"
NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/monthly/point"

PARAMETER_METADATA: dict[str, dict[str, str]] = {
    "PRECTOTCORR": {
        "parameter_code": "PRECTOTCORR",
        "parameter_name": "Corrected Monthly Precipitation",
        "unit": "mm/day",
        "mission_source": "NASA GPM / MERRA-2 Assimilation",
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
        "mission_source": "NASA GLDAS / SMAP Assimilation",
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
        "mission_source": "NASA MODIS NDVI / GLDAS Assimilation",
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
        "mission_source": "NASA MERRA-2 / AIRS Reanalysis",
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
        "mission_source": "NASA MERRA-2 Surface Meteorology",
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
        "mission_label": "GPM / MERRA-2",
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
        "mission_label": "GLDAS / SMAP",
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
        "mission_label": "MERRA-2 / AIRS",
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
        "mission_label": "MODIS NDVI / GLDAS",
        "primary_point": {"name": "SE Amazon Deforestation Arc", "lat": -12.0, "lon": -55.0},
        "comparison_point": {"name": "Central Amazon Core", "lat": -2.0, "lon": -64.0},
        "default_window": [1990, 2025],
        "data_source": "NASA POWER (MERRA-2 Soil Profile / Canopy Context)",
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

    # Trim trailing unpublished months (all NaNs at tail)
    while records and math.isnan(records[-1][1]):
        records.pop()
    while records and math.isnan(records[0][1]):
        records.pop(0)

    if not records:
        raise ValueError("NASA POWER returned no valid monthly observations for this coordinate.")

    ts_list = [r[0] for r in records]
    vals = pd.Series([r[1] for r in records], dtype=float).interpolate(method="linear", limit_direction="both")
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
            "mission_source": "NASA POWER / MERRA-2",
            "resolution": "0.5° × 0.625° Grid",
            "plain_definition": f"Monthly NASA Earth observation time series for {code}.",
            "question": f"How is {code} changing?",
            "positive_label": "Increasing",
            "negative_label": "Decreasing",
        }
    return PARAMETER_METADATA[code]


def list_preset_cases() -> list[dict[str, Any]]:
    """Return lightweight metadata for the 4 curated Detective Case Files."""
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

    for key, entry in cache.get("live_cache", {}).items():
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
    dist, e_lat, e_lon, ts_all, vals_all, label = candidates[0]
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

    # 1. Exact live_cache hit
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

    # 2. Check if matching a preset case coordinate closely (< 5 km)
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

    # 3. Query live NASA POWER Monthly API for full 1981-2025 baseline so slider moves are instant
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

        # Persist full 1981-2025 series to local JSON cache atomically
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


async def seed_preset_cases() -> dict[str, Any]:
    """Fetch real 1981-2025 NASA POWER data for all 4 Detective Case Files and persist to cases_cache.json."""
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

            # Also populate live_cache for direct coordinate lookups
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
    parser.add_argument("--seed", action="store_true", help="Fetch and cache the 4 preset Detective Case Files.")
    args = parser.parse_args()
    if args.seed:
        result = asyncio.run(seed_preset_cases())
        print(f"Seeded {len(result['cases'])} Detective Case Files into {CACHE_FILE}")
