"""Comprehensive tests for TerraShift India-only upgrade (Items 1-8)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ---------------------------------------------------------------------------
# ITEM 1: Satellite variables registry + scaling/fill/QA parsing
# ---------------------------------------------------------------------------


def test_satellite_registry_has_at_least_three_satellite_variables():
    from acquisition.dataset_registry import get_satellite_trend_variables, get_trend_variable_registry

    sat_vars = get_satellite_trend_variables()
    sat_ids = {v["id"] for v in sat_vars}
    assert {"MOD13C2", "GPM_3IMERGM", "OMNO2d"}.issubset(sat_ids)
    assert len(sat_vars) >= 3
    for item in get_trend_variable_registry():
        assert item["doi"]
        assert item["units"]
        assert item["plain_definition"]
        assert item["source_type"] in {"satellite", "model/reanalysis"}


def test_parse_and_scale_four_satellite_datasets():
    from acquisition.dataset_registry import parse_and_scale_satellite_series

    # MOD13C2: scale 0.0001, fill -3000, QA bits 0-1 == 3 -> masked
    ndvi = parse_and_scale_satellite_series(
        "MOD13C2",
        [5000, -3000, 6200, 4000],
        qa_flags=[0, 0, 3, 1],
    )
    assert ndvi[0] == pytest.approx(0.5)
    assert ndvi[1] is None
    assert ndvi[2] is None
    assert ndvi[3] == pytest.approx(0.4)

    # GPM_3IMERGM: fill -9999.9, valid mm/day
    gpm = parse_and_scale_satellite_series("GPM_3IMERGM", [0.5, -9999.9, -1.0, 12.5])
    assert gpm[0] == pytest.approx(0.5)
    assert gpm[1] is None
    assert gpm[2] is None
    assert gpm[3] == pytest.approx(12.5)

    # OMNO2d: fill -1.26765e30, molecules/cm2 -> 1e15 molec/cm2
    no2 = parse_and_scale_satellite_series("OMNO2d", [4.5e15, -1.26765e30, -5.0])
    assert no2[0] == pytest.approx(4.5)
    assert no2[1] is None
    assert no2[2] is None

    # MOD11C3: scale 0.02 K -> Celsius (- 273.15), fill 0
    lst = parse_and_scale_satellite_series("MOD11C3", [15000, 0, 15157], qa_flags=[0, 0, 0])
    assert lst[0] == pytest.approx(300.0 - 273.15)
    assert lst[1] is None
    assert lst[2] == pytest.approx(15157 * 0.02 - 273.15)


# ---------------------------------------------------------------------------
# ITEM 2: Polygon masking, cos(lat) area weighting & /api/investigate contract
# ---------------------------------------------------------------------------


def test_polygon_sample_and_cos_lat_area_weighting():
    from acquisition.spatial_subset import compute_area_weighted_series, sample_polygon_grid_points

    sampled = sample_polygon_grid_points("state_rajasthan", resolution_deg=0.5, max_api_points=25)
    assert sampled["grid_cells_used"] >= 3
    assert len(sampled["sampled_points"]) >= 3

    # cos(lat) weighting test with known values
    cell_series = [
        {"lat": 0.0, "lon": 75.0, "timestamps": ["2020-01", "2020-02"], "values": [10.0, 20.0]},
        {"lat": 60.0, "lon": 75.0, "timestamps": ["2020-01", "2020-02"], "values": [4.0, 8.0]},
    ]
    weighted = compute_area_weighted_series(cell_series)
    # (10*1 + 4*0.5) / 1.5 = 12 / 1.5 = 8.0; (20*1 + 8*0.5) / 1.5 = 24 / 1.5 = 16.0
    assert weighted["values"][0] == pytest.approx(8.0)
    assert weighted["values"][1] == pytest.approx(16.0)


def test_investigate_endpoint_point_and_region_contract(monkeypatch):
    from fastapi.testclient import TestClient
    import main as backend_main

    timestamps = [f"{yr:04d}-{mo:02d}" for yr in range(2005, 2025) for mo in range(1, 13)]
    values = [25.0 + 0.03 * i / 12.0 + 3.0 * float(np.sin(2 * np.pi * (i % 12) / 12)) for i in range(len(timestamps))]

    async def fake_power_point(lat, lon, param, start_year, end_year):
        return {
            "timestamps": timestamps,
            "values": values,
            "data_status": "cache",
            "bounding_box": {"south": lat - 0.25, "north": lat + 0.25, "west": lon - 0.3, "east": lon + 0.3},
            "provenance": {
                "source": "NASA POWER / MERRA-2",
                "collection": "POWER",
                "data_type": "reanalysis",
                "community": "AG",
                "parameter": param,
                "parameter_name": "2m Air Temp",
                "units": "°C",
                "temporal_resolution": "Monthly",
                "spatial_resolution": "0.5°x0.625°",
                "requested_coordinates": {"lat": lat, "lon": lon},
                "actual_coordinates": {"lat": lat, "lon": lon},
                "retrieval_status": "cached",
                "dataset_tag": "cached",
                "fallback_used": False,
                "fallback_distance_km": 0.0,
                "is_synthetic": False,
            },
        }

    async def fake_power_region(region_id, parameter, start_year, end_year):
        base = await fake_power_point(26.9, 73.8, parameter, start_year, end_year)
        base["region_coverage"] = {
            "region_id": region_id,
            "region_name": "Rajasthan",
            "grid_cells_used": 12,
            "area_covered_pct": 94.5,
            "weighting": "cos(latitude)",
        }
        base["quality_flags"] = ["Arid/semi-arid region: check dust/irrigation artifacts"]
        return base

    monkeypatch.setattr(backend_main, "fetch_nasa_monthly", fake_power_point)
    monkeypatch.setattr(backend_main, "fetch_region_power_monthly", fake_power_region)

    client = TestClient(backend_main.app)
    # Point mode
    r1 = client.post(
        "/api/investigate",
        json={
            "parameter": "T2M",
            "primary_point": {"name": "Jaipur", "lat": 26.9, "lon": 75.8},
            "start_year": 2005,
            "end_year": 2024,
        },
    )
    assert r1.status_code == 200
    assert r1.json()["response"]["source_type"] == "model/reanalysis"

    # Region mode
    r2 = client.post(
        "/api/investigate",
        json={
            "parameter": "T2M",
            "region_type": "state",
            "region_id": "state_rajasthan",
            "start_year": 2005,
            "end_year": 2024,
        },
    )
    assert r2.status_code == 200
    body2 = r2.json()["response"]
    assert body2["region_coverage"]["grid_cells_used"] == 12
    assert body2["region_coverage"]["weighting"] == "cos(latitude)"


# ---------------------------------------------------------------------------
# ITEM 3: Current 36 Indian States/UTs & District Parent Mapping
# ---------------------------------------------------------------------------


def test_india_boundaries_36_states_and_districts_valid():
    states_path = REPO_ROOT / "data" / "boundaries" / "states" / "india_states.geojson"
    districts_path = REPO_ROOT / "data" / "boundaries" / "districts" / "india_districts.geojson"
    states = json.loads(states_path.read_text(encoding="utf-8"))
    districts = json.loads(districts_path.read_text(encoding="utf-8"))

    assert len(states["features"]) == 36
    names = {f["properties"]["name"] for f in states["features"]}
    state_ids = {f["properties"]["region_id"] for f in states["features"]}

    assert "Odisha" in names
    assert "Uttarakhand" in names
    assert "Telangana" in names
    assert "Ladakh" in names
    assert "Jammu and Kashmir" in names
    assert "Dadra and Nagar Haveli and Daman and Diu" in names
    assert "Andaman and Nicobar Islands" in names
    assert "Orissa" not in names
    assert "Uttaranchal" not in names

    assert len(districts["features"]) >= 700
    for feat in districts["features"]:
        props = feat["properties"]
        assert props.get("parent_state_id") in state_ids
        assert props.get("state") in names


# ---------------------------------------------------------------------------
# ITEM 4: Benjamini-Hochberg FDR, Legend Range & /api/trend-map
# ---------------------------------------------------------------------------


def test_benjamini_hochberg_fdr_and_legend_range():
    from stats_engine import benjamini_hochberg_fdr, compute_robust_legend_range

    fdr = benjamini_hochberg_fdr([0.001, 0.01, 0.04, 0.50, 0.80], alpha=0.05)
    assert fdr["q_values"][0] == pytest.approx(0.005)
    assert fdr["significant_fdr"][0] is True
    assert fdr["significant_fdr"][1] is True
    assert fdr["significant_fdr"][3] is False
    assert fdr["significant_fdr"][4] is False

    rng = compute_robust_legend_range([-0.1, 0.02, 0.04, 0.05, 5.0])
    assert rng["max"] > 0
    assert rng["min"] == pytest.approx(-rng["max"])


def test_trend_map_endpoint_contract(monkeypatch):
    from fastapi.testclient import TestClient
    import main as backend_main

    async def fake_trend_map(*, variable, level, start_year, end_year, season):
        return {
            "cache_id": "test_cache",
            "variable": variable,
            "unit": "°C",
            "source_type": "model/reanalysis",
            "mission": "NASA POWER / MERRA-2",
            "level": level,
            "start_year": start_year,
            "end_year": end_year,
            "season": season,
            "legend_range": {"min": -0.05, "max": 0.05, "symmetric_abs_p95": 0.05},
            "summary": {"total_regions": 36, "computed_regions": 36, "significant_fdr_count": 12, "fdr_alpha": 0.05},
            "opposite_trends": {"top_positive": [], "top_negative": []},
            "regions": [],
            "geojson": {"type": "FeatureCollection", "features": []},
        }

    monkeypatch.setattr(backend_main, "compute_india_trend_map", fake_trend_map)
    client = TestClient(backend_main.app)
    resp = client.get("/api/trend-map?variable=T2M&level=state&start=1990&end=2025&season=JJAS")
    assert resp.status_code == 200
    assert resp.json()["summary"]["significant_fdr_count"] == 12


# ---------------------------------------------------------------------------
# ITEM 7: AI Suggests Variables schema validation & deterministic fallback
# ---------------------------------------------------------------------------


def test_suggest_variables_validation_and_fallback(monkeypatch):
    from fastapi.testclient import TestClient
    import ai_explainer
    import main as backend_main

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = TestClient(backend_main.app)
    resp = client.get("/api/suggest-variables?region=state_rajasthan")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ai_enhanced"] is False
    assert len(body["suggestions"]) >= 3
    valid_ids = {item["id"] for item in ai_explainer.get_trend_variable_registry()}
    for s in body["suggestions"]:
        assert s["variable_id"] in valid_ids
        assert s["expected_direction"] in {"increasing", "decreasing", "variable"}

    # Unknown ID rejection
    validated = ai_explainer.validate_suggested_variables(
        [
            {"variable_id": "FAKE_VAR_999", "reason": "bad", "expected_direction": "increasing"},
            {"variable_id": "MOD13C2", "reason": "tracks vegetation", "expected_direction": "increasing"},
        ],
        {item["id"]: item for item in ai_explainer.get_trend_variable_registry()},
    )
    assert len(validated) == 1
    assert validated[0]["variable_id"] == "MOD13C2"


# ---------------------------------------------------------------------------
# ITEM 8: Seasonal Mann-Kendall (Hirsch 1982)
# ---------------------------------------------------------------------------


def test_seasonal_mann_kendall_detects_monotonic_trend():
    from stats_engine import seasonal_mann_kendall_test

    timestamps = [f"{yr:04d}-{mo:02d}" for yr in range(2000, 2020) for mo in range(1, 13)]
    # Strong seasonal cycle + steady +0.10/yr upward trend
    values = [
        20.0 + 0.10 * (yr - 2000) + 8.0 * float(np.sin(2.0 * np.pi * mo / 12.0))
        for yr in range(2000, 2020)
        for mo in range(1, 13)
    ]
    res = seasonal_mann_kendall_test(timestamps, values)
    assert res["is_significant"] is True
    assert res["p_value"] < 0.001
    assert abs(res["seasonal_sens_slope_per_year"] - 0.10) < 0.01
    assert res["method"] == "Hirsch, Slack & Smith (1982) Seasonal Mann-Kendall"
