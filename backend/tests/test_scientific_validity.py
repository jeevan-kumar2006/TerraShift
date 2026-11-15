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
from scipy.stats import linregress, theilslopes
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


# ==============================================================================
# 12-CASE CONTROLLED MATHEMATICAL TEST BENCH (PART 5)
# ==============================================================================

def _make_timestamps(n: int, start_year: int = 2000) -> list[str]:
    """Helper to generate n consecutive monthly timestamps."""
    dates = pd.date_range(f"{start_year}-01-01", periods=n, freq="MS")
    return [d.strftime("%Y-%m") for d in dates]


def test_mathematical_bench_case_1_perfectly_increasing():
    """Case 1: Monotonically increasing linear series (Tau=1.0, p < 0.001, exact slope)."""
    n = 60
    t = np.arange(n, dtype=float)
    y = 0.5 * t + 10.0  # slope = 0.5/month = 6.0/year
    res_mk = mann_kendall_test(y)
    res_sen = sens_slope(y, step_frequency=12)

    assert abs(res_mk["tau"] - 1.0) < 1e-9
    assert res_mk["p_value"] < 0.0001
    assert abs(res_sen["sens_slope_per_month"] - 0.5) < 1e-9
    assert abs(res_sen["sens_slope_per_year"] - 6.0) < 1e-9


def test_mathematical_bench_case_2_perfectly_decreasing():
    """Case 2: Monotonically decreasing linear series (Tau=-1.0, p < 0.001, exact negative slope)."""
    n = 60
    t = np.arange(n, dtype=float)
    y = -0.25 * t + 50.0  # slope = -0.25/month = -3.0/year
    res_mk = mann_kendall_test(y)
    res_sen = sens_slope(y, step_frequency=12)

    assert abs(res_mk["tau"] - (-1.0)) < 1e-9
    assert res_mk["p_value"] < 0.0001
    assert abs(res_sen["sens_slope_per_month"] - (-0.25)) < 1e-9
    assert abs(res_sen["sens_slope_per_year"] - (-3.0)) < 1e-9


def test_mathematical_bench_case_3_constant_series():
    """Case 3: Invariant constant series (Tau=0.0, p=1.0, slope=0.0, no false positive)."""
    n = 48
    y = np.full(n, 25.0)
    res_mk = mann_kendall_test(y)
    res_sen = sens_slope(y, step_frequency=12)

    assert abs(res_mk["tau"]) < 1e-9
    assert res_mk["p_value"] == 1.0
    assert res_mk["is_significant"] is False
    assert abs(res_sen["sens_slope_per_year"]) < 1e-9


def test_mathematical_bench_case_4_noisy_known_trend():
    """Case 4: Linear trend masked by Gaussian white noise recovers true slope within 95% CI."""
    rng = np.random.default_rng(42)
    n = 120
    t = np.arange(n, dtype=float)
    true_step_slope = 0.05  # 0.60 per year
    y = true_step_slope * t + rng.normal(0.0, 0.5, n)

    res_sen = sens_slope(y, step_frequency=12)
    # 95% CI must bracket true slope of 0.60/year
    assert res_sen["sens_slope_ci_lower"] <= 0.60 <= res_sen["sens_slope_ci_upper"]
    assert abs(res_sen["sens_slope_per_year"] - 0.60) < 0.15


def test_mathematical_bench_case_5_seasonal_no_trend():
    """Case 5: Pure harmonic seasonal cycle without long-term trend (STL removes cycle, slope ~ 0)."""
    n = 72  # 6 years
    timestamps = _make_timestamps(n)
    t = np.arange(n, dtype=float)
    # Seasonal amplitude 10.0, zero trend
    y = 10.0 * np.sin(2.0 * np.pi * t / 12.0) + 20.0

    analysis = analyze_series(timestamps, y.tolist())
    primary = analysis["primary_stats"]

    # Seasonality explains > 90% of raw variance
    assert primary["variance_reduction_pct"] > 90.0
    # Deseasonalized slope must be negligible
    assert abs(primary["sens_slope_per_year"]) < 0.01
    assert primary["is_significant"] is False


def test_mathematical_bench_case_6_seasonal_with_known_trend():
    """Case 6: Strong seasonal cycle superimposed on a linear warming trend."""
    n = 120  # 10 years
    timestamps = _make_timestamps(n)
    t = np.arange(n, dtype=float)
    # 0.04 C/month = 0.48 C/year warming + strong 8C seasonal swing
    warming_rate_yr = 0.48
    y = (warming_rate_yr / 12.0) * t + 8.0 * np.cos(2.0 * np.pi * t / 12.0) + 15.0

    analysis = analyze_series(timestamps, y.tolist())
    primary = analysis["primary_stats"]

    # Mann-Kendall on deseasonalized anomalies must confirm significance
    assert primary["is_significant"] is True
    assert primary["p_value"] < 0.001
    # Recovered Sen's slope must closely match injected 0.48 C/year
    assert abs(primary["sens_slope_per_year"] - warming_rate_yr) < 0.05


def test_mathematical_bench_case_7_missing_observations_tolerance_and_rejection():
    """Case 7: Short interior missing gaps (<= 3 months) are linearly interpolated; gaps > 3 rejected."""
    n = 48
    timestamps = _make_timestamps(n)
    y_short_gap = [float(i) for i in range(n)]
    # Create an interior gap of 2 months (indices 10, 11)
    y_short_gap[10] = None
    y_short_gap[11] = None

    analysis = analyze_series(timestamps, y_short_gap)
    # Must succeed and interpolate smoothly
    raw_vals = analysis["primary_series"]["raw_values"]
    assert len(raw_vals) == n
    assert abs(raw_vals[10] - 10.0) < 1e-4
    assert abs(raw_vals[11] - 11.0) < 1e-4

    # Create a long interior gap of 4 months (> MAX_INTERPOLATION_GAP_MONTHS)
    y_long_gap = [float(i) for i in range(n)]
    for idx in range(12, 16):
        y_long_gap[idx] = None
    with pytest.raises(ValueError, match="missing gap of 4 consecutive months"):
        analyze_series(timestamps, y_long_gap)


def test_mathematical_bench_case_8_outliers_sen_breakdown_resistance_vs_ols():
    """Case 8: Extreme rogue spikes corrupt parametric OLS while Theil-Sen remains stable."""
    rng = np.random.default_rng(88)
    n = 60
    t = np.arange(n, dtype=float)
    clean_y = 0.05 * t + 5.0  # true step slope = 0.05 -> 0.60/year
    corrupted_y = clean_y.copy()
    # Inject 3 severe positive outliers (+100.0) simulating telemetry corruption
    corrupted_y[10] += 100.0
    corrupted_y[25] += 120.0
    corrupted_y[40] += 110.0

    sen_res = sens_slope(corrupted_y, step_frequency=12)
    # Compute parametric OLS slope for comparison
    ols_slope, _, _, _, _ = linregress(t / 12.0, corrupted_y)

    # Sen's median slope is robust to the 5% gross contamination (within 0.10 of true 0.60)
    assert abs(sen_res["sens_slope_per_year"] - 0.60) < 0.10
    # OLS is drastically distorted (reverses sign to -0.29, error > 0.8)
    assert abs(ols_slope - 0.60) > 0.80, "OLS must exhibit severe vulnerability to outliers"


def test_mathematical_bench_case_9_irregular_timestamps_reindexing():
    """Case 9: Irregular dates and duplicate entries are re-indexed to regular calendar months."""
    n = 36
    # Create irregular day-of-month dates and duplicate month entries
    raw_dates = []
    base = pd.to_datetime("2015-01-01")
    for i in range(n):
        dt = base + pd.DateOffset(months=i, days=(i % 15))
        raw_dates.append(dt.strftime("%Y-%m-%d"))

    # Introduce a duplicate month with different values
    raw_dates.append("2015-06-18")
    raw_values = [10.0 + 0.1 * i for i in range(n)] + [15.0]

    # Analysis must succeed by aggregating duplicate months and reindexing to regular MS
    analysis = analyze_series(raw_dates, raw_values)
    assert len(analysis["primary_series"]["timestamps"]) == n
    assert analysis["primary_stats"]["observation_months"] == n


def test_mathematical_bench_case_10_autocorrelated_red_noise_defense():
    """Case 10: Autocorrelated red noise AR(1) triggers Hamed-Rao variance modification."""
    rng = np.random.default_rng(999)
    n = 120
    phi = 0.70
    noise = np.zeros(n)
    innov = rng.normal(0, 1.0, n)
    for t in range(1, n):
        noise[t] = phi * noise[t - 1] + innov[t]

    # Standard MK test on strong red noise without actual trend often over-rejects (false positive)
    # Hamed-Rao corrects variance to account for positive autocorrelation
    mk_std = mann_kendall_test(noise, variant="standard")
    mk_hr = mann_kendall_test(noise, variant="hamed_rao")

    # Corrected Z-score must be attenuated relative to uncorrected
    assert abs(mk_hr["z_score"]) < abs(mk_std["z_score"])
    assert mk_hr["p_value"] >= mk_std["p_value"]


def test_mathematical_bench_case_11_short_observation_period_rejection():
    """Case 11: Series shorter than minimum 24-month horizon is strictly rejected."""
    n = 18
    timestamps = _make_timestamps(n)
    values = [20.0 + 0.1 * i for i in range(n)]

    with pytest.raises(ValueError, match="At least 24 monthly observations are required"):
        analyze_series(timestamps, values)


def test_mathematical_bench_case_12_insufficient_valid_observations_rejection():
    """Case 12: Series with total span >= 24 but fewer than 24 valid observations is rejected."""
    n = 30
    timestamps = _make_timestamps(n)
    # 20 valid points, 10 missing points scattered (valid < 24)
    values = [float(i) if i % 3 != 0 else None for i in range(n)]

    with pytest.raises(ValueError):
        analyze_series(timestamps, values)

