"""Hybrid NASA POWER, NASA CMR, AppEEARS & Giovanni India-exclusive Earth observation service."""

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

from config import (
    CACHE_FILE,
    INDIA_BOUNDS,
    MAX_FALLBACK_RADIUS_KM,
    NASA_APPEEARS_PRODUCTS_URL,
    NASA_CMR_COLLECTIONS_URL,
    NASA_POWER_POINT_URL as NASA_POWER_URL,
)
from acquisition.dataset_registry import TREND_VARIABLE_REGISTRY
from acquisition.spatial_subset import (
    compute_area_weighted_series,
    compute_terrain_quality_flags,
    sample_polygon_grid_points,
)


# Parameter-to-NASA POWER community routing
POWER_COMMUNITY_MAP: dict[str, str] = {
    "T2M": "AG",
    "PRECTOTCORR": "AG",
    "GWETROOT": "AG",
    "GWETPROF": "AG",
    "QV2M": "AG",
    "PS": "AG",
}


def is_within_india_bounds(lat: float, lon: float) -> bool:
    """Return True if coordinates fall within India's geographical domain (6.0N-37.5N, 68.0E-97.5E)."""
    return (
        INDIA_BOUNDS["lat_min"] <= float(lat) <= INDIA_BOUNDS["lat_max"]
        and INDIA_BOUNDS["lon_min"] <= float(lon) <= INDIA_BOUNDS["lon_max"]
    )

# In-memory cache for AppEEARS catalog so repeated lookups are instant
_APPEEARS_CACHE: list[dict[str, Any]] | None = None

PARAMETER_METADATA: dict[str, dict[str, str]] = {
    "PRECTOTCORR": {
        "parameter_code": "PRECTOTCORR",
        "parameter_name": "Corrected Monthly Precipitation",
        "unit": "mm/day",
        "mission_source": "NASA POWER — MERRA-2 Assimilated Precipitation (M2TMNXFLX)",
        "collection": "MERRA-2 M2TMNXFLX (Observation-Corrected Reanalysis)",
        "data_type": "reanalysis_assimilated",
        "temporal_resolution": "Monthly",
        "resolution": "0.5° × 0.625° MERRA-2 Grid",
        "plain_definition": "Bias-corrected monthly average daily precipitation rate (rain and snow water equivalent) from NASA GMAO MERRA-2 assimilation.",
        "question": "Where is rainfall accelerating?",
        "positive_label": "Wetting Trend",
        "negative_label": "Drying Trend",
    },
    "GWETROOT": {
        "parameter_code": "GWETROOT",
        "parameter_name": "Root-Zone Soil Wetness",
        "unit": "fraction (0–1)",
        "mission_source": "NASA POWER — MERRA-2 Land Surface Model (M2TMNXLND)",
        "collection": "MERRA-2 M2TMNXLND (Model-Derived Land Hydrology)",
        "data_type": "model_derived",
        "temporal_resolution": "Monthly",
        "resolution": "0.5° × 0.625° MERRA-2 Grid",
        "plain_definition": "Model-assimilated root-zone soil wetness fraction (0–1) in the top 100 cm from the MERRA-2 land surface model (cross-referenced with GLDAS/SMAP).",
        "question": "Where is drought worsening?",
        "positive_label": "Soil Wetting",
        "negative_label": "Soil Drying",
    },
    "GWETPROF": {
        "parameter_code": "GWETPROF",
        "parameter_name": "Total Profile Soil Wetness",
        "unit": "fraction (0–1)",
        "mission_source": "NASA POWER — MERRA-2 Land Surface Model (M2TMNXLND)",
        "collection": "MERRA-2 M2TMNXLND (Model-Derived Profile Soil Wetness)",
        "data_type": "model_derived",
        "temporal_resolution": "Monthly",
        "resolution": "0.5° × 0.625° MERRA-2 Grid",
        "plain_definition": "Model-assimilated total profile soil wetness fraction (0–1) from surface to bedrock (root water-supply proxy; distinct from satellite MODIS NDVI reflectance).",
        "question": "Where are forest canopies drying?",
        "positive_label": "Moisture Recovery",
        "negative_label": "Canopy Drying",
    },
    "T2M": {
        "parameter_code": "T2M",
        "parameter_name": "2-Meter Surface Air Temperature",
        "unit": "°C",
        "mission_source": "NASA POWER — MERRA-2 Atmospheric Reanalysis (M2TMNXSLV)",
        "collection": "MERRA-2 M2TMNXSLV (Atmospheric Reanalysis)",
        "data_type": "reanalysis",
        "temporal_resolution": "Monthly",
        "resolution": "0.5° × 0.625° MERRA-2 Grid",
        "plain_definition": "Monthly mean air temperature at 2 meters above the Earth's surface from NASA GMAO MERRA-2 reanalysis.",
        "question": "Where is warming fastest?",
        "positive_label": "Warming Trend",
        "negative_label": "Cooling Trend",
    },
    "QV2M": {
        "parameter_code": "QV2M",
        "parameter_name": "2-Meter Specific Humidity",
        "unit": "g/kg",
        "mission_source": "NASA POWER — MERRA-2 Atmospheric Reanalysis (M2TMNXSLV)",
        "collection": "MERRA-2 M2TMNXSLV (Atmospheric Reanalysis)",
        "data_type": "reanalysis",
        "temporal_resolution": "Monthly",
        "resolution": "0.5° × 0.625° MERRA-2 Grid",
        "plain_definition": "Monthly mean mass of water vapor per kilogram of air at 2 meters from MERRA-2 reanalysis, driving heat-stress and moisture availability.",
        "question": "Where is atmospheric humidity rising?",
        "positive_label": "Humidifying",
        "negative_label": "Drying Air",
    },
    "PS": {
        "parameter_code": "PS",
        "parameter_name": "Surface Atmospheric Pressure",
        "unit": "kPa",
        "mission_source": "NASA POWER — MERRA-2 Atmospheric Reanalysis (M2TMNXSLV)",
        "collection": "MERRA-2 M2TMNXSLV (Atmospheric Reanalysis)",
        "data_type": "reanalysis",
        "temporal_resolution": "Monthly",
        "resolution": "0.5° × 0.625° MERRA-2 Grid",
        "plain_definition": "Monthly mean atmospheric surface pressure from MERRA-2 reanalysis reflecting storm tracks and circulation cells.",
        "question": "Where are pressure systems shifting?",
        "positive_label": "Rising Pressure",
        "negative_label": "Falling Pressure",
    },
}

PRESET_CASE_SPECS: list[dict[str, Any]] = [
    {
        "case_id": "case_1_monsoon",
        "title": "Case 1: Western Ghats Orographic Monsoon vs Rain-Shadow Deccan",
        "short_title": "Western Ghats vs Deccan",
        "mechanism_teaser": "Arabian Sea Southwest Monsoon moisture uplift along the Western Ghats contrasts sharply with semi-arid rain-shadow conditions in Marathwada (Deccan Plateau).",
        "parameter": "PRECTOTCORR",
        "mission_label": "NASA POWER (MERRA-2) · Ref: GPM IMERG / IMD",
        "primary_point": {"name": "Thrissur / Kerala Coast (Western Ghats)", "lat": 10.52, "lon": 76.21},
        "comparison_point": {"name": "Aurangabad / Marathwada (Deccan)", "lat": 19.88, "lon": 75.34},
        "default_window": [1990, 2025],
        "data_source": "NASA POWER (MERRA-2 Assimilated Precipitation; GPM IMERG / IMD contextual ref)",
    },
    {
        "case_id": "case_2_himalaya",
        "title": "Case 2: Western Himalayan Warming vs Coromandel Coast",
        "short_title": "Himalaya vs Coast",
        "mechanism_teaser": "High-elevation snow-albedo feedbacks in Ladakh/Western Himalaya are compared against maritime thermal buffering along the Coromandel Coast.",
        "parameter": "T2M",
        "mission_label": "NASA POWER (MERRA-2) · Ref: MODIS LST / AIRS",
        "primary_point": {"name": "Leh / Ladakh (Western Himalaya)", "lat": 34.15, "lon": 77.58},
        "comparison_point": {"name": "Chennai / Coromandel Coast", "lat": 13.08, "lon": 80.27},
        "default_window": [1990, 2025],
        "data_source": "NASA POWER (MERRA-2 M2TMNXSLV 2m Air Temp; MODIS/AIRS contextual ref)",
    },
    {
        "case_id": "case_3_igp_thar",
        "title": "Case 3: Indo-Gangetic Plains vs Thar Desert Root-Zone Moisture",
        "short_title": "IGP vs Thar Moisture",
        "mechanism_teaser": "Intensive alluvial cultivation in the central Indo-Gangetic Plains contrasts with hyper-arid moisture deficits across the Thar Desert.",
        "parameter": "GWETROOT",
        "mission_label": "NASA POWER (MERRA-2 Land) · Ref: SMAP / GLDAS / GRACE",
        "primary_point": {"name": "Lucknow / Central Indo-Gangetic Plain", "lat": 26.85, "lon": 80.95},
        "comparison_point": {"name": "Jaisalmer / Thar Desert", "lat": 26.91, "lon": 70.91},
        "default_window": [1990, 2025],
        "data_source": "NASA POWER (MERRA-2 M2TMNXLND Root-Zone Wetness; SMAP/GLDAS contextual ref)",
    },
    {
        "case_id": "case_4_northeast",
        "title": "Case 4: Northeastern Monsoon Belt vs Central Indian Plateau",
        "short_title": "Northeast vs Central Plateau",
        "mechanism_teaser": "Bay of Bengal moisture convergence over the Meghalaya Hills contrasts with continental convective rainfall variability across the Central Indian Plateau.",
        "parameter": "PRECTOTCORR",
        "mission_label": "NASA POWER (MERRA-2) · Ref: GPM / TRMM / IMD",
        "primary_point": {"name": "Shillong / Meghalaya (Northeast India)", "lat": 25.57, "lon": 91.89},
        "comparison_point": {"name": "Nagpur / Central Indian Plateau", "lat": 21.15, "lon": 79.09},
        "default_window": [1990, 2025],
        "data_source": "NASA POWER (MERRA-2 Precip; GPM IMERG / IMD Monsoon contextual ref)",
    },
    {
        "case_id": "case_5_heat_belt",
        "title": "Case 5: Vidarbha Interior Heat Belt vs Eastern Ghats Coast",
        "short_title": "Vidarbha vs Eastern Ghats",
        "mechanism_teaser": "Pre-monsoon continental heating across Vidarbha and central India is contrasted with Bay of Bengal coastal moderation along Odisha and the Eastern Ghats.",
        "parameter": "T2M",
        "mission_label": "NASA POWER (MERRA-2) · Ref: MODIS Terra / ECOSTRESS",
        "primary_point": {"name": "Akola / Vidarbha (Central-Deccan)", "lat": 20.70, "lon": 77.00},
        "comparison_point": {"name": "Bhubaneswar / Eastern Ghats Coast", "lat": 20.30, "lon": 85.82},
        "default_window": [1990, 2025],
        "data_source": "NASA POWER (MERRA-2 M2TMNXSLV 2m Air Temp; MODIS LST contextual ref)",
    },
    {
        "case_id": "case_6_delta_basin",
        "title": "Case 6: Sundarbans Delta vs Upper Ganga-Indus Agricultural Basin",
        "short_title": "Sundarbans vs Punjab Basin",
        "mechanism_teaser": "Deltaic profile soil moisture dynamics in the Sundarbans are compared against irrigated alluvial plains in the upper Indus-Ganga agricultural belt.",
        "parameter": "GWETPROF",
        "mission_label": "NASA POWER (MERRA-2 Land) · Ref: GRACE-FO / ISRO MOSDAC",
        "primary_point": {"name": "Sundarbans / Lower Bengal Delta", "lat": 22.00, "lon": 88.80},
        "comparison_point": {"name": "Ludhiana / Upper Indus-Ganga Basin", "lat": 30.90, "lon": 75.85},
        "default_window": [1990, 2025],
        "data_source": "NASA POWER (MERRA-2 M2TMNXLND Profile Wetness; GRACE-FO/MOSDAC contextual ref)",
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


def validate_coordinates(lat: float, lon: float) -> tuple[float, float]:
    """Validate geographic latitude/longitude bounds."""
    lat_f = float(lat)
    lon_f = float(lon)
    if not math.isfinite(lat_f) or not (-90.0 <= lat_f <= 90.0):
        raise ValueError(f"Invalid latitude {lat}: must be between -90 and 90 degrees.")
    if not math.isfinite(lon_f) or not (-180.0 <= lon_f <= 180.0):
        raise ValueError(f"Invalid longitude {lon}: must be between -180 and 180 degrees.")
    return lat_f, lon_f


def _parse_power_monthly_payload(raw_param_dict: dict[str, Any]) -> tuple[list[str], list[float | None]]:
    """Strip ANN/13 keys, parse YYYYMM into YYYY-MM, trim leading/trailing missing values, and preserve interior gaps."""
    records: list[tuple[str, float | None]] = []
    for k in sorted(raw_param_dict.keys()):
        if not isinstance(k, str) or len(k) != 6 or k.endswith("13"):
            continue
        month_num = int(k[4:6])
        if month_num < 1 or month_num > 12:
            continue
        ts = f"{k[:4]}-{k[4:6]}"
        val = raw_param_dict[k]
        if val is None:
            fv: float | None = None
        else:
            num = float(val)
            if not math.isfinite(num) or num <= -990.0:
                fv = None
            else:
                fv = round(num, 4)
        records.append((ts, fv))

    while records and records[-1][1] is None:
        records.pop()
    while records and records[0][1] is None:
        records.pop(0)

    if not records:
        raise ValueError("NASA POWER returned no valid monthly observations for this coordinate.")

    return [r[0] for r in records], [r[1] for r in records]


def _slice_window(
    timestamps: list[str], values: list[float | None], start_year: int, end_year: int
) -> tuple[list[str], list[float | None]]:
    sliced_ts: list[str] = []
    sliced_vals: list[float | None] = []
    for ts, val in zip(timestamps, values):
        yr = int(ts[:4])
        if start_year <= yr <= end_year:
            sliced_ts.append(ts)
            sliced_vals.append(float(val) if val is not None else None)
    return sliced_ts, sliced_vals


def get_parameter_metadata(parameter: str) -> dict[str, str]:
    """Retrieve student-friendly metadata for a NASA POWER or satellite parameter code."""
    raw = parameter.strip()
    if raw in TREND_VARIABLE_REGISTRY:
        spec = TREND_VARIABLE_REGISTRY[raw]
        return {k: str(v) for k, v in spec.items() if isinstance(v, (str, int, float))}
    for k, spec in TREND_VARIABLE_REGISTRY.items():
        if k.upper() == raw.upper():
            return {sk: str(sv) for sk, sv in spec.items() if isinstance(sv, (str, int, float))}
    code = raw.upper()
    if code not in PARAMETER_METADATA:
        return {
            "parameter_code": code,
            "parameter_name": code,
            "unit": "units",
            "mission_source": "NASA Earth Observation",
            "source_type": "external",
            "source_badge": "External / Imported Series",
            "collection": "External / Custom Series",
            "data_type": "external",
            "temporal_resolution": "Monthly",
            "resolution": "0.5° × 0.625° Grid / Point",
            "plain_definition": f"Monthly Earth observation time series for {code}.",
            "question": f"How is {code} changing?",
            "positive_label": "Increasing",
            "negative_label": "Decreasing",
        }
    meta = dict(PARAMETER_METADATA[code])
    meta.setdefault("source_type", "model/reanalysis")
    meta.setdefault("source_badge", "Model: NASA POWER / MERRA-2")
    return meta


async def fetch_region_power_monthly(
    region_id: str,
    parameter: str = "T2M",
    start_year: int = 1990,
    end_year: int = 2025,
) -> dict[str, Any]:
    """
    Mask a regular 0.5-deg grid with the India state/district polygon, sample interior
    grid points (never centroid-only when multi-cell coverage exists), fetch NASA POWER
    monthly series concurrently, and compute a cos(latitude) area-weighted mean.
    """
    grid_info = sample_polygon_grid_points(region_id, resolution_deg=0.5, min_cells=3, max_api_points=9)
    sampled = grid_info["sampled_points"]
    region_meta = grid_info["region_meta"]

    sem = asyncio.Semaphore(5)

    async def _fetch_one(pt: dict[str, float]) -> dict[str, Any] | None:
        async with sem:
            try:
                res = await fetch_nasa_monthly(
                    pt["lat"],
                    pt["lon"],
                    parameter=parameter,
                    start_year=start_year,
                    end_year=end_year,
                )
                return {
                    "lat": pt["lat"],
                    "lon": pt["lon"],
                    "timestamps": res["timestamps"],
                    "values": res["values"],
                    "data_status": res.get("data_status", "live"),
                    "provenance": res.get("provenance"),
                }
            except Exception:
                return None

    fetched = await asyncio.gather(*[_fetch_one(pt) for pt in sampled])
    valid_cells = [c for c in fetched if c is not None and c.get("timestamps")]
    if not valid_cells:
        raise RuntimeError(
            f"Unable to retrieve NASA POWER grid cells for region '{region_meta['region_name']}'."
        )

    agg = compute_area_weighted_series(valid_cells)
    valid_vals = [v for v in agg["values"] if v is not None]
    mean_val = float(sum(valid_vals) / len(valid_vals)) if valid_vals else None

    q_flags = compute_terrain_quality_flags(
        geom=grid_info["geom"],
        mean_t2m_c=mean_val if parameter.upper() == "T2M" else None,
        mean_precip_mm_day=mean_val if parameter.upper() == "PRECTOTCORR" else None,
    )
    if grid_info["low_cell_count_warning"]:
        q_flags.append({
            "flag": "low_grid_cell_count",
            "severity": "warning",
            "grid_cells_used": grid_info["grid_cells_used"],
            "message": grid_info["low_cell_count_warning"],
        })

    statuses = {c.get("data_status", "live") for c in valid_cells}
    agg_status = "live" if "live" in statuses else ("cache" if "cache" in statuses else "offline_fallback")

    return {
        "parameter": parameter.upper(),
        "region_id": region_meta["region_id"],
        "region_name": region_meta["region_name"],
        "region_level": region_meta.get("region_level", "state"),
        "lat": round(float(grid_info["geom"].centroid.y), 4),
        "lon": round(float(grid_info["geom"].centroid.x), 4),
        "bounding_box": grid_info["bbox"],
        "timestamps": agg["timestamps"],
        "values": agg["values"],
        "data_status": agg_status,
        "dataset_tag": "live" if agg_status == "live" else "cached",
        "region_coverage": {
            "grid_cells_used": grid_info["grid_cells_used"],
            "sampled_cells_count": len(valid_cells),
            "area_covered_pct": grid_info["area_covered_pct"],
            "weighting_method": agg["weighting_method"],
            "low_cell_count_warning": grid_info["low_cell_count_warning"],
        },
        "quality_flags": q_flags,
        "provenance": build_series_provenance(
            parameter=parameter.upper(),
            requested_lat=round(float(grid_info["geom"].centroid.y), 4),
            requested_lon=round(float(grid_info["geom"].centroid.x), 4),
            source_lat=round(float(grid_info["geom"].centroid.y), 4),
            source_lon=round(float(grid_info["geom"].centroid.x), 4),
            retrieval_status=f"region_{agg_status}_{len(valid_cells)}_cells",
            start_year=start_year,
            end_year=end_year,
            is_synthetic=False,
        ),
    }


def build_series_provenance(
    *,
    parameter: str,
    requested_lat: float,
    requested_lon: float,
    actual_lat: float,
    actual_lon: float,
    timestamps: list[str],
    retrieval_status: str,
    fallback_distance_km: float | None = None,
    source_override: str | None = None,
    collection_override: str | None = None,
    data_type_override: str | None = None,
    unit_override: str | None = None,
    spatial_resolution_override: str | None = None,
    is_synthetic: bool = False,
    power_header: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build complete scientific provenance metadata for any retrieved, cached, imported, or synthetic series."""
    param = parameter.upper()
    meta = get_parameter_metadata(param)
    api_ver = ""
    if power_header and isinstance(power_header.get("api"), dict):
        api_ver = str(power_header["api"].get("version", "")).strip()
    default_source = meta["mission_source"]
    if api_ver and "NASA POWER" in default_source:
        default_source = f"NASA POWER API {api_ver} — {default_source.replace('NASA POWER — ', '')}"

    dist_val = round(float(fallback_distance_km), 2) if fallback_distance_km is not None else 0.0
    req_lat = round(float(requested_lat), 4)
    req_lon = round(float(requested_lon), 4)
    act_lat = round(float(actual_lat), 4)
    act_lon = round(float(actual_lon), 4)
    src = source_override or default_source
    return {
        "source": src,
        "source_name": src,
        "collection": collection_override or meta.get("collection", "MERRA-2"),
        "data_type": "synthetic_demo" if is_synthetic else (data_type_override or meta.get("data_type", "reanalysis")),
        "community": POWER_COMMUNITY_MAP.get(param, "AG"),
        "parameter": param,
        "parameter_name": meta["parameter_name"],
        "units": unit_override or meta["unit"],
        "temporal_resolution": meta.get("temporal_resolution", "Monthly"),
        "spatial_resolution": spatial_resolution_override or meta["resolution"],
        "start_date": timestamps[0] if timestamps else None,
        "end_date": timestamps[-1] if timestamps else None,
        "requested_coordinates": {"lat": req_lat, "lon": req_lon},
        "actual_coordinates": {"lat": act_lat, "lon": act_lon},
        "requested_lat": req_lat,
        "requested_lon": req_lon,
        "source_lat": act_lat,
        "source_lon": act_lon,
        "retrieval_status": retrieval_status,
        "dataset_tag": retrieval_status,
        "fallback_used": retrieval_status == "offline_fallback",
        "fallback_distance_km": dist_val,
        "is_synthetic": bool(is_synthetic),
    }


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
            p_lat, p_lon = float(c["primary_point"]["lat"]), float(c["primary_point"]["lon"])
            c_lat, c_lon = float(c["comparison_point"]["lat"]), float(c["comparison_point"]["lon"])
            return {
                "case": c,
                "primary": {
                    "parameter": c["parameter"],
                    "lat": p_lat,
                    "lon": p_lon,
                    "bounding_box": compute_bounding_box(p_lat, p_lon),
                    "timestamps": p_ts,
                    "values": p_vals,
                    "data_status": "cache",
                    "dataset_tag": "cached",
                    "provenance": build_series_provenance(
                        parameter=c["parameter"],
                        requested_lat=p_lat,
                        requested_lon=p_lon,
                        actual_lat=p_lat,
                        actual_lon=p_lon,
                        timestamps=p_ts,
                        retrieval_status="cached",
                    ),
                },
                "comparison": {
                    "parameter": c["parameter"],
                    "lat": c_lat,
                    "lon": c_lon,
                    "bounding_box": compute_bounding_box(c_lat, c_lon),
                    "timestamps": c_ts,
                    "values": c_vals,
                    "data_status": "cache",
                    "dataset_tag": "cached",
                    "provenance": build_series_provenance(
                        parameter=c["parameter"],
                        requested_lat=c_lat,
                        requested_lon=c_lon,
                        actual_lat=c_lat,
                        actual_lon=c_lon,
                        timestamps=c_ts,
                        retrieval_status="cached",
                    ),
                },
            }
    return None


def _find_nearest_cached(
    cache: dict[str, Any],
    parameter: str,
    lat: float,
    lon: float,
    start_year: int,
    end_year: int,
    max_radius_km: float = MAX_FALLBACK_RADIUS_KM,
) -> dict[str, Any] | None:
    """
    Find nearest cached observation for parameter by Haversine distance within max_radius_km.
    Preserves actual source coordinates rather than labeling another location's data as local.
    """
    param = parameter.upper()
    candidates: list[tuple[float, float, float, list[str], list[float | None], str]] = []

    for _, entry in cache.get("live_cache", {}).items():
        if entry.get("parameter", "").upper() == param and entry.get("timestamps"):
            e_lat = float(entry["lat"])
            e_lon = float(entry["lon"])
            dist = _haversine_km(lat, lon, e_lat, e_lon)
            candidates.append((dist, e_lat, e_lon, entry["timestamps"], entry["values"], f"cached ({e_lat:.2f}°, {e_lon:.2f}°)"))

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
    dist, src_lat, src_lon, ts_all, vals_all, label = candidates[0]
    if dist > max_radius_km:
        return None

    ts, vals = _slice_window(ts_all, vals_all, start_year, end_year)
    return {
        "parameter": param,
        "lat": round(src_lat, 4),
        "lon": round(src_lon, 4),
        "requested_lat": round(float(lat), 4),
        "requested_lon": round(float(lon), 4),
        "source_lat": round(src_lat, 4),
        "source_lon": round(src_lon, 4),
        "fallback_distance_km": round(dist, 2),
        "bounding_box": compute_bounding_box(src_lat, src_lon),
        "timestamps": ts,
        "values": vals,
        "data_status": "offline_fallback",
        "dataset_tag": "offline_fallback",
        "fallback_note": (
            f"Offline fallback: Using nearest cached MERRA-2 series from {label} at "
            f"({src_lat:.2f}°, {src_lon:.2f}°), located {dist:.1f} km from requested ({lat:.2f}°, {lon:.2f}°)."
        ),
        "provenance": build_series_provenance(
            parameter=param,
            requested_lat=lat,
            requested_lon=lon,
            actual_lat=src_lat,
            actual_lon=src_lon,
            timestamps=ts,
            retrieval_status="offline_fallback",
            fallback_distance_km=dist,
        ),
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
    Validates coordinates, routes parameter to the appropriate POWER community,
    checks local cache first, queries NASA POWER API (1981-2025) on miss and caches atomically,
    and falls back to nearest cached coordinate within MAX_FALLBACK_RADIUS_KM if offline.
    """
    lat_f, lon_f = validate_coordinates(lat, lon)
    param = parameter.upper()
    community = POWER_COMMUNITY_MAP.get(param, "AG")
    cache = _load_cache()
    key = _make_cache_key(param, lat_f, lon_f)

    if key in cache.get("live_cache", {}):
        entry = cache["live_cache"][key]
        ts, vals = _slice_window(entry["timestamps"], entry["values"], start_year, end_year)
        if len(ts) >= 24:
            e_lat = float(entry.get("lat", lat_f))
            e_lon = float(entry.get("lon", lon_f))
            return {
                "parameter": param,
                "lat": round(e_lat, 4),
                "lon": round(e_lon, 4),
                "bounding_box": compute_bounding_box(e_lat, e_lon),
                "timestamps": ts,
                "values": vals,
                "data_status": "cache",
                "dataset_tag": "cached",
                "provenance": build_series_provenance(
                    parameter=param,
                    requested_lat=lat_f,
                    requested_lon=lon_f,
                    actual_lat=e_lat,
                    actual_lon=e_lon,
                    timestamps=ts,
                    retrieval_status="cached",
                    power_header=entry.get("power_header"),
                ),
            }

    for c in cache.get("cases", []):
        if c.get("parameter", "").upper() == param:
            for pt_key, ser_key in [("primary_point", "primary_series"), ("comparison_point", "comparison_series")]:
                pt = c[pt_key]
                pt_lat, pt_lon = float(pt["lat"]), float(pt["lon"])
                dist_km = _haversine_km(lat_f, lon_f, pt_lat, pt_lon)
                if dist_km < 5.0:
                    ser = c[ser_key]
                    ts, vals = _slice_window(ser["timestamps"], ser["values"], start_year, end_year)
                    if len(ts) >= 24:
                        return {
                            "parameter": param,
                            "lat": round(pt_lat, 4),
                            "lon": round(pt_lon, 4),
                            "bounding_box": compute_bounding_box(pt_lat, pt_lon),
                            "timestamps": ts,
                            "values": vals,
                            "data_status": "cache",
                            "dataset_tag": "cached",
                            "provenance": build_series_provenance(
                                parameter=param,
                                requested_lat=lat_f,
                                requested_lon=lon_f,
                                actual_lat=pt_lat,
                                actual_lon=pt_lon,
                                timestamps=ts,
                                retrieval_status="cached",
                                fallback_distance_km=dist_km,
                            ),
                        }

    query_params = {
        "parameters": param,
        "community": community,
        "longitude": round(lon_f, 4),
        "latitude": round(lat_f, 4),
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
        power_header = payload.get("header") if isinstance(payload.get("header"), dict) else None
        full_ts, full_vals = _parse_power_monthly_payload(raw_param)

        cache = _load_cache()
        cache["live_cache"][key] = {
            "parameter": param,
            "lat": round(lat_f, 4),
            "lon": round(lon_f, 4),
            "timestamps": full_ts,
            "values": full_vals,
            "power_header": power_header,
        }
        _save_cache_atomic(cache)

        ts, vals = _slice_window(full_ts, full_vals, start_year, end_year)
        return {
            "parameter": param,
            "lat": round(lat_f, 4),
            "lon": round(lon_f, 4),
            "bounding_box": compute_bounding_box(lat_f, lon_f),
            "timestamps": ts,
            "values": vals,
            "data_status": "live",
            "dataset_tag": "live",
            "provenance": build_series_provenance(
                parameter=param,
                requested_lat=lat_f,
                requested_lon=lon_f,
                actual_lat=lat_f,
                actual_lon=lon_f,
                timestamps=ts,
                retrieval_status="live",
                power_header=power_header,
            ),
        }
    except Exception as exc:
        fallback = _find_nearest_cached(cache, param, lat_f, lon_f, start_year, end_year)
        if fallback is not None and len(fallback["timestamps"]) >= 24:
            return fallback
        raise RuntimeError(
            f"NASA POWER API unavailable and no cached fallback within {MAX_FALLBACK_RADIUS_KM:.0f} km found for {param}: {exc}"
        ) from exc


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
            "title": "NASA Giovanni Time-Series Portal (Export CSV → Analyse)",
            "category": "NASA India Earth Observation",
            "description": f"Export area-averaged monthly CSV for bbox [{bbox_str}] ({g_var}) and upload via Import CSV.",
            "url": giovanni_url,
        },
        {
            "id": "hydrology_ts",
            "agency": "NASA GES DISC",
            "title": "Hydrology Time Series / Data Rods",
            "category": "NASA India Earth Observation",
            "description": f"Generate GLDAS ASCII/CSV rods at ({lat:.2f}°N, {lon:.2f}°E) and import into TerraShift.",
            "url": hydro_url,
        },
        {
            "id": "appeears",
            "agency": "NASA LP DAAC",
            "title": "NASA AppEEARS Portal (MODIS / SMAP / ECOSTRESS)",
            "category": "NASA India Earth Observation",
            "description": "Live product catalog discovery in-app; point/polygon extraction via Earthdata login.",
            "url": "https://appeears.earthdatacloud.nasa.gov/",
        },
        {
            "id": "isro_mosdac",
            "agency": "ISRO / MOSDAC",
            "title": "ISRO Meteorological & Oceanographic Satellite Data Archival Centre",
            "category": "Indian Meteorological & Space Context",
            "description": "INSAT-3D/3DR, Oceansat, and India monsoon contextual reference portal.",
            "url": "https://www.mosdac.gov.in/",
        },
        {
            "id": "imd_india",
            "agency": "IMD (India Meteorological Department)",
            "title": "IMD Gridded Climate & Monsoon Reference",
            "category": "Indian Meteorological & Space Context",
            "description": "Official Indian Meteorological Department seasonal (DJF, MAM, JJAS, OND) climatology reference.",
            "url": "https://mausam.imd.gov.in/",
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
    Query live public endpoints from NASA CMR (MODIS/GPM/OMI/SMAP/MOPITT) and NASA AppEEARS
    for India coordinates.
    """
    global _APPEEARS_CACHE
    box = compute_bounding_box(lat, lon)
    bbox_str = f"{box['west']},{box['south']},{box['east']},{box['north']}"

    cmr_collections: list[dict[str, str]] = []
    appeears_products: list[dict[str, str]] = []

    async with httpx.AsyncClient(timeout=4.5, follow_redirects=True) as client:
        cmr_task = client.get(
            NASA_CMR_COLLECTIONS_URL,
            params={"bounding_box": bbox_str, "page_size": 6},
        )
        appeears_task = (
            client.get(NASA_APPEEARS_PRODUCTS_URL) if _APPEEARS_CACHE is None else None
        )

        results = await asyncio.gather(
            cmr_task,
            *([appeears_task] if appeears_task is not None else []),
            return_exceptions=True,
        )

        if isinstance(results[0], httpx.Response) and results[0].status_code == 200:
            entries = results[0].json().get("feed", {}).get("entry", [])
            for e in entries:
                short_name = e.get("short_name") or e.get("dataset_id", "NASA Dataset")
                if not any(c["short_name"] == short_name for c in cmr_collections):
                    cmr_collections.append({
                        "short_name": short_name,
                        "title": e.get("title", short_name),
                        "data_center": e.get("data_center", "NASA EOSDIS"),
                        "summary": (e.get("summary") or "")[:160],
                    })

        if appeears_task is not None and len(results) >= 2 and isinstance(results[1], httpx.Response):
            if results[1].status_code == 200 and isinstance(results[1].json(), list):
                _APPEEARS_CACHE = results[1].json()

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
                "product_id": "MOD13C2.061",
                "platform": "Terra MODIS",
                "description": "Vegetation Indices Monthly CMG 0.05 deg (NDVI / EVI)",
                "resolution": "0.05°",
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
                "short_name": "GPM_3IMERGM",
                "title": "GPM IMERG Final Precipitation L3 1 month 0.1 degree x 0.1 degree V07",
                "data_center": "NASA GES DISC",
                "summary": "Multi-satellite merged monthly precipitation calibrated with global rain gauges.",
            },
            {
                "short_name": "OMNO2d",
                "title": "OMI/Aura NO2 Cloud-Screened Total and Tropospheric Column L3 0.25 degree",
                "data_center": "NASA GES DISC",
                "summary": "Satellite tropospheric nitrogen dioxide column abundance.",
            },
        ]

    return {
        "coordinates": {"lat": lat, "lon": lon, "bounding_box": box},
        "cmr_collections": cmr_collections[:6],
        "appeears_products": appeears_products[:5],
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
    is_synthetic = "SYNTHETIC" in source_hint.upper() or "DEMO" in source_hint.upper()
    for ln in lines[:10]:
        if ln.startswith("#") or ln.startswith("%"):
            upper_ln = ln.upper()
            if "SYNTHETIC_DEMO_DATA" in upper_ln or "SYNTHETIC" in upper_ln:
                is_synthetic = True

    dataset_tag = "synthetic" if is_synthetic else "imported"

    # Parse NASA Giovanni / GES DISC Hydrology / AppEEARS CSV or whitespace lines
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
            "parameter_name": (
                f"Synthetic Demo Series ({detected_source} Format)"
                if is_synthetic
                else f"Imported {detected_source} Series"
            ),
            "unit": detected_unit,
            "mission_source": (
                f"Synthetic Demo Waveform ({detected_source} format)"
                if is_synthetic
                else detected_source
            ),
            "is_synthetic": "true" if is_synthetic else "false",
            "dataset_tag": dataset_tag,
        },
    )


async def seed_preset_cases() -> dict[str, Any]:
    """Fetch real 1981-2025 NASA POWER data for all 6 Detective Case Files and persist to cases_cache.json."""
    cache = _load_cache()
    seeded_cases: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=15.0) as client:
        for spec in PRESET_CASE_SPECS:
            param = spec["parameter"]
            community = POWER_COMMUNITY_MAP.get(param.upper(), "AG")
            p_pt = spec["primary_point"]
            c_pt = spec["comparison_point"]

            p_resp, c_resp = await asyncio.gather(
                client.get(
                    NASA_POWER_URL,
                    params={
                        "parameters": param,
                        "community": community,
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
                        "community": community,
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
