"""India-exclusive physiographic regions, IMD 4-season trend analysis, anomaly detection, and Holm-Bonferroni correction."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import linregress

from stats_engine import _clean_float, mann_kendall_test, sens_slope

INDIA_SEASONS: list[dict[str, Any]] = [
    {"code": "JF", "name": "Winter (Jan–Feb)", "months": [1, 2]},
    {"code": "MAM", "name": "Pre-Monsoon (Mar–May)", "months": [3, 4, 5]},
    {"code": "JJAS", "name": "Southwest Monsoon (Jun–Sep)", "months": [6, 7, 8, 9]},
    {"code": "OND", "name": "Post-Monsoon (Oct–Dec)", "months": [10, 11, 12]},
]

INDIA_PHYSIOGRAPHIC_REGIONS: list[dict[str, Any]] = [
    {
        "region_id": "himalaya",
        "name": "Himalayan Region",
        "representative_point": {"name": "Leh / Ladakh (Western Himalaya)", "lat": 34.15, "lon": 77.58},
        "zone_mapping": "north",
        "climate_profile": "High-altitude cold arid & alpine cryosphere; strong elevation-dependent warming sensitivity.",
        "key_datasets": ["MOD11C3 (LST)", "MERRA-2 T2M", "AIRS", "GRACE-FO"],
    },
    {
        "region_id": "igp",
        "name": "Indo-Gangetic Plains",
        "representative_point": {"name": "Lucknow / Central IGP", "lat": 26.85, "lon": 80.95},
        "zone_mapping": "north",
        "climate_profile": "Intensively cultivated alluvial plain; winter aerosol/CO haze, summer heatwaves, groundwater extraction.",
        "key_datasets": ["MOP03JM (CO)", "MOD08_M3 (AOD)", "GRACE-FO (TWS)", "MOD13C2 (NDVI)"],
    },
    {
        "region_id": "thar",
        "name": "Thar Desert & Arid West",
        "representative_point": {"name": "Jaisalmer / Western Rajasthan", "lat": 26.91, "lon": 70.91},
        "zone_mapping": "west",
        "climate_profile": "Hyper-arid subtropical desert; extreme pre-monsoon temperatures and dust aerosol loading.",
        "key_datasets": ["SMAP SPL3SMP_E", "MOD11C3 (LST)", "MERRA-2 Dust AOD"],
    },
    {
        "region_id": "central_plateau",
        "name": "Central Indian Plateau",
        "representative_point": {"name": "Nagpur / Vidarbha-Satpura", "lat": 21.15, "lon": 79.09},
        "zone_mapping": "central",
        "climate_profile": "Monsoon-dependent rainfed agriculture and dry deciduous forest; intense MAM heat stress.",
        "key_datasets": ["GPM_3IMERGM", "GLDAS_NOAH025_M", "MOD13C2 (NDVI)"],
    },
    {
        "region_id": "western_ghats",
        "name": "Western Ghats",
        "representative_point": {"name": "Thrissur / Malabar Escarpment", "lat": 10.52, "lon": 76.21},
        "zone_mapping": "south",
        "climate_profile": "Orographic Southwest Monsoon barrier, tropical evergreen forests, intense JJAS precipitation.",
        "key_datasets": ["GPM_3IMERGM", "MOD13C2 (EVI)", "MOD17A2HGF (GPP)"],
    },
    {
        "region_id": "eastern_ghats",
        "name": "Eastern Ghats",
        "representative_point": {"name": "Visakhapatnam / Eastern Escarpment", "lat": 17.69, "lon": 83.22},
        "zone_mapping": "south",
        "climate_profile": "Discontinuous coastal ranges influenced by both JJAS and Bay of Bengal post-monsoon cyclones.",
        "key_datasets": ["GPM_3IMERGM", "MOD11C3 (LST)", "MERRA-2 T2M"],
    },
    {
        "region_id": "coastal_india",
        "name": "Coastal Regions of India",
        "representative_point": {"name": "Bhubaneswar / Odisha-Bengal Coast", "lat": 20.30, "lon": 85.82},
        "zone_mapping": "east",
        "climate_profile": "Humid maritime climate, deltaic ecosystems, cyclone-driven post-monsoon precipitation extremes.",
        "key_datasets": ["NASA POWER T2M/RH", "GPM_3IMERGM", "MERRA-2 M2TMNXLND"],
    },
    {
        "region_id": "deccan_plateau",
        "name": "Deccan Plateau",
        "representative_point": {"name": "Aurangabad / Marathwada", "lat": 19.88, "lon": 75.34},
        "zone_mapping": "west",
        "climate_profile": "Semi-arid rain-shadow plateau east of the Western Ghats; recurring agricultural drought sensitivity.",
        "key_datasets": ["GLDAS_NOAH025_M (RZSM)", "SMAP SPL3SMP_E", "GPM_3IMERGM"],
    },
    {
        "region_id": "northeast",
        "name": "Northeastern India",
        "representative_point": {"name": "Shillong / Meghalaya Hills", "lat": 25.57, "lon": 91.89},
        "zone_mapping": "northeast",
        "climate_profile": "Orographic Bay of Bengal moisture convergence, biodiversity hotspot, high pre-monsoon & JJAS rainfall.",
        "key_datasets": ["GPM_3IMERGM", "MOD13C2 (NDVI)", "MERRA-2 ET"],
    },
    {
        "region_id": "river_basins",
        "name": "Major River Basins (Ganga–Indus–Godavari)",
        "representative_point": {"name": "Patna / Lower Ganga Basin", "lat": 25.59, "lon": 85.14},
        "zone_mapping": "east",
        "climate_profile": "Alluvial river corridors linking Himalayan snowmelt, monsoon runoff, and basin-scale groundwater storage.",
        "key_datasets": ["GRACE-FO (TWS)", "GLDAS Runoff", "GPM_3IMERGM"],
    },
]


def _holm_bonferroni(p_values: list[float]) -> list[float]:
    """Compute Holm-Bonferroni step-down adjusted p-values for multiple hypothesis testing."""
    m = len(p_values)
    if m == 0:
        return []
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    adjusted = [0.0] * m
    running_max = 0.0
    for rank, (orig_idx, p_val) in enumerate(indexed):
        adj = min(1.0, p_val * (m - rank))
        running_max = max(running_max, adj)
        adjusted[orig_idx] = round(running_max, 5)
    return adjusted


def _lag1_autocorr(arr: np.ndarray) -> float | None:
    if len(arr) < 4 or np.nanstd(arr) < 1e-12:
        return None
    x = arr[:-1] - np.mean(arr[:-1])
    y = arr[1:] - np.mean(arr[1:])
    denom = float(np.sqrt(np.sum(x * x) * np.sum(y * y)))
    if denom < 1e-12:
        return None
    return _clean_float(float(np.sum(x * y) / denom), 4)


def analyze_india_seasons(
    timestamps: list[str],
    values: list[float | None],
    *,
    baseline_start: int = 1991,
    baseline_end: int = 2020,
) -> dict[str, Any]:
    """Compute EDA, 4-season IMD trends (JF, MAM, JJAS, OND), OLS, MK, Sen's slope, Holm-Bonferroni, and anomalies."""
    if len(timestamps) != len(values) or len(timestamps) < 24:
        raise ValueError("At least 24 monthly observations with matching timestamps are required.")

    df = pd.DataFrame({"ts": pd.to_datetime(timestamps, errors="coerce"), "val": pd.to_numeric(values, errors="coerce")})
    df = df.dropna(subset=["ts", "val"]).sort_values("ts")
    df = df[df["val"] > -990.0]
    if len(df) < 24:
        raise ValueError("Insufficient valid observations after filtering missing values.")

    df["year"] = df["ts"].dt.year
    df["month"] = df["ts"].dt.month

    vals_np = df["val"].to_numpy(dtype=float)
    q25, q75 = np.percentile(vals_np, [25, 75])
    n_total = len(timestamps)
    n_valid = int(len(df))
    eda = {
        "n_total": n_total,
        "n_valid": n_valid,
        "n_months": n_valid,
        "missing_pct": _clean_float(100.0 * (n_total - n_valid) / n_total if n_total else 0.0, 2),
        "start_year": int(df["year"].min()),
        "end_year": int(df["year"].max()),
        "start_date": df["ts"].min().strftime("%Y-%m"),
        "end_date": df["ts"].max().strftime("%Y-%m"),
        "mean": _clean_float(float(np.mean(vals_np))),
        "std": _clean_float(float(np.std(vals_np, ddof=1))),
        "median": _clean_float(float(np.median(vals_np))),
        "iqr": _clean_float(float(q75 - q25)),
        "min": _clean_float(float(np.min(vals_np))),
        "max": _clean_float(float(np.max(vals_np))),
    }

    seasonal_results: list[dict[str, Any]] = []
    raw_p_values: list[float] = []

    for s_spec in INDIA_SEASONS:
        sub = df[df["month"].isin(s_spec["months"])]
        yr_means = sub.groupby("year")["val"].mean().sort_index()
        years = yr_means.index.to_numpy(dtype=float)
        y_vals = yr_means.to_numpy(dtype=float)

        if len(y_vals) >= 4:
            mk = mann_kendall_test(y_vals)
            sen = sens_slope(y_vals)
            slope_yr = float(sen["sens_slope_per_month"])
            ci_lo = float(sen["sens_slope_ci_lower"]) / 12.0
            ci_hi = float(sen["sens_slope_ci_upper"]) / 12.0
            lr = linregress(years, y_vals)
            ols_slope = float(lr.slope)
            ols_r2 = float(lr.rvalue ** 2)
            ols_p = float(lr.pvalue)
            r1 = _lag1_autocorr(y_vals)
            p_mk = float(mk["p_value"])
        else:
            mk = {"tau": 0.0, "p_value": 1.0, "s_stat": 0}
            slope_yr, ci_lo, ci_hi = 0.0, 0.0, 0.0
            ols_slope, ols_r2, ols_p, r1, p_mk = 0.0, 0.0, 1.0, None, 1.0

        raw_p_values.append(p_mk)
        seasonal_results.append(
            {
                "code": s_spec["code"],
                "name": s_spec["name"],
                "months": s_spec["months"],
                "n_years": int(len(y_vals)),
                "mean_value": _clean_float(float(np.mean(y_vals))) if len(y_vals) else None,
                "std_value": _clean_float(float(np.std(y_vals, ddof=1))) if len(y_vals) > 1 else None,
                "sen_slope_per_year": _clean_float(slope_yr, 5),
                "sen_slope_per_decade": _clean_float(slope_yr * 10.0, 4),
                "sens_ci_lower": _clean_float(ci_lo, 5),
                "sens_ci_upper": _clean_float(ci_hi, 5),
                "ols_slope_per_decade": _clean_float(ols_slope * 10.0, 4),
                "r_squared": _clean_float(ols_r2, 4),
                "ols_p_value": _clean_float(ols_p, 5),
                "mk_tau": _clean_float(mk["tau"], 4),
                "mk_p_value": _clean_float(p_mk, 5),
                "lag1_autocorr": r1,
                "direction": "increasing" if slope_yr > 0 else ("decreasing" if slope_yr < 0 else "stable"),
            }
        )

    holm_p = _holm_bonferroni(raw_p_values)
    seasons_dict: dict[str, dict[str, Any]] = {}
    for item, hp in zip(seasonal_results, holm_p):
        item["holm_adjusted_p"] = hp
        item["significant_unadjusted"] = bool((item["mk_p_value"] or 1.0) < 0.05)
        item["significant_holm"] = bool(hp < 0.05)
        seasons_dict[item["code"]] = item

    # Annual anomaly series vs 1991-2020 climatology baseline (or full period if <10 baseline years)
    ann = df.groupby("year")["val"].mean().sort_index()
    base_slice = ann[(ann.index >= baseline_start) & (ann.index <= baseline_end)]
    if len(base_slice) < 10:
        base_slice = ann
    base_mean = float(base_slice.mean())
    base_std = float(base_slice.std(ddof=1)) if len(base_slice) > 1 else 1.0
    if base_std < 1e-12:
        base_std = 1.0

    anomalies = [
        {
            "year": int(yr),
            "annual_mean": _clean_float(float(val), 4),
            "anomaly": _clean_float(float(val - base_mean), 4),
            "z_score": _clean_float(float((val - base_mean) / base_std), 3),
        }
        for yr, val in ann.items()
    ]
    sorted_anom = sorted(anomalies, key=lambda x: x["anomaly"] or 0.0, reverse=True)
    return {
        "eda": eda,
        "seasons": seasons_dict,
        "baseline_period": f"{int(base_slice.index.min())}–{int(base_slice.index.max())}",
        "baseline_mean": _clean_float(base_mean, 4),
        "annual_anomalies": anomalies,
        "top_positive_years": sorted_anom[:3],
        "top_negative_years": list(reversed(sorted_anom[-3:])),
    }
