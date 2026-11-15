"""Integration and regression test suite for TerraShift FastAPI API contract, CORS, and data routes."""

from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_root_and_health_endpoints(client):
    """Test root and liveness/readiness health & status endpoints."""
    # 1. Root /
    root_resp = client.get("/")
    assert root_resp.status_code == 200
    root_data = root_resp.json()
    assert root_data["status"] == "ok"
    assert root_data["service"] == "TerraShift API"
    assert "/api/health" in root_data["health"]

    # 2. Readiness /api/health and lightweight liveness /health
    h_resp = client.get("/api/health")
    assert h_resp.status_code == 200
    h_data = h_resp.json()
    assert h_data["status"] == "ok"
    assert h_data["service"] == "TerraShift API"
    assert h_data["version"] == "2.0.0"
    assert h_data["cache_available"] is True
    assert "timestamp" in h_data

    liveness_resp = client.get("/health")
    assert liveness_resp.status_code == 200
    assert liveness_resp.json() == {"status": "ok"}

    # 3. Diagnostic /api/status
    s_resp = client.get("/api/status")
    assert s_resp.status_code == 200
    s_data = s_resp.json()
    assert s_data["status"] == "ok"
    assert s_data["cases_count"] == 6
    assert s_data["live_cache_count"] >= 0
    assert len(s_data["parameters"]) == 6
    assert "T2M" in s_data["parameters"]


def test_cors_preflight_and_headers(client):
    """Verify CORS headers for browser requests from frontend development origin."""
    response = client.options(
        "/api/investigate",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") in ("*", "http://localhost:5173")


def test_validation_errors_structured_format(client):
    """Ensure malformed requests produce structured 422 responses with readable details."""
    # Mismatched timestamps and values
    resp = client.post(
        "/api/analyze",
        json={"timestamps": ["2020-01", "2020-02"], "values": [1.0]},
    )
    assert resp.status_code == 422
    err_body = resp.json()
    assert err_body["error"] is True
    assert "detail" in err_body
    assert "timestamps and values must have identical lengths" in err_body["detail"]

    # start_year >= end_year in investigate request
    resp2 = client.post(
        "/api/investigate",
        json={
            "parameter": "T2M",
            "primary_point": {"name": "Test", "lat": 10.0, "lon": 10.0},
            "start_year": 2020,
            "end_year": 2015,
        },
    )
    assert resp2.status_code == 422
    assert "start_year must be strictly less than end_year" in resp2.json()["detail"]

    # Invalid latitude out of bounds
    resp3 = client.post(
        "/api/investigate",
        json={
            "parameter": "T2M",
            "primary_point": {"name": "Test", "lat": 95.0, "lon": 10.0},
            "start_year": 1990,
            "end_year": 2020,
        },
    )
    assert resp3.status_code == 422


def test_cases_detail_with_custom_window(client):
    """Verify GET /api/cases/{case_id} supports window slicing query params."""
    resp = client.get("/api/cases/case_1_monsoon?start_year=1995&end_year=2015")
    assert resp.status_code == 200
    data = resp.json()
    req = data["request"]
    assert req["start_year"] == 1995
    assert req["end_year"] == 2015
    series = data["response"]["primary_series"]
    assert series["timestamps"][0] == "1995-01"
    assert series["timestamps"][-1] == "2015-12"
    assert len(series["timestamps"]) == 21 * 12

    # 404 for non-existent case
    resp404 = client.get("/api/cases/unknown_case_id")
    assert resp404.status_code == 404


def test_import_series_with_window_slicing(client):
    """Test /api/import-series with optional window filtering."""
    # Synthetic Giovanni CSV
    rows = ["# NASA Giovanni Series", "time,precip"]
    for yr in range(1995, 2025):
        for mo in range(1, 13):
            val = 2.0 + 0.05 * (yr - 1995) + 1.2 * np.sin(2 * np.pi * mo / 12.0)
            rows.append(f"{yr:04d}-{mo:02d}-01,{val:.3f}")

    # Import with window sliced to 2000-2015
    resp = client.post(
        "/api/import-series",
        json={
            "raw_text": "\n".join(rows),
            "source_hint": "NASA Giovanni",
            "region_name": "Tropical Basin",
            "start_year": 2000,
            "end_year": 2015,
            "unit": "mm/day",
        },
    )
    assert resp.status_code == 200
    res = resp.json()["response"]
    assert res["primary_series"]["timestamps"][0] == "2000-01"
    assert res["primary_series"]["timestamps"][-1] == "2015-12"
    assert len(res["primary_series"]["timestamps"]) == 16 * 12
    assert res["primary_stats"]["observation_months"] == 16 * 12


def test_partner_intel_query_validation(client):
    """Verify partner intel query validation on start_year < end_year."""
    resp = client.get("/api/partner-intel?lat=45.0&lon=-75.0&parameter=T2M&start_year=2025&end_year=2010")
    assert resp.status_code == 400
    assert "start_year must be strictly less than end_year" in resp.json()["detail"]
