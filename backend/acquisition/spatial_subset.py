"""India polygon boundary loader, native-grid polygon masking, area-weighted extraction, and subset storage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr
from shapely.geometry import shape
from shapely.ops import unary_union
from shapely import contains_xy

from .storage_manager import DATA_DIR, get_processed_path


BOUNDARIES_DIR = DATA_DIR / "boundaries"
ZONE_LABELS = {
    "india": "Entire India",
    "north": "North India",
    "south": "South India",
    "east": "East India",
    "west": "West India",
    "central": "Central India",
    "northeast": "Northeast India",
}


def _count_vertices(geom: Any) -> int:
    total = 0
    gtype = geom.geom_type
    if gtype == "Polygon":
        total += len(geom.exterior.coords)
        for ring in geom.interiors:
            total += len(ring.coords)
    elif gtype == "MultiPolygon":
        for poly in geom.geoms:
            total += _count_vertices(poly)
    return total


def list_available_regions() -> list[dict[str, Any]]:
    """List supported India macro-zones, states, and districts from authoritative GeoJSON files."""
    regions: list[dict[str, Any]] = []
    states_file = BOUNDARIES_DIR / "states" / "india_states.geojson"
    india_file = BOUNDARIES_DIR / "india" / "india_outline.geojson"
    districts_file = BOUNDARIES_DIR / "districts" / "india_sample_districts.geojson"

    # 1. Entire India + 6 Macro-Zones
    zones_geoms: dict[str, list[Any]] = {z: [] for z in ZONE_LABELS}
    if india_file.exists():
        india_fc = json.loads(india_file.read_text(encoding="utf-8"))
        for feat in india_fc.get("features", []):
            g = shape(feat["geometry"])
            zones_geoms["india"].append(g)

    state_entries: list[dict[str, Any]] = []
    if states_file.exists():
        states_fc = json.loads(states_file.read_text(encoding="utf-8"))
        for feat in states_fc.get("features", []):
            props = feat.get("properties", {})
            g = shape(feat["geometry"])
            z = str(props.get("zone", "india")).lower()
            if z in zones_geoms:
                zones_geoms[z].append(g)
            minx, miny, maxx, maxy = g.bounds
            state_entries.append(
                {
                    "region_id": props.get("region_id"),
                    "name": props.get("name"),
                    "zone": z,
                    "level": "state",
                    "vertex_count": _count_vertices(g),
                    "bbox": [round(minx, 3), round(miny, 3), round(maxx, 3), round(maxy, 3)],
                }
            )

    for z_id, z_label in ZONE_LABELS.items():
        geoms = zones_geoms.get(z_id, [])
        if not geoms and z_id == "india" and state_entries:
            continue
        if geoms:
            merged = unary_union(geoms)
            minx, miny, maxx, maxy = merged.bounds
            regions.append(
                {
                    "region_id": z_id,
                    "name": z_label,
                    "zone": z_id,
                    "level": "country" if z_id == "india" else "zone",
                    "vertex_count": _count_vertices(merged),
                    "bbox": [round(minx, 3), round(miny, 3), round(maxx, 3), round(maxy, 3)],
                }
            )

    regions.extend(state_entries)

    if districts_file.exists():
        dist_fc = json.loads(districts_file.read_text(encoding="utf-8"))
        for feat in dist_fc.get("features", []):
            props = feat.get("properties", {})
            g = shape(feat["geometry"])
            minx, miny, maxx, maxy = g.bounds
            regions.append(
                {
                    "region_id": props.get("region_id"),
                    "name": props.get("name"),
                    "zone": str(props.get("zone", "india")).lower(),
                    "level": "district",
                    "vertex_count": _count_vertices(g),
                    "bbox": [round(minx, 3), round(miny, 3), round(maxx, 3), round(maxy, 3)],
                }
            )

    return regions


def load_region_polygon(region_id: str) -> tuple[Any, dict[str, Any]]:
    """Load exact Shapely Polygon/MultiPolygon geometry and metadata for a region_id."""
    key = region_id.strip().lower()
    india_file = BOUNDARIES_DIR / "india" / "india_outline.geojson"
    states_file = BOUNDARIES_DIR / "states" / "india_states.geojson"
    districts_file = BOUNDARIES_DIR / "districts" / "india_sample_districts.geojson"

    if key == "india" and india_file.exists():
        fc = json.loads(india_file.read_text(encoding="utf-8"))
        geom = shape(fc["features"][0]["geometry"])
        return geom, {
            "region_id": "india",
            "region_name": "Entire India",
            "region_level": "country",
            "zone": "india",
            "boundary_file": str(india_file),
            "polygon_vertex_count": _count_vertices(geom),
        }

    if key in ZONE_LABELS and key != "india" and states_file.exists():
        fc = json.loads(states_file.read_text(encoding="utf-8"))
        matching = [
            shape(f["geometry"])
            for f in fc.get("features", [])
            if str(f.get("properties", {}).get("zone", "")).lower() == key
        ]
        if matching:
            geom = unary_union(matching)
            return geom, {
                "region_id": key,
                "region_name": ZONE_LABELS[key],
                "region_level": "zone",
                "zone": key,
                "boundary_file": str(states_file),
                "polygon_vertex_count": _count_vertices(geom),
            }

    for path in (states_file, districts_file):
        if not path.exists():
            continue
        fc = json.loads(path.read_text(encoding="utf-8"))
        for feat in fc.get("features", []):
            props = feat.get("properties", {})
            rid = str(props.get("region_id", "")).lower()
            rname = str(props.get("name", "")).lower()
            if key == rid or key == rname:
                geom = shape(feat["geometry"])
                return geom, {
                    "region_id": props.get("region_id", key),
                    "region_name": props.get("name", region_id),
                    "region_level": props.get("level", "state"),
                    "zone": str(props.get("zone", "india")).lower(),
                    "boundary_file": str(path),
                    "polygon_vertex_count": _count_vertices(geom),
                }

    raise ValueError(f"Unknown India region_id '{region_id}'. Check /api/acquisition/boundaries for valid IDs.")


def _find_lat_lon_names(ds: xr.Dataset) -> tuple[str, str]:
    lat_name = next((c for c in ("lat", "latitude", "Lat", "Y", "y") if c in ds.coords or c in ds.dims), None)
    lon_name = next((c for c in ("lon", "longitude", "Lon", "X", "x") if c in ds.coords or c in ds.dims), None)
    if not lat_name or not lon_name:
        raise ValueError(f"Dataset lacks standard latitude/longitude coordinates. Found coords: {list(ds.coords)}")
    return lat_name, lon_name


def extract_polygon_subset(
    *,
    ds: xr.Dataset,
    variable_name: str,
    region_id: str,
    output_stem: str | None = None,
) -> dict[str, Any]:
    """
    Mask an xarray Dataset strictly to a real India/state/district polygon without
    substituting rectangular bounding boxes, preserving original grid resolution,
    handling ascending/descending lat and 0..360 lon conventions, and computing
    cosine-latitude area-weighted means.
    """
    if variable_name not in ds.data_vars:
        raise ValueError(f"Variable '{variable_name}' not found in dataset variables: {list(ds.data_vars)}")

    geom, region_meta = load_region_polygon(region_id)
    lat_name, lon_name = _find_lat_lon_names(ds)

    work = ds
    # Normalize 0..360 longitude to -180..180 cleanly while sorting ascending
    lons_raw = work[lon_name].to_numpy()
    if float(np.nanmax(lons_raw)) > 180.0:
        new_lon = ((lons_raw + 180.0) % 360.0) - 180.0
        work = work.assign_coords({lon_name: new_lon}).sortby(lon_name)

    # Ensure ascending latitude ordering if inverted, while preserving resolution
    lats_raw = work[lat_name].to_numpy()
    if len(lats_raw) > 1 and lats_raw[0] > lats_raw[-1]:
        work = work.sortby(lat_name)

    minx, miny, maxx, maxy = geom.bounds
    da = work[variable_name]

    # Pre-clip slightly around polygon bounds for efficiency, then apply true polygon mask
    lats = work[lat_name].to_numpy()
    lons = work[lon_name].to_numpy()
    lat_mask_1d = (lats >= miny - 1.5) & (lats <= maxy + 1.5)
    lon_mask_1d = (lons >= minx - 1.5) & (lons <= maxx + 1.5)
    if np.any(lat_mask_1d) and np.any(lon_mask_1d):
        da = da.isel({lat_name: lat_mask_1d, lon_name: lon_mask_1d})
        work = work.isel({lat_name: lat_mask_1d, lon_name: lon_mask_1d})

    sub_lats = work[lat_name].to_numpy()
    sub_lons = work[lon_name].to_numpy()
    lon2d, lat2d = np.meshgrid(sub_lons, sub_lats)

    poly_mask_2d = contains_xy(geom, lon2d, lat2d)
    inside_count = int(np.sum(poly_mask_2d))
    if inside_count == 0:
        # Check whether centroid or coarse grid cells touch polygon before failing
        raise ValueError(
            f"No grid cell centers fell inside polygon '{region_meta['region_name']}' "
            f"(grid shape {poly_mask_2d.shape}). Grid may be outside India or coarser than the district."
        )

    mask_da = xr.DataArray(
        poly_mask_2d,
        dims=(lat_name, lon_name),
        coords={lat_name: sub_lats, lon_name: sub_lons},
    )
    masked_da = da.where(mask_da)

    # Area weighting proportional to cos(latitude)
    weights_1d = np.cos(np.deg2rad(np.clip(sub_lats, -89.9, 89.9)))
    weights_2d = xr.DataArray(
        np.broadcast_to(weights_1d[:, None], (len(sub_lats), len(sub_lons))),
        dims=(lat_name, lon_name),
        coords={lat_name: sub_lats, lon_name: sub_lons},
    ).where(mask_da)

    weighted_mean_da = masked_da.weighted(weights_2d.fillna(0.0)).mean(dim=(lat_name, lon_name), skipna=True)
    vals = masked_da.to_numpy().astype(float)
    valid_vals = vals[np.isfinite(vals)]
    total_inside_obs = int(inside_count * (vals.shape[0] if vals.ndim == 3 else 1))
    valid_fraction = round(float(len(valid_vals) / max(1, total_inside_obs)), 4)

    time_series: list[dict[str, Any]] = []
    time_name = next((c for c in ("time", "Time", "t") if c in masked_da.dims), None)
    if time_name is not None:
        t_coords = masked_da[time_name].to_numpy()
        w_vals = weighted_mean_da.to_numpy()
        for t_val, w_val in zip(t_coords, w_vals):
            ts_str = str(t_val)[:10]
            time_series.append(
                {
                    "timestamp": ts_str,
                    "area_weighted_mean": None if not np.isfinite(w_val) else round(float(w_val), 5),
                }
            )

    out_ds = masked_da.to_dataset(name=variable_name)
    out_ds.attrs.update(
        {
            "region_id": region_meta["region_id"],
            "region_name": region_meta["region_name"],
            "weighting": "cos(latitude) grid-cell area weighted over shapely polygon mask",
            "original_resolution_preserved": "true",
        }
    )

    stem = output_stem or f"{variable_name}_{region_meta['region_id']}"
    out_path = get_processed_path(region_meta["zone"], f"{stem}.nc")
    out_ds.to_netcdf(out_path)

    return {
        **region_meta,
        "grid_cells_total": int(poly_mask_2d.size),
        "grid_cells_inside_mask": inside_count,
        "original_resolution_preserved": True,
        "weighting_method": "cosine_latitude_area_weighted",
        "output_file": str(out_path),
        "variable_name": variable_name,
        "units": str(da.attrs.get("units", "unknown")),
        "regional_mean": round(float(np.nanmean(valid_vals)), 5) if len(valid_vals) else None,
        "regional_min": round(float(np.nanmin(valid_vals)), 5) if len(valid_vals) else None,
        "regional_max": round(float(np.nanmax(valid_vals)), 5) if len(valid_vals) else None,
        "valid_fraction": valid_fraction,
        "time_series": time_series,
    }
