"""Real NASA Satellite Mission Data Service (MOD13C2, GPM_3IMERGM, OMNO2d, MOD11C3).

Fetches monthly satellite observations via NASA Earthdata (earthaccess / CMR / OPeNDAP / AppEEARS),
applies dataset-specific scale factors, fill values, and QA masks, and caches validated series on disk.
Never fabricates synthetic or placeholder satellite values.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

from config import SATELLITE_CACHE_DIR
from acquisition.cmr_client import search_granules
from acquisition.dataset_registry import (
    TREND_VARIABLE_REGISTRY,
    get_dataset_by_id,
    parse_and_scale_satellite_series,
)
from acquisition.earthdata_auth import get_auth_diagnostics
from acquisition.spatial_subset import (
    compute_area_weighted_series,
    compute_terrain_quality_flags,
    load_region_polygon,
)

SATELLITE_VARIABLE_IDS = {"MOD13C2", "GPM_3IMERGM", "OMNO2d", "MOD11C3"}


def is_satellite_variable(parameter: str) -> bool:
    return parameter.strip() in SATELLITE_VARIABLE_IDS or parameter.strip().upper() in {
        k.upper() for k in SATELLITE_VARIABLE_IDS
    }


def normalize_satellite_id(parameter: str) -> str:
    p = parameter.strip()
    for k in SATELLITE_VARIABLE_IDS:
        if k.upper() == p.upper():
            return k
    return p


def _cache_key(dataset_id: str, scope_key: str, start_year: int, end_year: int) -> Path:
    SATELLITE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe_scope = re.sub(r"[^a-zA-Z0-9._-]+", "_", scope_key).strip("_")
    return SATELLITE_CACHE_DIR / f"{dataset_id}_{safe_scope}_{start_year}_{end_year}.json"


def _read_disk_cache(cache_path: Path) -> dict[str, Any] | None:
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("timestamps") and payload.get("values"):
            payload["data_status"] = "cache"
            payload["dataset_tag"] = "cached_satellite"
            return payload
    except Exception:
        return None
    return None


def _write_disk_cache(cache_path: Path, payload: dict[str, Any]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _extract_var_from_opendap_ds(
    ds: xr.Dataset,
    dataset_id: str,
    lat: float | None = None,
    lon: float | None = None,
    region_id: str | None = None,
) -> tuple[float | None, int | None]:
    """Extract either polygon-averaged or nearest-pixel value + QA flag from an xarray Dataset."""
    spec = TREND_VARIABLE_REGISTRY[dataset_id]
    cat_entry = get_dataset_by_id(dataset_id) or {}
    candidate_vars = cat_entry.get("variable_names", [])

    target_var = next((v for v in candidate_vars if v in ds.data_vars), None)
    if target_var is None:
        # Fallback to first numeric 2D/3D data variable that is not QA/time
        for v in ds.data_vars:
            if "qa" not in str(v).lower() and "quality" not in str(v).lower() and ds[v].ndim >= 2:
                target_var = str(v)
                break
    if target_var is None:
        raise ValueError(f"No matching science variable found in {dataset_id} granule: {list(ds.data_vars)}")

    qa_var = next(
        (
            v
            for v in ds.data_vars
            if any(q.lower() in str(v).lower() for q in ("reliability", "quality", "qc", "cloud"))
        ),
        None,
    )

    lat_name = next((c for c in ("lat", "latitude", "Lat", "YDim", "y") if c in ds.coords or c in ds.dims), None)
    lon_name = next((c for c in ("lon", "longitude", "Lon", "XDim", "x") if c in ds.coords or c in ds.dims), None)
    if not lat_name or not lon_name:
        raise ValueError(f"Granule missing lat/lon coordinates for {dataset_id}")

    da = ds[target_var]
    if region_id:
        from shapely import contains_xy

        geom, _ = load_region_polygon(region_id)
        minx, miny, maxx, maxy = geom.bounds
        lats = ds[lat_name].to_numpy()
        lons = ds[lon_name].to_numpy()
        lat_mask = (lats >= miny - 0.5) & (lats <= maxy + 0.5)
        lon_mask = (lons >= minx - 0.5) & (lons <= maxx + 0.5)
        sub = da.isel({lat_name: lat_mask, lon_name: lon_mask})
        sub_lats = sub[lat_name].to_numpy()
        sub_lons = sub[lon_name].to_numpy()
        lon2d, lat2d = np.meshgrid(sub_lons, sub_lats)
        poly_mask = contains_xy(geom, lon2d, lat2d)
        if not np.any(poly_mask):
            rep = geom.representative_point()
            lat, lon = float(rep.y), float(rep.x)
        else:
            w1d = np.cos(np.deg2rad(np.clip(sub_lats, -89.9, 89.9)))
            w2d = np.broadcast_to(w1d[:, None], (len(sub_lats), len(sub_lons)))
            arr = sub.to_numpy().astype(float)
            while arr.ndim > 2:
                arr = arr[0]
            valid = np.isfinite(arr) & poly_mask & (arr != spec["fill_value"])
            if not np.any(valid):
                return None, None
            raw_val = float(np.sum(arr[valid] * w2d[valid]) / np.sum(w2d[valid]))
            return raw_val, None

    if lat is None or lon is None:
        raise ValueError("Either lat/lon or region_id must be provided.")

    pt_da = da.sel({lat_name: lat, lon_name: lon}, method="nearest")
    raw_val = float(np.asarray(pt_da).item())
    qa_val = None
    if qa_var and qa_var in ds.data_vars:
        try:
            qa_val = int(np.asarray(ds[qa_var].sel({lat_name: lat, lon_name: lon}, method="nearest")).item())
        except Exception:
            qa_val = None
    return raw_val, qa_val


async def fetch_satellite_monthly(
    *,
    dataset_id: str,
    start_year: int = 2001,
    end_year: int = 2025,
    lat: float | None = None,
    lon: float | None = None,
    region_id: str | None = None,
) -> dict[str, Any]:
    """
    Retrieve monthly satellite observations for MOD13C2, GPM_3IMERGM, OMNO2d, or MOD11C3.
    Uses local disk cache first; otherwise queries NASA Earthdata CMR + OPeNDAP/earthaccess
    using EARTHDATA_* environment variables. Raises RuntimeError on missing auth or failure
    (never returns synthetic data).
    """
    ds_id = normalize_satellite_id(dataset_id)
    if ds_id not in TREND_VARIABLE_REGISTRY:
        raise ValueError(f"Unknown satellite dataset_id: {dataset_id}")

    spec = TREND_VARIABLE_REGISTRY[ds_id]
    scope_key = region_id.strip().lower() if region_id else f"{lat:.3f}_{lon:.3f}"
    cache_path = _cache_key(ds_id, scope_key, start_year, end_year)
    cached = _read_disk_cache(cache_path)
    if cached is not None:
        return cached

    auth = get_auth_diagnostics()
    if not auth.get("earthdata_configured"):
        raise RuntimeError(
            f"NASA Earthdata credentials are required to fetch live {ds_id} ({spec['mission_source']}) data. "
            "Configure EARTHDATA_TOKEN or EARTHDATA_USERNAME + EARTHDATA_PASSWORD in environment variables."
        )

    # Attempt real CMR granule discovery + earthaccess / OPeNDAP extraction
    if region_id:
        geom, reg_meta = load_region_polygon(region_id)
        minx, miny, maxx, maxy = geom.bounds
        bbox = [round(miny, 3), round(minx, 3), round(maxy, 3), round(maxx, 3)]
        loc_name = reg_meta["region_name"]
    else:
        assert lat is not None and lon is not None
        bbox = [round(lat - 0.5, 3), round(lon - 0.5, 3), round(lat + 0.5, 3), round(lon + 0.5, 3)]
        loc_name = f"{lat:.2f}°N, {lon:.2f}°E"

    granules_resp = await search_granules(
        dataset_id=ds_id,
        start_date=f"{start_year}-01-01",
        end_date=f"{end_year}-12-31",
        bbox=bbox,
        page_size=200,
    )
    granules = granules_resp.get("granules", [])
    if not granules:
        raise RuntimeError(
            f"No NASA CMR granules found for {ds_id} in window {start_year}-{end_year} over {loc_name}."
        )

    def _download_and_extract() -> tuple[list[str], list[float | None], list[int | None]]:
        import earthaccess  # type: ignore

        earthaccess.login(strategy="environment")
        results = earthaccess.search_data(
            short_name=ds_id,
            bounding_box=(bbox[1], bbox[0], bbox[3], bbox[2]),
            temporal=(f"{start_year}-01-01", f"{end_year}-12-31"),
            count=min(360, len(granules)),
        )
        if not results:
            raise RuntimeError(f"earthaccess returned 0 granules for {ds_id}.")

        ts_list: list[str] = []
        raw_vals: list[float | None] = []
        qa_vals: list[int | None] = []

        opened = earthaccess.open(results)
        for gran, fobj in zip(results, opened):
            try:
                t_start = str(gran["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"])[:7]
            except Exception:
                t_start = ""
            if not t_start:
                continue
            with xr.open_dataset(fobj) as ds:
                rv, qv = _extract_var_from_opendap_ds(ds, ds_id, lat=lat, lon=lon, region_id=region_id)
                ts_list.append(t_start)
                raw_vals.append(rv)
                qa_vals.append(qv)

        return ts_list, raw_vals, qa_vals

    ts_raw, vals_raw, qas_raw = await asyncio.to_thread(_download_and_extract)
    if len(ts_raw) < 24:
        raise RuntimeError(
            f"Retrieved only {len(ts_raw)} monthly granules for {ds_id}; at least 24 months are required for trend analysis."
        )

    # Sort chronologically and apply dataset-specific scale factors, fill values, and QA masks
    paired = sorted(zip(ts_raw, vals_raw, qas_raw), key=lambda x: x[0])
    timestamps = [p[0] for p in paired]
    scaled_values = parse_and_scale_satellite_series(
        ds_id,
        [p[1] for p in paired],
        [p[2] for p in paired],
    )

    q_flags = compute_terrain_quality_flags(
        lat=lat,
        lon=lon,
        mean_ndvi=float(np.nanmean([v for v in scaled_values if v is not None])) if ds_id == "MOD13C2" else None,
        mean_precip_mm_day=float(np.nanmean([v for v in scaled_values if v is not None])) if ds_id == "GPM_3IMERGM" else None,
    )

    payload: dict[str, Any] = {
        "parameter": ds_id,
        "lat": lat,
        "lon": lon,
        "region_id": region_id,
        "location_name": loc_name,
        "bounding_box": {
            "south": bbox[0],
            "west": bbox[1],
            "north": bbox[2],
            "east": bbox[3],
        },
        "timestamps": timestamps,
        "values": scaled_values,
        "data_status": "live",
        "dataset_tag": "satellite_live",
        "quality_flags": q_flags,
        "provenance": {
            "source": spec["mission_source"],
            "source_badge": spec["source_badge"],
            "collection": spec["collection"],
            "data_type": "satellite",
            "doi": spec["doi"],
            "retrieval_status": "live_earthdata",
            "is_synthetic": False,
            "units": spec["units"],
            "qa_rule": spec["qa_mask_rule"],
        },
    }
    _write_disk_cache(cache_path, payload)
    return payload
