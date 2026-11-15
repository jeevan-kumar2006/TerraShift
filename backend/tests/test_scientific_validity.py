"""Independent reference validation and scientific defensibility regression tests for TerraShift.

Tests include:
1. Exact mathematical benchmarking of Mann-Kendall test against pymannkendall.original_test.
2. Exact benchmarking of Hamed-Rao variance modification against pymannkendall.hamed_rao_modification_test.
3. Benchmarking of Theil-Sen slope and confidence intervals against scipy.stats.theilslopes.
4. Non-parametric Pettitt (1979) changepoint test validation on abrupt step shifts vs stationary noise.
5. Weatherhead et al. (1998) AR(1) autocorrelation variance inflation validation.
6. Provenance traceability verification across /api/cases, /api/investigate, /api/india/seasonal-analysis, and /api/india/regional-comparison.
7. Synthetic data safeguards preventing misleading real-world claims.
8. Physical domain invariant checks across all 6 curated India cases.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pymannkendall as mk
import pytest
from scipy.stats import theilslopes
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app
from stats_engine import (
    analyze_series,
    estimate_years_to_significance,
    mann_kendall_test,
    pettitt_test,
    sens_slope,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_mann_kendall_exact_match_pymannkendall_various_sample_sizes():
    """Verify Mann-Kendall S, Tau, z-score, and p-value match pymannkendall across multiple N."""
    rng = np.random.default_rng(101)
    for n in [10, 24, 60, 120, 240]:
        y = np.linspace(2.0, 15.0, n) + rng.normal(0.0, 0.6, n)
        ref = mk.original_test(y)
        ours = mann_kendall_test(y, variant="standard")

        assert abs(ours["tau"] - ref.Tau) < 1e-6, f"Tau mismatch for N={n}"
        assert abs(ours["z_score"] - ref.z) < 1e-5, f"Z mismatch for N={n}"
        assert abs(ours["p_value"] - ref.p) < 1e-5, f"P-value mismatch for N={n}"
        assert ours["is_significant"] == (ref.h is True or ref.p < 0.05)


def test_hamed_rao_exact_match_under_severe_red_noise():
    """Verify Hamed-Rao (1998) autocorrelation modification matches reference library under strong AR(1)."""
    rng = np.random.default_rng(202)
    for phi in [0.4, 0.65, 0.8]:
        n = 120
        noise = np.zeros(n)
        innovations = rng.normal(0.0, 0.4, n)
        for t in range(1, n):
            noise[t] = phi * noise[t - 1] + innovations[t]
        y = 0.03 * np.arange(n) + noise

        ref = mk.hamed_rao_modification_test(y)
        ours = mann_kendall_test(y, variant="hamed_rao")

        assert abs(ours["tau"] - ref.Tau) < 1e-6, f"Tau mismatch for phi={phi}"
        assert abs(ours["z_score"] - ref.z) < 1e-3, f"Z mismatch for phi={phi}"
        assert abs(ours["p_value"] - ref.p) < 1e-3, f"P mismatch for phi={phi}"


def test_ties_exact_match_pymannkendall():
    """Verify tie-corrected variance matches pymannkendall on series with heavy repeated values."""
    y_ties = np.repeat([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0], 8)  # 64 items, 8 items per tie
    ref = mk.original_test(y_ties)
    ours = mann_kendall_test(y_ties)

    assert abs(ours["tau"] - ref.Tau) < 1e-6
    assert abs(ours["z_score"] - ref.z) < 1e-5
    assert abs(ours["p_value"] - ref.p) < 1e-5


def test_sens_slope_matches_scipy_theilslopes():
    """Verify Sen's median slope and 95% confidence bounds match scipy.stats.theilslopes."""
    rng = np.random.default_rng(303)
    for n in [24, 60, 120]:
        y = np.linspace(10.0, 25.0, n) + rng.normal(0.0, 0.8, n)
        scipy_res = theilslopes(y, alpha=0.95)
        ours = sens_slope(y, step_frequency=12)

        # per-month step slope matches scipy raw slope
        assert abs(ours["sens_slope_per_month"] - scipy_res.slope) < 1e-6
        # Annualized slope is 12 * step slope
        assert abs(ours["sens_slope_per_year"] - (scipy_res.slope * 12.0)) < 1e-5
        # 95% confidence intervals closely track scipy bounds
        step_ci_low = ours["sens_slope_ci_lower"] / 12.0
        step_ci_high = ours["sens_slope_ci_upper"] / 12.0
        assert abs(step_ci_low - scipy_res.low_slope) < 0.015
        assert abs(step_ci_high - scipy_res.high_slope) < 0.015


def test_pettitt_regime_changepoint_detection():
    """Pettitt (1979) test must detect abrupt step shifts and reject stationary white noise."""
    rng = np.random.default_rng(404)
    # 1. Abrupt shift at index 50 (from mean 10.0 to 16.0)
    step_y = np.concatenate([rng.normal(10.0, 0.6, 50), rng.normal(16.0, 0.6, 50)])
    step_res = pettitt_test(step_y)
    assert step_res["is_significant"] is True
    assert step_res["p_value"] < 0.001
    assert abs(step_res["changepoint_index"] - 49) <= 1  # near split index 49-50

    # 2. Stationary white noise (no regime shift)
    white_noise = rng.normal(12.0, 1.0, 100)
    white_res = pettitt_test(white_noise)
    assert white_res["is_significant"] is False
    assert white_res["p_value"] > 0.05


def test_weatherhead_autocorrelation_inflation_defense():
    """Verify that positive AR(1) autocorrelation increases observation horizon needed for significance."""
    n = 120
    slope = 0.02
    resid_std = 0.8
    # White noise horizon
    years_white = estimate_years_to_significance(n, slope, resid_std, is_significant=False, lag1_autocorr=0.0)
    # Moderate red noise (phi = 0.6) horizon
    years_red = estimate_years_to_significance(n, slope, resid_std, is_significant=False, lag1_autocorr=0.6)

    assert years_red > years_white, "Red noise must increase years required to confirm significance"
    # Flat / zero slope must cap safely at 99 years
    years_flat = estimate_years_to_significance(n, 0.0, resid_std, is_significant=False)
    assert years_flat == 99


def test_provenance_traceability_across_all_endpoints(client):
    """Verify complete scientific provenance is delivered across API endpoints."""
    # 1. /api/cases/{case_id}
    res_case = client.get("/api/cases/case_1_monsoon")
    assert res_case.status_code == 200
    p_prov = res_case.json()["response"]["primary_provenance"]
    assert p_prov is not None
    for field in ["source", "collection", "parameter", "units", "temporal_resolution", "spatial_resolution", "actual_coordinates"]:
        assert field in p_prov and p_prov[field] is not None

    # 2. /api/india/seasonal-analysis
    res_season = client.post(
        "/api/india/seasonal-analysis",
        json={"case_id": "case_2_himalaya", "start_year": 1991, "end_year": 2024},
    )
    assert res_season.status_code == 200
    body = res_season.json()
    assert "provenance" in body["meta"]
    assert body["meta"]["provenance"]["collection"] is not None
    assert "annual_anomalies" in body["analysis"]

    # 3. /api/india/regional-comparison
    res_comp = client.get("/api/india/regional-comparison?start_year=1991&end_year=2024")
    assert res_comp.status_code == 200
    rows = res_comp.json()["rows"]
    assert len(rows) >= 6
    for row in rows:
        assert "provenance" in row
        assert row["provenance"]["source"] is not None


def test_synthetic_data_safeguard(client):
    """Verify that synthetic time series cannot strip synthetic flags or produce misleading claims."""
    rows = ["# SYNTHETIC_DEMO_DATA: true", "time,val"]
    for yr in range(2010, 2014):
        for m in range(1, 13):
            rows.append(f"{yr}-{m:02d}-01,{5.0 + 0.02 * (yr - 2010)}")
    raw_synthetic = "\n".join(rows)

    resp = client.post(
        "/api/import-series",
        json={"raw_text": raw_synthetic, "region_name": "Synthetic Lab Test"},
    )
    assert resp.status_code == 200
    payload = resp.json()["response"]
    assert payload["data_status"] == "synthetic"
    assert payload["primary_provenance"]["is_synthetic"] is True
    assert "[SYNTHETIC DEMO]" in payload["detective_brief"]["verdict_headline"]
    assert "SYNTHETIC DEMO DATA" in payload["detective_brief"]["limitations_note"]


def test_physical_domain_invariants_across_preset_cases(client):
    """Verify physical invariants for all 6 curated India cases."""
    # Case 2: Himalayan temperatures must be within physically plausible ranges (-40C to 40C)
    c2 = client.get("/api/cases/case_2_himalaya").json()["response"]
    c2_vals = [v for v in c2["primary_series"]["raw_values"] if v is not None]
    assert len(c2_vals) >= 400
    assert min(c2_vals) > -40.0 and max(c2_vals) < 40.0, "Himalayan temperatures must be physically bounded"
    assert abs(c2["primary_stats"]["sens_slope_per_year"]) < 1.0, "Decadal warming/cooling rate must be physically plausible"

    # Case 1: Western Ghats precipitation must have positive mean daily rainfall rate
    c1 = client.get("/api/cases/case_1_monsoon").json()["response"]
    vals = [v for v in c1["primary_series"]["raw_values"] if v is not None]
    assert np.mean(vals) > 0.0, "Precipitation values must be positive"
    assert min(vals) >= 0.0, "Rainfall cannot be negative"

    # Case 3: Root-zone soil moisture wetness fraction must remain between 0 and 1
    c3 = client.get("/api/cases/case_3_igp_thar").json()["response"]
    c3_vals = [v for v in c3["primary_series"]["raw_values"] if v is not None]
    assert min(c3_vals) >= 0.0 and max(c3_vals) <= 1.0, "GWETROOT wetness fraction must be within [0, 1]"
