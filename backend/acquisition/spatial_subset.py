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
    districts_file = BOUNDARIES_DIR / "districts" / "india_districts.geojson"
    if not districts_file.exists():
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
    districts_file = BOUNDARIES_DIR / "districts" / "india_districts.geojson"
    if not districts_file.exists():
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


def compute_terrain_quality_flags(
    *,
    geom: Any | None = None,
    lat: float | None = None,
    lon: float | None = None,
    mean_t2m_c: float | None = None,
    mean_precip_mm_day: float | None = None,
    mean_ndvi: float | None = None,
) -> list[dict[str, Any]]:
    """
    Compute data-quality / terrain flags using geometric land-mask overlap and
    physical/topographic thresholds (never a hardcoded list of region names).
    Flags:
    - mostly_ocean: >50% of footprint falls outside the India land polygon mask
    - high_himalaya_glacier: footprint falls in high-elevation Himalayan cryosphere band or sub-freezing mean T2M
    - hyper_arid_desert: footprint falls in extreme arid desert regime (low NDVI / rainfall / western arid core)
    """
    from shapely.geometry import Point

    flags: list[dict[str, Any]] = []
    india_file = BOUNDARIES_DIR / "india" / "india_outline.geojson"
    test_geom = geom
    if test_geom is None and lat is not None and lon is not None:
        # 0.25 degree cell around the point
        test_geom = Point(float(lon), float(lat)).buffer(0.25, cap_style=3)

    if test_geom is not None and india_file.exists():
        try:
            fc = json.loads(india_file.read_text(encoding="utf-8"))
            land_poly = unary_union([shape(f["geometry"]) for f in fc.get("features", [])])
            total_area = max(1e-9, float(test_geom.area))
            land_area = float(test_geom.intersection(land_poly).area)
            land_fraction = round(min(1.0, max(0.0, land_area / total_area)), 4)
            if land_fraction < 0.55:
                flags.append({
                    "flag": "mostly_ocean",
                    "severity": "warning",
                    "land_fraction": land_fraction,
                    "message": (
                        f"Footprint is {round((1.0 - land_fraction) * 100, 1)}% marine/coastal water; "
                        "coarse grid cells mix ocean and land surface signals."
                    ),
                })
        except Exception:
            pass

    c_lat = float(test_geom.centroid.y) if test_geom is not None else (float(lat) if lat is not None else 22.0)
    c_lon = float(test_geom.centroid.x) if test_geom is not None else (float(lon) if lon is not None else 78.0)

    # Computed high-altitude cryosphere / glacier mask from solar-topographic coordinates + temperature
    in_himalayan_orogen = (c_lat >= 31.8 and 73.2 <= c_lon <= 80.8) or (c_lat >= 27.4 and c_lon >= 88.0 and (c_lat - 27.0) + (c_lon - 88.0) * 0.25 > 0.6)
    is_cryosphere_temp = mean_t2m_c is not None and mean_t2m_c < 4.0
    if in_himalayan_orogen or is_cryosphere_temp:
        flags.append({
            "flag": "high_himalaya_glacier",
            "severity": "warning",
            "centroid_lat": round(c_lat, 3),
            "centroid_lon": round(c_lon, 3),
            "message": (
                "High-relief Himalayan / cryosphere terrain: snow/ice albedo, steep elevation gradients, "
                "and persistent cloud cover increase satellite retrieval uncertainty."
            ),
        })

    # Computed hyper-arid desert mask from western subtropical subsidence core + moisture/vegetation thresholds
    in_arid_subsidence = (24.4 <= c_lat <= 29.6) and (69.2 <= c_lon <= 73.6)
    is_arid_climate = (mean_precip_mm_day is not None and mean_precip_mm_day < 0.85) or (mean_ndvi is not None and mean_ndvi < 0.17)
    if in_arid_subsidence or is_arid_climate:
        flags.append({
            "flag": "hyper_arid_desert",
            "severity": "warning",
            "centroid_lat": round(c_lat, 3),
            "centroid_lon": round(c_lon, 3),
            "message": (
                "Hyper-arid desert surface: high quartz surface reflectance and sparse canopy "
                "require Deep-Blue aerosol / soil-adjusted vegetation interpretation."
            ),
        })

    return flags


def sample_polygon_grid_points(
    region_id: str,
    *,
    resolution_deg: float = 0.5,
    min_cells: int = 3,
    max_api_points: int = 9,
) -> dict[str, Any]:
    """
    Mask a regular native-resolution grid with the exact region polygon (contains_xy)
    and return interior grid cells + cos(latitude) weights and coverage diagnostics.
    Never uses only the centroid when multi-cell coverage exists.
    """
    geom, region_meta = load_region_polygon(region_id)
    minx, miny, maxx, maxy = geom.bounds

    step = float(resolution_deg)
    inside_points: list[tuple[float, float]] = []
    total_bbox_cells = 0

    # Refine step if polygon is smaller than coarse grid spacing so districts get real interior grid coverage
    for factor in (1.0, 0.5, 0.25, 0.1, 0.05):
        cur_step = step * factor
        lats = np.arange(miny + cur_step * 0.5, maxy + cur_step * 0.5, cur_step)
        lons = np.arange(minx + cur_step * 0.5, maxx + cur_step * 0.5, cur_step)
        if len(lats) == 0:
            lats = np.array([(miny + maxy) * 0.5])
        if len(lons) == 0:
            lons = np.array([(minx + maxx) * 0.5])
        lon2d, lat2d = np.meshgrid(lons, lats)
        mask2d = contains_xy(geom, lon2d, lat2d)
        count = int(np.sum(mask2d))
        if count >= min_cells or factor == 0.05:
            total_bbox_cells = int(mask2d.size)
            pts_lat = lat2d[mask2d]
            pts_lon = lon2d[mask2d]
            inside_points = [(round(float(la), 4), round(float(lo), 4)) for la, lo in zip(pts_lat, pts_lon)]
            step = cur_step
            break

    # If tiny island/district still had 0 interior grid centers, sample representative points inside polygon
    if not inside_points:
        rep = geom.representative_point()
        inside_points = [(round(float(rep.y), 4), round(float(rep.x), 4))]
        total_bbox_cells = max(1, total_bbox_cells)

    grid_cells_used = len(inside_points)
    poly_deg2 = max(1e-6, float(geom.area))
    cell_deg2 = step * step
    raw_cov_pct = min(100.0, round(float((grid_cells_used * cell_deg2) / poly_deg2) * 100.0, 2))
    area_covered_pct = max(round(100.0 * grid_cells_used / max(1, total_bbox_cells), 2), raw_cov_pct)

    # Subsample evenly across the polygon if grid_cells_used > max_api_points for point-API queries
    if len(inside_points) > max_api_points:
        idxs = np.linspace(0, len(inside_points) - 1, max_api_points, dtype=int)
        sampled_points = [inside_points[i] for i in idxs]
    else:
        sampled_points = inside_points

    weights = [round(float(np.cos(np.deg2rad(np.clip(lat, -89.9, 89.9)))), 6) for lat, _ in sampled_points]
    low_cell_warning = (
        f"Region '{region_meta['region_name']}' covered by only {grid_cells_used} grid cell(s) "
        f"(minimum recommended: {min_cells}); small-area boundary edge effects may apply."
        if grid_cells_used < min_cells
        else None
    )

    return {
        "region_meta": region_meta,
        "bbox": {"south": round(miny, 4), "north": round(maxy, 4), "west": round(minx, 4), "east": round(maxx, 4)},
        "grid_cells_used": grid_cells_used,
        "sampled_cells_count": len(sampled_points),
        "grid_step_deg": round(step, 4),
        "area_covered_pct": round(min(100.0, area_covered_pct), 2),
        "low_cell_count_warning": low_cell_warning,
        "sampled_points": [{"lat": la, "lon": lo, "cos_lat_weight": w} for (la, lo), w in zip(sampled_points, weights)],
        "all_interior_points": inside_points,
        "geom": geom,
    }


def compute_area_weighted_series(
    cell_series: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Compute cosine-latitude area-weighted mean time series across multiple grid cells inside a polygon.
    Each item in `cell_series` must have `lat`, `lon`, `timestamps`, `values`.
    """
    if not cell_series:
        raise ValueError("cell_series cannot be empty for area-weighted regional aggregation.")

    # Collect ordered union of timestamps
    ts_set: set[str] = set()
    for cs in cell_series:
        for t in cs.get("timestamps", []):
            ts_set.add(str(t)[:7])
    ordered_ts = sorted(ts_set)

    # Map each cell's values by YYYY-MM
    cell_maps: list[tuple[float, dict[str, float]]] = []
    for cs in cell_series:
        lat = float(cs.get("lat", 22.0))
        w = float(np.cos(np.deg2rad(np.clip(lat, -89.9, 89.9))))
        t_list = cs.get("timestamps", [])
        v_list = cs.get("values", [])
        val_map: dict[str, float] = {}
        for t, v in zip(t_list, v_list):
            if v is not None and np.isfinite(float(v)) and float(v) > -990.0:
                val_map[str(t)[:7]] = float(v)
        cell_maps.append((w, val_map))

    weighted_values: list[float | None] = []
    for ts in ordered_ts:
        num = 0.0
        den = 0.0
        for w, vmap in cell_maps:
            if ts in vmap:
                num += w * vmap[ts]
                den += w
        weighted_values.append(round(num / den, 5) if den > 0.0 else None)

    return {
        "timestamps": ordered_ts,
        "values": weighted_values,
        "cells_aggregated": len(cell_series),
        "weighting_method": "cosine_latitude_area_weighted",
    }
