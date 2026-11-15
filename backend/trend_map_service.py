"""India Trend Choropleth Map computation service with batching, disk caching, BH-FDR, and opposite-trends."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
from shapely.geometry import shape

from config import BOUNDARIES_DIR, DATA_DIR, STATISTICAL_ALPHA
from acquisition.spatial_subset import load_region_polygon
from india_analytics import INDIA_SEASONS
from nasa_service import fetch_nasa_monthly, get_parameter_metadata
from satellite_service import fetch_satellite_monthly, is_satellite_variable
from stats_engine import (
    analyze_series,
    benjamini_hochberg_fdr,
    compute_robust_legend_range,
    mann_kendall_test,
    sens_slope,
)

TREND_MAP_CACHE_DIR = DATA_DIR / "processed" / "trend_map_cache"
_PROGRESS_STATE: dict[str, dict[str, Any]] = {}


def _season_months(season: str) -> list[int] | None:
    s = season.strip().upper()
    if s in ("", "ANNUAL", "ALL"):
        return None
    for spec in INDIA_SEASONS:
        if spec["code"] == s:
            return list(spec["months"])
    raise ValueError(f"Invalid season '{season}'. Expected one of: annual, DJF, MAM, JJAS, ON.")


def _filter_season(timestamps: list[str], values: list[float | None], months: list[int]) -> tuple[list[str], list[float | None]]:
    """Aggregate monthly series into annual seasonal means for the requested season months."""
    yr_buckets: dict[int, list[float]] = {}
    for ts, val in zip(timestamps, values):
        if val is None or not np.isfinite(float(val)) or float(val) <= -990.0:
            continue
        s = str(ts).strip()
        if len(s) >= 7 and s[:4].isdigit() and s[5:7].isdigit():
            yr = int(s[:4])
            mo = int(s[5:7])
            if mo in months:
                # For DJF, Dec belongs to the following year's winter
                eff_yr = yr + 1 if (months == [12, 1, 2] and mo == 12) else yr
                yr_buckets.setdefault(eff_yr, []).append(float(val))

    out_ts = []
    out_vals = []
    for yr in sorted(yr_buckets.keys()):
        out_ts.append(f"{yr:04d}-01")
        out_vals.append(round(float(np.mean(yr_buckets[yr])), 5))
    return out_ts, out_vals


def _compute_region_trend_from_series(
    timestamps: list[str],
    values: list[float | None],
    season: str,
) -> dict[str, Any]:
    months = _season_months(season)
    if months is None:
        res = analyze_series(timestamps, values, mk_variant="hamed_rao")
        st = res["primary_stats"]
        return {
            "sen_slope_per_decade": st["sens_slope_per_decade"],
            "ci_lower": round(float(st["sens_slope_ci_lower"]) * 10.0, 4),
            "ci_upper": round(float(st["sens_slope_ci_upper"]) * 10.0, 4),
            "p_value": st["p_value"],
            "n_obs": st["observation_months"],
        }

    s_ts, s_vals = _filter_season(timestamps, values, months)
    if len(s_vals) < 6:
        raise ValueError(f"Insufficient seasonal years ({len(s_vals)}) for season {season}.")
    arr = np.asarray(s_vals, dtype=float)
    mk = mann_kendall_test(arr, variant="hamed_rao")
    sen = sens_slope(arr)
    slope_yr = float(sen["sens_slope_per_month"])
    return {
        "sen_slope_per_decade": round(slope_yr * 10.0, 4),
        "ci_lower": round(float(sen["sens_slope_ci_lower"]) / 12.0 * 10.0, 4),
        "ci_upper": round(float(sen["sens_slope_ci_upper"]) / 12.0 * 10.0, 4),
        "p_value": round(float(mk["p_value"]), 6),
        "n_obs": len(s_vals),
    }


def _load_level_features(level: str) -> list[dict[str, Any]]:
    lvl = level.strip().lower()
    if lvl == "state":
        path = BOUNDARIES_DIR / "states" / "india_states.geojson"
    elif lvl == "district":
        path = BOUNDARIES_DIR / "districts" / "india_districts.geojson"
        if not path.exists():
            path = BOUNDARIES_DIR / "districts" / "india_sample_districts.geojson"
    else:
        raise ValueError("level must be 'state' or 'district'.")

    fc = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for feat in fc.get("features", []):
        props = feat.get("properties", {})
        geom = shape(feat["geometry"])
        rep = geom.representative_point()
        out.append({
            "region_id": props.get("region_id"),
            "name": props.get("name"),
            "state": props.get("state", props.get("name")),
            "zone": props.get("zone", "india"),
            "lat": round(float(rep.y), 3),
            "lon": round(float(rep.x), 3),
        })
    return out


def get_trend_map_progress(cache_id: str) -> dict[str, Any]:
    return _PROGRESS_STATE.get(cache_id, {"cache_id": cache_id, "status": "idle", "completed": 0, "total": 0})


async def compute_india_trend_map(
    *,
    variable: str,
    level: str = "state",
    start_year: int = 1990,
    end_year: int = 2025,
    season: str = "annual",
) -> dict[str, Any]:
    """
    Compute regional Sen's slope, 95% CI, Hamed-Rao MK p-value, and Benjamini-Hochberg FDR
    across every Indian state/UT (or district), plus data-driven legend range and opposite trends.
    """
    var_clean = variable.strip()
    lvl = level.strip().lower()
    seas = season.strip().upper() if season.strip().lower() != "annual" else "annual"
    _season_months(seas)

    TREND_MAP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe_var = re.sub(r"[^a-zA-Z0-9._-]+", "_", var_clean)
    cache_id = f"{safe_var}_{lvl}_{start_year}_{end_year}_{seas}"
    cache_path = TREND_MAP_CACHE_DIR / f"{cache_id}.json"

    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(cached, dict) and cached.get("regions"):
                cached["cached"] = True
                return cached
        except Exception:
            pass

    features = _load_level_features(lvl)
    total = len(features)
    _PROGRESS_STATE[cache_id] = {"cache_id": cache_id, "status": "running", "completed": 0, "total": total}

    sem = asyncio.Semaphore(8)
    meta = get_parameter_metadata(var_clean)

    # For district level (753 districts), group onto 0.5-deg MERRA-2 grid cells so we fetch unique grid cells
    # rather than issuing 753 redundant identical NASA POWER requests for the same 0.5-deg cell.
    grid_series_cache: dict[tuple[float, float], dict[str, Any]] = {}

    async def _fetch_grid_cell(lat: float, lon: float) -> dict[str, Any] | None:
        g_lat = round(round(lat * 2.0) / 2.0, 2)
        g_lon = round(round(lon * 2.0) / 2.0, 2)
        key = (g_lat, g_lon)
        if key in grid_series_cache:
            return grid_series_cache[key]
        async with sem:
            try:
                if is_satellite_variable(var_clean):
                    res = await fetch_satellite_monthly(
                        dataset_id=var_clean,
                        start_year=start_year,
                        end_year=end_year,
                        lat=g_lat,
                        lon=g_lon,
                    )
                else:
                    res = await fetch_nasa_monthly(
                        g_lat,
                        g_lon,
                        parameter=var_clean.upper(),
                        start_year=start_year,
                        end_year=end_year,
                    )
                grid_series_cache[key] = res
                return res
            except Exception:
                return None

    # Pre-warm unique grid cells in parallel batches
    unique_keys = {
        (round(round(f["lat"] * 2.0) / 2.0, 2), round(round(f["lon"] * 2.0) / 2.0, 2))
        for f in features
    }
    await asyncio.gather(*[_fetch_grid_cell(la, lo) for la, lo in unique_keys])

    region_rows: list[dict[str, Any]] = []
    p_values: list[float | None] = []
    slopes: list[float | None] = []

    for idx, feat in enumerate(features):
        g_key = (round(round(feat["lat"] * 2.0) / 2.0, 2), round(round(feat["lon"] * 2.0) / 2.0, 2))
        series = grid_series_cache.get(g_key)
        if not series or not series.get("timestamps"):
            region_rows.append({
                **feat,
                "sen_slope_per_decade": None,
                "ci_lower": None,
                "ci_upper": None,
                "p_value": None,
                "fdr_q_value": None,
                "significant_fdr": False,
                "n_obs": 0,
                "status": "unavailable",
            })
            p_values.append(None)
            slopes.append(None)
        else:
            try:
                tr = _compute_region_trend_from_series(series["timestamps"], series["values"], seas)
                region_rows.append({
                    **feat,
                    **tr,
                    "fdr_q_value": None,
                    "significant_fdr": False,
                    "status": series.get("data_status", "live"),
                })
                p_values.append(tr["p_value"])
                slopes.append(tr["sen_slope_per_decade"])
            except Exception:
                region_rows.append({
                    **feat,
                    "sen_slope_per_decade": None,
                    "ci_lower": None,
                    "ci_upper": None,
                    "p_value": None,
                    "fdr_q_value": None,
                    "significant_fdr": False,
                    "n_obs": 0,
                    "status": "insufficient_data",
                })
                p_values.append(None)
                slopes.append(None)

        _PROGRESS_STATE[cache_id]["completed"] = idx + 1

    fdr = benjamini_hochberg_fdr(p_values, alpha=STATISTICAL_ALPHA)
    for row, qv, sig in zip(region_rows, fdr["q_values"], fdr["significant_fdr"]):
        row["fdr_q_value"] = qv
        row["significant_fdr"] = sig

    legend_range = compute_robust_legend_range(slopes, percentile=95.0)

    sig_pos = sorted(
        [r for r in region_rows if r["significant_fdr"] and (r["sen_slope_per_decade"] or 0.0) > 0],
        key=lambda r: float(r["sen_slope_per_decade"]),
        reverse=True,
    )[:5]
    sig_neg = sorted(
        [r for r in region_rows if r["significant_fdr"] and (r["sen_slope_per_decade"] or 0.0) < 0],
        key=lambda r: float(r["sen_slope_per_decade"]),
    )[:5]

    payload: dict[str, Any] = {
        "cache_id": cache_id,
        "variable": var_clean,
        "variable_name": meta.get("parameter_name", var_clean),
        "units": meta.get("unit") or meta.get("units", "units"),
        "source_badge": meta.get("source_badge", "Model: NASA POWER / MERRA-2"),
        "source_type": meta.get("source_type", "model/reanalysis"),
        "level": lvl,
        "start_year": start_year,
        "end_year": end_year,
        "season": seas,
        "alpha": STATISTICAL_ALPHA,
        "fdr_method": "Benjamini-Hochberg (1995)",
        "mk_method": "Mann-Kendall with Hamed-Rao (1998) autocorrelation correction",
        "total_regions": total,
        "valid_regions": fdr["m_tests"],
        "significant_regions_count": sum(1 for r in region_rows if r["significant_fdr"]),
        "legend_range": legend_range,
        "opposite_trends": {
            "top_positive": sig_pos,
            "top_negative": sig_neg,
        },
        "regions": region_rows,
        "progress": {"status": "done", "completed": total, "total": total},
        "cached": False,
    }
    _PROGRESS_STATE[cache_id] = {"cache_id": cache_id, "status": "done", "completed": total, "total": total}
    if fdr["m_tests"] > 0:
        cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
