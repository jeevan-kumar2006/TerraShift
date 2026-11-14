"""Unit tests for TerraShift statistical & STL decomposition engine."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pymannkendall as mk
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from stats_engine import analyze_series, mann_kendall_test


def _make_monthly_timestamps(start_year: int, n_months: int) -> list[str]:
    ts = []
    for i in range(n_months):
        year = start_year + i // 12
        month = (i % 12) + 1
        ts.append(f"{year:04d}-{month:02d}")
    return ts


def test_synthetic_trend_with_strong_seasonality():
    rng = np.random.default_rng(42)
    n_months = 30 * 12  # 30 years
    t_years = np.arange(n_months) / 12.0
    months = np.arange(n_months) % 12
    seasonal = 4.0 * np.sin(2.0 * np.pi * months / 12.0)
    noise = rng.normal(0.0, 0.3, size=n_months)
    values = 10.0 + 0.05 * t_years + seasonal + noise
    timestamps = _make_monthly_timestamps(1995, n_months)

    result = analyze_series(timestamps, values.tolist())
    stats = result["primary_stats"]
    series = result["primary_series"]

    assert len(series["raw_values"]) == n_months
    assert len(series["seasonal_cycle"]) == n_months
    assert len(series["deseasonalized_anomalies"]) == n_months
    assert len(series["trend_line"]) == n_months
    assert len(series["ci_upper"]) == n_months
    assert len(series["ci_lower"]) == n_months

    # Seasonal swings masked raw variance, STL strips it cleanly
    assert stats["variance_reduction_pct"] > 75.0
    assert stats["is_significant"] is True
    assert stats["p_value"] < 0.05
    assert stats["t_test_p_value"] < 0.05
    assert abs(stats["sens_slope_per_year"] - 0.05) < 0.01
    assert stats["years_to_significance"] == 0


def test_short_5_year_window_needs_more_years():
    rng = np.random.default_rng(10)
    n_months = 5 * 12  # 5 years
    t_years = np.arange(n_months) / 12.0
    months = np.arange(n_months) % 12
    seasonal = 3.0 * np.cos(2.0 * np.pi * months / 12.0)
    noise = rng.normal(0.0, 0.8, size=n_months)
    values = 5.0 + 0.04 * t_years + seasonal + noise
    timestamps = _make_monthly_timestamps(2020, n_months)

    result = analyze_series(timestamps, values.tolist())
    stats = result["primary_stats"]

    assert stats["is_significant"] is False
    assert stats["p_value"] >= 0.05
    assert stats["years_to_significance"] > 0


def test_pure_noise_not_significant():
    rng = np.random.default_rng(123)
    n_months = 20 * 12
    values = 15.0 + rng.normal(0.0, 0.8, size=n_months)
    timestamps = _make_monthly_timestamps(2005, n_months)

    result = analyze_series(timestamps, values.tolist())
    stats = result["primary_stats"]

    assert stats["is_significant"] is False
    assert stats["p_value"] >= 0.05


def test_opposite_teleconnection_correlation():
    rng = np.random.default_rng(99)
    n_months = 30 * 12
    t_years = np.arange(n_months) / 12.0
    months = np.arange(n_months) % 12
    shared_oscillation = rng.normal(0.0, 0.8, size=n_months)

    primary = 5.0 + 0.04 * t_years + 2.0 * np.sin(2.0 * np.pi * months / 12.0) + shared_oscillation
    opposite = 8.0 - 0.04 * t_years + 1.5 * np.cos(2.0 * np.pi * months / 12.0) - shared_oscillation
    timestamps = _make_monthly_timestamps(1995, n_months)

    result = analyze_series(timestamps, primary.tolist(), comparison_values=opposite.tolist())
    tele = result["teleconnection"]

    assert tele["enabled"] is True
    assert tele["cross_correlation_r"] < -0.5
    assert tele["comparison_sens_slope_per_year"] < -0.02


def test_mann_kendall_matches_pymannkendall():
    rng = np.random.default_rng(2026)
    arr = 0.02 * np.arange(120) + rng.normal(0.0, 0.5, size=120)

    ours = mann_kendall_test(arr, variant="standard")
    ref = mk.original_test(arr)

    assert abs(ours["tau"] - ref.Tau) < 1e-6
    assert abs(ours["z_score"] - ref.z) < 1e-6
    assert abs(ours["p_value"] - ref.p) < 1e-6


def test_edge_cases_constant_fill_values_and_too_short():
    timestamps = _make_monthly_timestamps(2020, 36)
    constant_vals = [4.2] * 36
    constant_vals[10] = -999.0  # sensor fill value should interpolate to 4.2
    res = analyze_series(timestamps, constant_vals)
    assert res["primary_stats"]["is_significant"] is False
    assert res["primary_stats"]["sens_slope_per_year"] == 0.0

    with pytest.raises(ValueError, match="At least 24"):
        analyze_series(_make_monthly_timestamps(2023, 18), [1.0] * 18)


def test_fastapi_analyze_endpoint():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    n_months = 48
    ts = _make_monthly_timestamps(2020, n_months)
    vals = [10.0 + 0.1 * (i / 12.0) + 2.0 * np.sin(2.0 * np.pi * (i % 12) / 12.0) for i in range(n_months)]
    resp = client.post("/api/analyze", json={"timestamps": ts, "values": vals})
    assert resp.status_code == 200
    body = resp.json()
    assert "primary_series" in body
    assert "primary_stats" in body
    assert body["primary_stats"]["observation_months"] == 48


def test_preset_cases_and_latency():
    import time
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    cases_resp = client.get("/api/cases")
    assert cases_resp.status_code == 200
    cases = cases_resp.json()["cases"]
    assert len(cases) == 4
    assert all(c["cached"] is True for c in cases)

    for c in cases:
        t0 = time.perf_counter()
        detail = client.get(f"/api/cases/{c['case_id']}")
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        assert detail.status_code == 200
        assert elapsed_ms < 250.0  # fast local cache path
        payload = detail.json()
        assert payload["response"]["data_status"] == "cache"
        assert len(payload["response"]["primary_series"]["timestamps"]) >= 400
        assert payload["response"]["teleconnection"]["enabled"] is True


def test_investigate_and_explain_endpoints_and_offline_fallback(monkeypatch):
    import asyncio
    from fastapi.testclient import TestClient
    import httpx
    from main import app
    from nasa_service import fetch_nasa_monthly

    client = TestClient(app)

    # Test Case 2 Hydro Dipole opposite trends
    inv = client.post(
        "/api/investigate",
        json={
            "case_id": "case_2_dipole",
            "parameter": "GWETROOT",
            "primary_point": {"name": "US Southwest", "lat": 34.5, "lon": -108.0},
            "comparison_point": {"name": "Upper Midwest", "lat": 46.0, "lon": -94.0},
            "start_year": 1990,
            "end_year": 2025,
        },
    )
    assert inv.status_code == 200
    r = inv.json()["response"]
    assert r["primary_stats"]["sens_slope_per_year"] < 0
    assert r["primary_stats"]["is_significant"] is True
    assert r["teleconnection"]["comparison_sens_slope_per_year"] > 0
    assert r["teleconnection"]["comparison_is_significant"] is True

    # Test /api/explain deterministic fallback (no GEMINI_API_KEY)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    exp = client.post(
        "/api/explain",
        json={
            "lat": 78.22,
            "lon": 15.63,
            "parameter": "T2M",
            "sens_slope_per_year": 0.0829,
            "p_value": 0.0,
            "variance_reduction_pct": 87.4,
            "region_name": "Svalbard Archipelago",
            "case_id": "case_3_arctic",
        },
    )
    assert exp.status_code == 200
    assert "Arctic Amplification" in exp.json()["physical_mechanism"]
    assert exp.json()["ai_enhanced"] is False

    # Test offline fallback when httpx raises RequestError for an uncached coordinate
    async def broken_get(*args, **kwargs):
        raise httpx.ConnectError("Simulated network outage")

    monkeypatch.setattr(httpx.AsyncClient, "get", broken_get)
    fallback = asyncio.run(fetch_nasa_monthly(77.5, 16.0, "T2M", 1995, 2025))
    assert fallback["data_status"] == "offline_fallback"
    assert len(fallback["timestamps"]) > 300
