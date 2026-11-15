import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from india_analytics import analyze_india_seasons
from main import app
from nasa_service import is_within_india_bounds

client = TestClient(app)


def test_india_bounds_validation():
    assert is_within_india_bounds(22.5, 82.0) is True
    assert is_within_india_bounds(34.15, 77.58) is True  # Leh
    assert is_within_india_bounds(10.52, 76.21) is True  # Thrissur
    assert is_within_india_bounds(51.5, -0.1) is False   # London
    assert is_within_india_bounds(-3.46, -62.21) is False  # Amazon


def test_investigate_rejects_non_india_coordinates():
    resp = client.post(
        "/api/investigate",
        json={
            "parameter": "T2M",
            "primary_point": {"name": "London", "lat": 51.50, "lon": -0.12},
            "start_year": 1995,
            "end_year": 2024,
        },
    )
    assert resp.status_code == 422
    assert "India" in resp.json()["detail"]


def test_analyze_india_seasons_computation():
    timestamps = []
    values = []
    for yr in range(1991, 2025):
        for mo in range(1, 13):
            timestamps.append(f"{yr:04d}-{mo:02d}-01")
            # Warm pre-monsoon (MAM) trend + seasonal cycle
            base = 24.0 + 4.0 * (1 if mo in (4, 5, 6) else 0)
            trend = 0.04 * (yr - 1991) if mo in (3, 4, 5) else 0.01 * (yr - 1991)
            values.append(base + trend)

    res = analyze_india_seasons(timestamps, values, baseline_start=1991, baseline_end=2020)
    assert res["eda"]["n_valid"] == len(timestamps)
    assert set(res["seasons"].keys()) == {"DJF", "MAM", "JJAS", "ON"}
    mam = res["seasons"]["MAM"]
    assert mam["sen_slope_per_decade"] > 0.35
    assert mam["significant_holm"] is True
    assert len(res["annual_anomalies"]) == 34
    assert len(res["top_positive_years"]) > 0
    assert len(res["top_negative_years"]) > 0


def test_india_api_endpoints():
    r_reg = client.get("/api/india/regions")
    assert r_reg.status_code == 200
    reg_body = r_reg.json()
    assert len(reg_body["physiographic_regions"]) == 10
    assert set(reg_body["seasons"].keys()) == {"DJF", "MAM", "JJAS", "ON"}

    r_geo = client.get("/api/india/boundaries-geojson")
    assert r_geo.status_code == 200
    assert r_geo.json()["type"] in ("FeatureCollection", "Feature")

    r_seas = client.post(
        "/api/india/seasonal-analysis",
        json={"case_id": "case_2_himalaya", "start_year": 1990, "end_year": 2025},
    )
    assert r_seas.status_code == 200
    seas_body = r_seas.json()
    assert seas_body["meta"]["parameter"] == "T2M"
    assert set(seas_body["analysis"]["seasons"].keys()) == {"DJF", "MAM", "JJAS", "ON"}

    r_comp = client.get("/api/india/regional-comparison?start_year=1990&end_year=2025")
    assert r_comp.status_code == 200
    comp_body = r_comp.json()
    assert comp_body["count"] == 12
    assert len(comp_body["rows"]) == 12
