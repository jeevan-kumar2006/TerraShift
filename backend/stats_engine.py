"""Statistical and STL seasonal decomposition engine for TerraShift."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import linregress, norm, pearsonr, t as student_t
from statsmodels.tsa.seasonal import STL


def _clean_float(val: float | int | np.floating | None, digits: int = 4) -> float | None:
    """Convert numpy/float values to finite rounded Python floats or None."""
    if val is None:
        return None
    f = float(val)
    if not math.isfinite(f):
        return None
    return round(f, digits)


def _clean_array(arr: np.ndarray | list[float], digits: int = 4) -> list[float | None]:
    """Round an array of floats and sanitize non-finite entries."""
    return [_clean_float(v, digits) for v in arr]


MAX_INTERPOLATION_GAP_MONTHS = 3


def _prepare_series(
    timestamps: list[str], values: list[float | None]
) -> tuple[list[str], np.ndarray, dict[str, Any]]:
    """
    Validate, parse monthly timestamps, construct a complete monthly index,
    detect duplicate timestamps and missing months, reject gaps > 3 months,
    and linearly interpolate short interior gaps.
    """
    if len(timestamps) != len(values):
        raise ValueError("timestamps and values must have identical lengths.")
    if len(timestamps) < 24:
        raise ValueError("At least 24 monthly observations are required for STL decomposition.")

    parsed_dates = pd.to_datetime(timestamps, format="%Y-%m", errors="coerce")
    if parsed_dates.isna().any():
        parsed_dates = pd.to_datetime(timestamps, errors="coerce")
    if parsed_dates.isna().any():
        raise ValueError("All timestamps must be valid YYYY-MM date strings.")

    month_index = parsed_dates.to_period("M").to_timestamp()

    clean_vals: list[float] = []
    for v in values:
        if v is None:
            clean_vals.append(np.nan)
        else:
            fv = float(v)
            if not math.isfinite(fv) or fv <= -990.0:
                clean_vals.append(np.nan)
            else:
                clean_vals.append(fv)

    raw_series = pd.Series(clean_vals, index=month_index, dtype=float).sort_index()
    duplicate_timestamps_count = int(raw_series.index.duplicated().sum())
    if duplicate_timestamps_count > 0:
        raw_series = raw_series.groupby(level=0).mean()

    first_valid = raw_series.first_valid_index()
    last_valid = raw_series.last_valid_index()
    if first_valid is None or last_valid is None:
        raise ValueError("Time series has too few valid observations.")

    trimmed = raw_series.loc[first_valid:last_valid]
    full_index = pd.date_range(start=first_valid, end=last_valid, freq="MS")
    s_full = trimmed.reindex(full_index)

    expected_months = int(len(s_full))
    valid_months = int(s_full.notna().sum())
    missing_months = int(expected_months - valid_months)
    missing_pct = round((missing_months / expected_months) * 100.0, 2) if expected_months > 0 else 0.0

    max_consecutive_missing = 0
    current_run = 0
    for is_na in s_full.isna().to_numpy():
        if is_na:
            current_run += 1
            if current_run > max_consecutive_missing:
                max_consecutive_missing = current_run
        else:
            current_run = 0

    if expected_months < 24 or valid_months < 24:
        raise ValueError("At least 24 valid monthly observations are required for STL decomposition.")

    if max_consecutive_missing > MAX_INTERPOLATION_GAP_MONTHS:
        raise ValueError(
            f"Time series contains a missing gap of {max_consecutive_missing} consecutive months "
            f"(maximum allowed linear interpolation gap is {MAX_INTERPOLATION_GAP_MONTHS} months)."
        )

    s_interp = s_full.interpolate(
        method="linear", limit=MAX_INTERPOLATION_GAP_MONTHS, limit_direction="both"
    )
    if s_interp.isna().any():
        raise ValueError("Unable to interpolate missing observations in time series.")

    clean_ts = [dt.strftime("%Y-%m") for dt in s_interp.index]
    quality = {
        "expected_months": expected_months,
        "valid_months": valid_months,
        "missing_months": missing_months,
        "missing_pct": missing_pct,
        "interpolated_months": missing_months,
        "max_consecutive_missing": max_consecutive_missing,
        "duplicate_timestamps_merged": duplicate_timestamps_count,
        "max_interpolation_gap_limit": MAX_INTERPOLATION_GAP_MONTHS,
    }
    return clean_ts, s_interp.to_numpy(dtype=float), quality


def mann_kendall_test(y: np.ndarray, variant: str = "standard") -> dict[str, Any]:
    """
    Perform non-parametric Mann-Kendall trend test with tie correction.
    Optionally applies Hamed-Rao (1998) autocorrelation variance modification.
    """
    arr = np.asarray(y, dtype=float)
    n = len(arr)
    if n < 4:
        return {"s_stat": 0.0, "tau": 0.0, "z_score": 0.0, "p_value": 1.0, "is_significant": False}

    # Compute S statistic using upper-triangular pairwise differences
    diff = arr[None, :] - arr[:, None]
    tri_idx = np.triu_indices(n, k=1)
    s_stat = float(np.sum(np.sign(diff[tri_idx])))

    # Tie correction for variance
    _, counts = np.unique(arr, return_counts=True)
    tie_counts = counts[counts > 1]
    tie_term = float(np.sum(tie_counts * (tie_counts - 1) * (2 * tie_counts + 5)))
    var_s = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0

    # Optional Hamed-Rao autocorrelation correction
    if variant == "hamed_rao" and var_s > 0.0:
        slope = sens_slope(arr)["sens_slope_per_month"]
        detrended = arr - slope * np.arange(n, dtype=float)
        ranks = pd.Series(detrended).rank(method="average").to_numpy(dtype=float)
        ranks_centered = ranks - np.mean(ranks)
        denom = float(np.sum(ranks_centered ** 2))
        if denom > 0.0:
            n_s_factor = 1.0
            max_lag = n - 1
            z_crit = norm.ppf(0.975)
            for lag in range(1, max_lag + 1):
                acf_k = float(np.sum(ranks_centered[:-lag] * ranks_centered[lag:]) / denom)
                # Only include statistically significant lag autocorrelations
                se_acf = 1.0 / math.sqrt(n)
                if abs(acf_k) > z_crit * se_acf:
                    n_s_factor += (2.0 / (n * (n - 1) * (n - 2))) * (n - lag) * (n - lag - 1) * (n - lag - 2) * acf_k
            if n_s_factor > 0.1:
                var_s *= n_s_factor

    if var_s <= 0.0:
        return {"s_stat": float(s_stat), "tau": 0.0, "z_score": 0.0, "p_value": 1.0, "is_significant": False}

    if s_stat > 0:
        z_score = (s_stat - 1.0) / math.sqrt(var_s)
    elif s_stat < 0:
        z_score = (s_stat + 1.0) / math.sqrt(var_s)
    else:
        z_score = 0.0

    p_value = float(2.0 * (1.0 - norm.cdf(abs(z_score))))
    denom_tau = 0.5 * n * (n - 1)
    tau = float(s_stat / denom_tau) if denom_tau > 0 else 0.0

    return {
        "s_stat": float(s_stat),
        "tau": tau,
        "z_score": float(z_score),
        "p_value": p_value,
        "is_significant": bool(p_value < 0.05),
    }


def pettitt_test(y: np.ndarray | list[float]) -> dict[str, Any]:
    """
    Pettitt (1979) non-parametric test for detecting a single abrupt changepoint (regime shift)
    in a continuous time series.

    Computes U_{t,T} = sum_{i=1}^t sum_{j=t+1}^T sgn(x_i - x_j).
    Changepoint occurs at K_T = max_{1 <= t < T} |U_{t,T}|.
    Two-sided p-value approximation: p ~= 2 * exp(-6 * K_T^2 / (T^3 + T^2)).
    """
    arr = np.asarray(y, dtype=float)
    n = len(arr)
    if n < 4:
        return {
            "k_stat": 0.0,
            "changepoint_index": None,
            "p_value": 1.0,
            "is_significant": False,
        }

    ranks = pd.Series(arr).rank(method="average").to_numpy(dtype=float)
    cum_ranks = np.cumsum(ranks)
    t = np.arange(1, n, dtype=float)
    u_t = 2.0 * cum_ranks[:-1] - t * (n + 1.0)
    abs_u_t = np.abs(u_t)
    best_idx = int(np.argmax(abs_u_t))
    k_stat = float(abs_u_t[best_idx])
    p_val = float(2.0 * np.exp(-6.0 * (k_stat ** 2) / (float(n) ** 3 + float(n) ** 2)))
    p_val = min(1.0, max(0.0, p_val))

    return {
        "k_stat": k_stat,
        "changepoint_index": best_idx,
        "p_value": p_val,
        "is_significant": bool(p_val < 0.05),
    }


def sens_slope(y: np.ndarray, step_frequency: int = 12) -> dict[str, float]:
    """
    Compute Theil-Sen median slope and non-parametric 95% confidence bounds (Sen, 1968).

    Args:
        y: input 1D sequence of observations.
        step_frequency: number of steps per year (12 for monthly series, 1 for annual/seasonal series).
    """
    arr = np.asarray(y, dtype=float)
    n = len(arr)
    if n < 2:
        return {
            "sens_slope_step": 0.0,
            "sens_slope_per_month": 0.0,
            "sens_slope_per_year": 0.0,
            "sens_slope_per_decade": 0.0,
            "sens_slope_ci_lower": 0.0,
            "sens_slope_ci_upper": 0.0,
        }

    i_idx, j_idx = np.triu_indices(n, k=1)
    slopes = np.sort((arr[j_idx] - arr[i_idx]) / (j_idx - i_idx))
    slope_step = float(np.median(slopes))
    freq = float(step_frequency)
    slope_year = slope_step * freq
    slope_decade = slope_year * 10.0

    # Sen (1968) non-parametric 95% confidence interval using Kendall variance
    _, counts = np.unique(arr, return_counts=True)
    tie_counts = counts[counts > 1]
    tie_term = float(np.sum(tie_counts * (tie_counts - 1) * (2 * tie_counts + 5)))
    var_s = max(0.0, (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0)
    total_pairs = len(slopes)
    if var_s > 0.0 and total_pairs >= 2:
        c_alpha = float(norm.ppf(0.975) * math.sqrt(var_s))
        m1 = max(0, min(total_pairs - 1, int(math.floor((total_pairs - c_alpha) / 2.0))))
        m2 = max(0, min(total_pairs - 1, int(math.ceil((total_pairs + c_alpha) / 2.0)) - 1))
        ci_low_yr = float(slopes[m1]) * freq
        ci_high_yr = float(slopes[m2]) * freq
    else:
        ci_low_yr = slope_year
        ci_high_yr = slope_year

    return {
        "sens_slope_step": slope_step,
        "sens_slope_per_month": slope_step,  # backwards-compatible alias for monthly series
        "sens_slope_per_year": slope_year,
        "sens_slope_per_decade": slope_decade,
        "sens_slope_ci_lower": ci_low_yr,
        "sens_slope_ci_upper": ci_high_yr,
    }


def estimate_years_to_significance(
    n: int,
    slope_per_year: float,
    resid_std: float,
    is_significant: bool,
    lag1_autocorr: float = 0.0,
) -> int:
    """
    Estimate additional years of monthly observations required at the observed slope,
    residual variance, and lag-1 autocorrelation to reach 95% two-sided confidence (alpha=0.05).
    Incorporates the Weatherhead et al. (1998) AR(1) autocorrelation variance inflation:
    vif = (1 + phi) / (1 - phi).
    Returns 0 if already significant, or 99 (capped) for near-zero flat slopes.
    """
    if is_significant:
        return 0
    if abs(slope_per_year) < 1e-7 or resid_std < 0.0:
        return 99
    if resid_std <= 1e-12:
        return 1

    max_months = 1200  # 100 years cap
    if n >= max_months:
        return 99

    # Weatherhead et al. (1998) variance inflation for AR(1) red noise
    phi = float(np.clip(lag1_autocorr, -0.85, 0.85))
    vif = (1.0 + phi) / max(0.01, 1.0 - phi) if abs(phi) > (1.96 / math.sqrt(n)) else 1.0
    effective_resid_std = resid_std * math.sqrt(vif)

    total_n_arr = np.arange(n + 1, max_months + 1, dtype=float)
    s_xx = (total_n_arr * (total_n_arr ** 2 - 1.0)) / 1728.0
    t_stats = abs(slope_per_year) * np.sqrt(s_xx) / effective_resid_std
    t_crits = student_t.ppf(0.975, df=total_n_arr - 2.0)
    hits = np.flatnonzero(t_stats >= t_crits)
    if len(hits) > 0:
        target_n = int(total_n_arr[hits[0]])
        return int(math.ceil((target_n - n) / 12.0))

    return 99


def _analyze_single(timestamps: list[str], values: list[float | None], mk_variant: str = "standard") -> dict[str, Any]:
    """Run STL decomposition, Mann-Kendall, Sen's slope, OLS t-test, and observation-period power estimate."""
    clean_ts, raw, quality = _prepare_series(timestamps, values)
    n = len(raw)

    # 1. STL Seasonal Decomposition (period=12)
    idx = pd.to_datetime(clean_ts, format="%Y-%m")
    pd_series = pd.Series(raw, index=idx)
    stl_res = STL(pd_series, period=12, robust=True).fit()
    seasonal_cycle = stl_res.seasonal.to_numpy(dtype=float)

    deseasonalized = raw - seasonal_cycle
    deseasonalized_anomalies = deseasonalized - float(np.mean(deseasonalized))

    raw_var = float(np.var(raw))
    anom_var = float(np.var(deseasonalized_anomalies))
    if raw_var > 1e-12:
        variance_reduction_pct = max(0.0, (1.0 - (anom_var / raw_var)) * 100.0)
    else:
        variance_reduction_pct = 0.0

    seasonal_amplitude = float((np.max(seasonal_cycle) - np.min(seasonal_cycle)) / 2.0)

    # Raw Mann-Kendall p-value for demonstrating why stripping seasonality matters
    raw_mk = mann_kendall_test(raw, variant=mk_variant)

    # 2. Non-parametric Mann-Kendall & Sen's slope on deseasonalized anomalies
    mk_res = mann_kendall_test(deseasonalized_anomalies, variant=mk_variant)
    sen_res = sens_slope(deseasonalized_anomalies)

    # 3. Parametric OLS Linear Regression & Student's t-test with 95% confidence band
    x = np.arange(n, dtype=float) / 12.0
    if float(np.std(deseasonalized_anomalies)) < 1e-12:
        ols_slope = 0.0
        ols_intercept = 0.0
        t_statistic = 0.0
        degrees_of_freedom = max(1, n - 2)
        t_test_p_value = 1.0
        trend_line = np.zeros(n, dtype=float)
        ci_upper = np.zeros(n, dtype=float)
        ci_lower = np.zeros(n, dtype=float)
        resid_std = 0.0
    else:
        reg = linregress(x, deseasonalized_anomalies)
        ols_slope = float(reg.slope)
        ols_intercept = float(reg.intercept)
        degrees_of_freedom = max(1, n - 2)
        t_statistic = float(ols_slope / reg.stderr) if getattr(reg, "stderr", 0.0) and reg.stderr > 0 else 0.0
        t_test_p_value = float(reg.pvalue)
        trend_line = ols_intercept + ols_slope * x

        residuals = deseasonalized_anomalies - trend_line
        resid_std = math.sqrt(float(np.sum(residuals ** 2)) / max(1, n - 2))
        x_mean = float(np.mean(x))
        s_xx = float(np.sum((x - x_mean) ** 2))
        t_crit = float(student_t.ppf(0.975, df=degrees_of_freedom))
        margin = t_crit * resid_std * np.sqrt((1.0 / n) + ((x - x_mean) ** 2) / max(s_xx, 1e-12))
        ci_upper = trend_line + margin
        ci_lower = trend_line - margin

    # Lag-1 autocorrelation check on detrended deseasonalized anomalies
    detrended_resid = deseasonalized_anomalies - (ols_intercept + ols_slope * x)
    if n > 3 and float(np.std(detrended_resid)) > 1e-12:
        r_centered = detrended_resid - float(np.mean(detrended_resid))
        denom_acf = float(np.sum(r_centered ** 2))
        lag1_acf = float(np.sum(r_centered[:-1] * r_centered[1:]) / denom_acf) if denom_acf > 0 else 0.0
        autocorr_sig = abs(lag1_acf) > (1.96 / math.sqrt(n))
    else:
        lag1_acf = 0.0
        autocorr_sig = False

    # Outlier detection (|z| > 3 on detrended deseasonalized anomalies) without deleting points
    if float(np.std(detrended_resid)) > 1e-12:
        z_anom = np.abs((detrended_resid - float(np.mean(detrended_resid))) / float(np.std(detrended_resid)))
        outlier_count = int(np.sum(z_anom > 3.0))
    else:
        outlier_count = 0

    # Non-parametric Pettitt (1979) test for abrupt structural regime shift
    pettitt_res = pettitt_test(deseasonalized_anomalies)
    cp_idx = pettitt_res["changepoint_index"]
    cp_ts = clean_ts[cp_idx] if cp_idx is not None and 0 <= cp_idx < len(clean_ts) else None

    # 4. Years-to-significance horizon calculation
    # Use Sen's slope (or OLS slope if Sen's slope is degenerate while OLS is non-zero)
    effective_slope = sen_res["sens_slope_per_year"]
    if abs(effective_slope) < 1e-7 and abs(ols_slope) >= 1e-7:
        effective_slope = ols_slope

    years_needed = estimate_years_to_significance(
        n=n,
        slope_per_year=effective_slope,
        resid_std=resid_std,
        is_significant=mk_res["is_significant"],
        lag1_autocorr=lag1_acf,
    )

    series_dict = {
        "timestamps": clean_ts,
        "raw_values": _clean_array(raw, 4),
        "seasonal_cycle": _clean_array(seasonal_cycle, 4),
        "deseasonalized_anomalies": _clean_array(deseasonalized_anomalies, 4),
        "trend_line": _clean_array(trend_line, 4),
        "ci_upper": _clean_array(ci_upper, 4),
        "ci_lower": _clean_array(ci_lower, 4),
    }

    stats_dict = {
        "mann_kendall_s": _clean_float(mk_res["s_stat"], 1),
        "mann_kendall_tau": _clean_float(mk_res["tau"], 4),
        "z_score": _clean_float(mk_res["z_score"], 4),
        "p_value": _clean_float(mk_res["p_value"], 6),
        "t_statistic": _clean_float(t_statistic, 4),
        "degrees_of_freedom": int(degrees_of_freedom),
        "t_test_p_value": _clean_float(t_test_p_value, 6),
        "raw_p_value": _clean_float(raw_mk["p_value"], 6),
        "is_significant": bool(mk_res["is_significant"]),
        "sens_slope_per_year": _clean_float(sen_res["sens_slope_per_year"], 4),
        "sens_slope_per_decade": _clean_float(sen_res["sens_slope_per_decade"], 4),
        "sens_slope_ci_lower": _clean_float(sen_res["sens_slope_ci_lower"], 4),
        "sens_slope_ci_upper": _clean_float(sen_res["sens_slope_ci_upper"], 4),
        "ols_slope_per_year": _clean_float(ols_slope, 4),
        "ols_slope_per_decade": _clean_float(ols_slope * 10.0, 4),
        "ols_intercept": _clean_float(ols_intercept, 4),
        "lag1_autocorrelation": _clean_float(lag1_acf, 4),
        "autocorrelation_significant": bool(autocorr_sig),
        "changepoint_detected": bool(pettitt_res["is_significant"]),
        "changepoint_k_stat": _clean_float(pettitt_res["k_stat"], 1),
        "changepoint_p_value": _clean_float(pettitt_res["p_value"], 6),
        "changepoint_index": cp_idx,
        "changepoint_timestamp": cp_ts,
        "outlier_count": int(outlier_count),
        "years_to_significance": years_needed,
        "estimated_additional_observation_years": years_needed,
        "variance_reduction_pct": _clean_float(variance_reduction_pct, 1),
        "seasonal_amplitude": _clean_float(seasonal_amplitude, 4),
        "observation_months": int(n),
        "observation_years": _clean_float(n / 12.0, 1),
        "mk_variant": mk_variant,
        "valid_months": quality["valid_months"],
        "missing_months": quality["missing_months"],
        "missing_pct": quality["missing_pct"],
        "interpolated_months": quality["interpolated_months"],
        "max_consecutive_missing": quality["max_consecutive_missing"],
        "duplicate_timestamps_merged": quality["duplicate_timestamps_merged"],
        "ci_methodology": (
            "Shaded band shows the 95% two-sided Student's t confidence interval around the OLS linear fit on STL "
            "deseasonalized anomalies. Sen's slope 95% CI uses the non-parametric Kendall rank variance approximation (Sen, 1968). "
            "Structural shifts are assessed using Pettitt's (1979) non-parametric changepoint test."
        ),
        "horizon_assumptions": (
            "Estimated Additional Observation Period is a theoretical statistical power calculation (not a climate forecast): "
            "it evaluates when the observed trend would achieve two-sided alpha = 0.05 given the observed residual variance and "
            "accounting for AR(1) autocorrelation variance inflation (Weatherhead et al., 1998; Santer et al., 2000)."
        ),
    }

    return {"series": series_dict, "stats": stats_dict, "_raw_anomalies": deseasonalized_anomalies}


def analyze_series(
    timestamps: list[str],
    values: list[float | None],
    comparison_values: list[float | None] | None = None,
    comparison_timestamps: list[str] | None = None,
    mk_variant: str = "standard",
) -> dict[str, Any]:
    """
    Run full STL decomposition, Mann-Kendall, Sen's slope, OLS t-test,
    years-to-significance, and optional teleconnection cross-correlation.
    """
    primary = _analyze_single(timestamps, values, mk_variant=mk_variant)

    teleconnection: dict[str, Any] = {
        "enabled": False,
        "comparison_anomalies": [],
        "comparison_sens_slope_per_year": None,
        "comparison_sens_slope_per_decade": None,
        "comparison_is_significant": False,
        "comparison_p_value": None,
        "cross_correlation_r": None,
        "cross_correlation_p_value": None,
    }
    comparison_series = None
    comparison_stats = None

    if comparison_values is not None and len(comparison_values) >= 24:
        comp_ts = comparison_timestamps if comparison_timestamps is not None else timestamps
        comp = _analyze_single(comp_ts, comparison_values, mk_variant=mk_variant)
        comparison_series = comp["series"]
        comparison_stats = comp["stats"]

        # Align on common timestamps for Pearson correlation
        s_a = pd.Series(primary["_raw_anomalies"], index=primary["series"]["timestamps"])
        s_b = pd.Series(comp["_raw_anomalies"], index=comp["series"]["timestamps"])
        aligned = pd.concat([s_a, s_b], axis=1, join="inner").dropna()

        if len(aligned) >= 6 and float(aligned.iloc[:, 0].std()) > 1e-12 and float(aligned.iloc[:, 1].std()) > 1e-12:
            r_val, r_p = pearsonr(aligned.iloc[:, 0].to_numpy(), aligned.iloc[:, 1].to_numpy())
        else:
            r_val, r_p = 0.0, 1.0

        teleconnection = {
            "enabled": True,
            "comparison_anomalies": comp["series"]["deseasonalized_anomalies"],
            "comparison_sens_slope_per_year": comp["stats"]["sens_slope_per_year"],
            "comparison_sens_slope_per_decade": comp["stats"]["sens_slope_per_decade"],
            "comparison_is_significant": comp["stats"]["is_significant"],
            "comparison_p_value": comp["stats"]["p_value"],
            "cross_correlation_r": _clean_float(r_val, 4),
            "cross_correlation_p_value": _clean_float(r_p, 6),
        }

    return {
        "primary_series": primary["series"],
        "primary_stats": primary["stats"],
        "teleconnection": teleconnection,
        "comparison_series": comparison_series,
        "comparison_stats": comparison_stats,
    }
