"""Modular AI & deterministic physical explanation engine for TerraShift.

Design boundary:
- Statistical metrics (Sen's slope, Mann-Kendall p-value, STL variance reduction, Pearson r)
  are computed exclusively by `stats_engine.py` and passed in read-only.
- Gemini Flash interprets validated statistics and provenance; it never calculates,
  modifies, or invents statistical values.
- Deterministic physics-grounded synthesis is always constructed first as a safe fallback.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from acquisition.dataset_registry import get_trend_variable_registry
from config import GEMINI_API_BASE_URL, GEMINI_MODEL
from nasa_service import get_parameter_metadata


def _classify_latitude_band(lat: float) -> str:
    abs_lat = abs(lat)
    if abs_lat >= 60.0:
        return "Polar / Cryosphere Zone"
    if abs_lat >= 35.0:
        return "Mid-Latitude Storm Track Belt"
    if abs_lat >= 15.0:
        return "Subtropical Hadley Cell Limb"
    return "Equatorial / ITCZ Tropical Belt"


def build_deterministic_brief(
    *,
    lat: float,
    lon: float,
    parameter: str,
    sens_slope_per_year: float,
    p_value: float,
    variance_reduction_pct: float,
    years_to_significance: int = 0,
    observation_years: float = 35.0,
    region_name: str = "Selected Region",
    comparison_name: str | None = None,
    comparison_slope_per_year: float | None = None,
    cross_correlation_r: float | None = None,
    case_id: str | None = None,
    provenance: dict[str, Any] | None = None,
    sens_slope_ci_lower: float | None = None,
    sens_slope_ci_upper: float | None = None,
    missing_pct: float | None = None,
) -> dict[str, Any]:
    """Synthesize a scientifically accurate, deterministic Detective Brief without external APIs."""
    param = parameter.upper()
    meta = get_parameter_metadata(param)
    is_sig = p_value < 0.05
    decade_rate = sens_slope_per_year * 10.0
    band_label = _classify_latitude_band(lat)

    source_desc = (
        provenance.get("source")
        if provenance and provenance.get("source")
        else meta["mission_source"]
    )
    data_type = provenance.get("data_type", "reanalysis") if provenance else "reanalysis"
    is_synthetic = bool(provenance.get("is_synthetic")) if provenance else False

    if is_sig:
        if comparison_slope_per_year is not None and (
            (sens_slope_per_year > 0 and comparison_slope_per_year < 0)
            or (sens_slope_per_year < 0 and comparison_slope_per_year > 0)
        ):
            verdict_headline = (
                f"Statistically Significant Contrasting Regional Trends Detected (p = {p_value:.4f})"
            )
        else:
            direction = "Upward" if sens_slope_per_year > 0 else "Downward" if sens_slope_per_year < 0 else "Flat"
            verdict_headline = (
                f"Statistically Significant {direction} {meta['parameter_name']} Shift (p = {p_value:.4f})"
            )
    else:
        if years_to_significance >= 90:
            verdict_headline = (
                f"No Statistically Significant Trend Detected Over {observation_years:.1f} Years (p = {p_value:.3f})"
            )
        else:
            verdict_headline = (
                f"Not Statistically Significant Over {observation_years:.1f} Years (p = {p_value:.3f}; "
                f"Est. Additional Period ~{years_to_significance} yrs)"
            )

    if is_synthetic:
        verdict_headline = f"[SYNTHETIC DEMO] {verdict_headline}"

    corr_clause = ""
    if comparison_name and cross_correlation_r is not None:
        corr_clause = (
            f" Concurrent deseasonalized anomaly correlation with {comparison_name} is r = {cross_correlation_r:.2f} "
            "(linear co-movement only; correlation alone does not prove physical causation or a teleconnection)."
        )

    if case_id == "case_1_monsoon":
        mechanism = (
            f"Hypothesis / Physical Context: Across {region_name} and {comparison_name or 'Marathwada / Deccan'}, "
            "orographic uplift of Southwest Monsoon (JJAS) moisture along the Western Ghats contrasts with leeward "
            "rain-shadow drying across the interior Deccan Plateau, "
            f"corresponding to MERRA-2 precipitation slopes of {decade_rate:+.3f} vs "
            f"{(comparison_slope_per_year or 0) * 10:+.3f} {meta['unit']}/decade.{corr_clause}"
        )
        reference = "NASA POWER (MERRA-2 M2TMNXFLX) · Context: GPM IMERG & IMD Gridded Rainfall"
    elif case_id == "case_2_himalaya":
        mechanism = (
            f"Hypothesis / Physical Context: {region_name} ({lat:.1f}°N) exhibits elevation-dependent warming "
            f"({decade_rate:+.2f} °C/decade), where snow-albedo feedbacks and clear-sky radiative forcing accelerate "
            f"surface heating relative to maritime moderation along {comparison_name or 'the Coromandel Coast'}.{corr_clause}"
        )
        reference = "NASA POWER (MERRA-2 M2TMNXSLV) · Context: MODIS Terra LST & AIRS"
    elif case_id == "case_3_igp_thar":
        mechanism = (
            f"Hypothesis / Physical Context: Across {region_name} vs {comparison_name or 'the Thar Desert'}, "
            "monsoon moisture penetration, evapotranspiration demand, and alluvial water storage contrast sharply "
            f"between cultivated Indo-Gangetic plains ({decade_rate:+.4f} {meta['unit']}/decade) and arid western sands "
            f"({(comparison_slope_per_year or 0) * 10:+.4f} {meta['unit']}/decade).{corr_clause}"
        )
        reference = "NASA POWER (MERRA-2 M2TMNXLND) · Context: SMAP L3, GLDAS Noah & GRACE-FO"
    elif case_id == "case_4_northeast":
        mechanism = (
            f"Hypothesis / Physical Context: {region_name} receives intense Bay of Bengal moisture convergence "
            f"({decade_rate:+.3f} {meta['unit']}/decade) compared to continental convective rainfall variability across "
            f"{comparison_name or 'the Central Indian Plateau'} ({(comparison_slope_per_year or 0) * 10:+.3f} {meta['unit']}/decade).{corr_clause}"
        )
        reference = "NASA POWER (MERRA-2 M2TMNXFLX) · Context: GPM IMERG, TRMM & IMD Monsoon Studies"
    elif case_id == "case_5_heat_belt":
        mechanism = (
            f"Hypothesis / Physical Context: Interior continental heating in {region_name} "
            f"({decade_rate:+.2f} °C/decade) drives intense pre-monsoon (MAM) heat anomalies compared against "
            f"coastal thermal buffering along {comparison_name or 'the Eastern Ghats Coast'}.{corr_clause}"
        )
        reference = "NASA POWER (MERRA-2 M2TMNXSLV) · Context: MODIS LST & ECOSTRESS"
    elif case_id == "case_6_delta_basin":
        mechanism = (
            f"Hypothesis / Physical Context: Across {region_name} and {comparison_name or 'the Upper Indus-Ganga Basin'}, "
            f"deltaic estuary moisture ({decade_rate:+.4f} {meta['unit']}/decade) contrasts with irrigated basin profile wetness "
            f"({(comparison_slope_per_year or 0) * 10:+.4f} {meta['unit']}/decade), complementing GRACE-FO groundwater assessments.{corr_clause}"
        )
        reference = "NASA POWER (MERRA-2 M2TMNXLND) · Context: GRACE-FO Mascon & ISRO MOSDAC"
    else:
        if param == "T2M":
            mechanism = (
                f"Hypothesis / Physical Context: In this {band_label} ({lat:.2f}°, {lon:.2f}°), radiative forcing "
                f"modulated by local surface albedo and circulation variability yields a deseasonalized slope of "
                f"{decade_rate:+.3f} °C/decade.{corr_clause}"
            )
            reference = f"{source_desc} · Context: NASA GISTEMP & NOAA NCEI"
        elif param in ("PRECTOTCORR", "QV2M"):
            mechanism = (
                f"Hypothesis / Physical Context: In this {band_label} ({lat:.2f}°, {lon:.2f}°), Clausius-Clapeyron "
                f"thermodynamics and shifting moisture convergence coincide with a deseasonalized rate of "
                f"{decade_rate:+.4f} {meta['unit']}/decade.{corr_clause}"
            )
            reference = f"{source_desc} · Context: NASA GPM / GES DISC Hydrology"
        elif param in ("GWETROOT", "GWETPROF"):
            mechanism = (
                f"Hypothesis / Physical Context: In this {band_label} ({lat:.2f}°, {lon:.2f}°), model-derived soil wetness "
                f"reflects precipitation supply minus evaporative demand, yielding {decade_rate:+.4f} {meta['unit']}/decade.{corr_clause}"
            )
            reference = f"{source_desc} · Context: NASA GLDAS / SMAP"
        else:
            mechanism = (
                f"Hypothesis / Physical Context: In this {band_label} ({lat:.2f}°, {lon:.2f}°), regional circulation and "
                f"baroclinic variability correspond to a deseasonalized rate of {decade_rate:+.4f} {meta['unit']}/decade.{corr_clause}"
            )
            reference = f"{source_desc}"

    if variance_reduction_pct >= 20.0:
        seasonality_note = (
            f"STL decomposition (period=12) removed {variance_reduction_pct:.1f}% of total variance, "
            "isolating interannual anomalies from the annual seasonal cycle."
        )
    else:
        seasonality_note = (
            f"STL decomposition removed {variance_reduction_pct:.1f}% seasonal variance; interannual and sub-seasonal "
            "oscillations dominate month-to-month variability in this low-seasonality regime."
        )

    ci_text = ""
    if sens_slope_ci_lower is not None and sens_slope_ci_upper is not None:
        ci_text = f" Sen's slope 95% CI: [{sens_slope_ci_lower:+.4f}, {sens_slope_ci_upper:+.4f}] {meta['unit']}/yr."

    if not is_sig:
        horizon_note = (
            f"Over this {observation_years:.1f}-year window, p = {p_value:.4f} (>= 0.05) means the trend cannot be "
            "statistically distinguished from natural variability — this does not prove absence of physical change."
            f"{ci_text} Estimated Additional Observation Period: ~{years_to_significance} yrs (a statistical power "
            "estimate assuming constant slope and variance, not a forecast)."
        )
    else:
        horizon_note = (
            f"Over {observation_years:.1f} years, the Mann-Kendall test is statistically significant (p = {p_value:.5f} < 0.05) "
            f"at alpha = 0.05.{ci_text}"
        )

    missing_note = f" Missing data: {missing_pct:.2f}%." if missing_pct is not None else ""
    limitations_note = (
        f"Dataset type: {data_type.replace('_', ' ')} ({source_desc}).{missing_note} "
        "Reanalysis/model-derived grids (0.5° × 0.625°) represent grid-cell averages rather than point gauges. "
        "Correlation (r) does not imply causation, and p >= 0.05 does not prove zero trend."
    )
    if is_synthetic:
        limitations_note = (
            "SYNTHETIC DEMO DATA: This time series is a mathematically generated educational waveform, "
            "not real NASA or partner agency observations. " + limitations_note
        )

    methodology_note = (
        "STL robust seasonal decomposition (period=12) followed by non-parametric Mann-Kendall test, "
        "Theil-Sen median slope, and OLS 95% Student's t confidence band on deseasonalized anomalies."
    )

    return {
        "verdict_headline": verdict_headline,
        "physical_mechanism": mechanism,
        "seasonality_note": seasonality_note,
        "horizon_note": horizon_note,
        "reference": reference,
        "biome_zone": band_label,
        "methodology_note": methodology_note,
        "limitations_note": limitations_note,
        "ai_enhanced": False,
    }


async def maybe_enhance_with_gemini(
    *,
    lat: float,
    lon: float,
    parameter: str,
    sens_slope_per_year: float,
    p_value: float,
    variance_reduction_pct: float,
    years_to_significance: int,
    observation_years: float,
    region_name: str,
    comparison_name: str | None,
    comparison_slope_per_year: float | None,
    cross_correlation_r: float | None,
    baseline: dict[str, Any],
    provenance: dict[str, Any] | None = None,
    sens_slope_ci_lower: float | None = None,
    sens_slope_ci_upper: float | None = None,
    missing_pct: float | None = None,
) -> dict[str, Any]:
    """
    Optionally refine the deterministic brief using Gemini Flash if GEMINI_API_KEY is configured.
    Strictly preserves computed statistics and provenance; returns `baseline` on any error.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return baseline

    meta = get_parameter_metadata(parameter)
    source_desc = provenance.get("source") if provenance else meta["mission_source"]
    data_type = provenance.get("data_type", "reanalysis") if provenance else "reanalysis"
    retrieval_status = provenance.get("retrieval_status", "unknown") if provenance else "unknown"
    is_synthetic = bool(provenance.get("is_synthetic")) if provenance else False

    prompt = (
        "You are a NASA Earth System Science reviewer writing a concise Field Dossier.\n"
        "STRICT RULES:\n"
        "1. Do NOT calculate, alter, round away, or invent any statistical values. Interpret ONLY the validated numbers below.\n"
        "2. Distinguish MERRA-2 reanalysis / model-derived data from direct satellite observations.\n"
        "3. Present physical mechanisms as plausible hypotheses unless causation is established.\n"
        "4. NEVER claim Pearson correlation (r) proves causation or a physical teleconnection.\n"
        "5. NEVER claim p >= 0.05 proves absence of change; describe it as insufficient evidence to distinguish from natural variability over the window.\n"
        "6. Refer to additional observation period as a statistical power estimate, NOT a prediction.\n"
        "Return ONLY valid JSON with keys: verdict_headline, physical_mechanism, seasonality_note, horizon_note, reference.\n"
        f"Validated Statistical & Provenance Context:\n"
        f"- Region A: {region_name} ({lat:.2f}, {lon:.2f}), Zone: {baseline['biome_zone']}\n"
        f"- Variable: {meta['parameter_name']} ({parameter}) in {meta['unit']}\n"
        f"- Source & Type: {source_desc} (type={data_type}, retrieval={retrieval_status}, synthetic={is_synthetic})\n"
        f"- Missing data: {missing_pct if missing_pct is not None else 0.0}%\n"
        f"- Deseasonalized Sen's slope: {sens_slope_per_year:+.4f} {meta['unit']}/yr"
        + (
            f" (95% CI [{sens_slope_ci_lower:+.4f}, {sens_slope_ci_upper:+.4f}])"
            if sens_slope_ci_lower is not None and sens_slope_ci_upper is not None
            else ""
        )
        + "\n"
        f"- Mann-Kendall p-value: {p_value:.5f} (alpha=0.05), STL variance removed: {variance_reduction_pct:.1f}%\n"
        f"- Observation window: {observation_years:.1f} years, Est. Additional Observation Period: {years_to_significance} yrs\n"
        f"- Region B: {comparison_name or 'None'}, slope={comparison_slope_per_year}, Pearson r={cross_correlation_r}\n"
        f"- Baseline physical context: {baseline['physical_mechanism']}\n"
        "Keep every field concise (max 2-3 sentences), scientifically rigorous, and accessible."
    )

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }

    async with httpx.AsyncClient(timeout=8.0) as client:
        url = f"{GEMINI_API_BASE_URL}/models/{GEMINI_MODEL}:generateContent?key={api_key}"
        try:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            data = resp.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(raw_text)
            required = ("verdict_headline", "physical_mechanism", "seasonality_note", "horizon_note", "reference")
            if not any(not isinstance(parsed.get(key), str) or not parsed[key].strip() for key in required):
                headline = parsed["verdict_headline"].strip()
                if is_synthetic and "SYNTHETIC" not in headline.upper():
                    headline = f"[SYNTHETIC DEMO] {headline}"
                return {
                    **baseline,
                    "verdict_headline": headline,
                    "physical_mechanism": parsed["physical_mechanism"].strip(),
                    "seasonality_note": parsed["seasonality_note"].strip(),
                    "horizon_note": parsed["horizon_note"].strip(),
                    "reference": parsed["reference"].strip(),
                    "ai_enhanced": True,
                }
        except Exception:
            pass

    return baseline


def compute_region_features(
    region_id: str | None,
    region_name: str,
    lat: float,
    lon: float,
    area_km2: float | None = None,
) -> dict[str, Any]:
    """Compute physical/geographic features of an Indian region from coordinates and boundary metadata."""
    lat_f = float(lat)
    lon_f = float(lon)

    if lat_f >= 28.5:
        climate_zone = "Himalayan / Northern Plains"
    elif lat_f >= 23.5 and lon_f <= 74.5:
        climate_zone = "Arid / Semi-Arid Western India"
    elif lat_f >= 23.5 and lon_f >= 88.0:
        climate_zone = "Humid Subtropical / Northeast Monsoon Belt"
    elif lat_f >= 21.5:
        climate_zone = "Central & Indo-Gangetic Plains"
    else:
        climate_zone = "Peninsular / Tropical Monsoon Zone"

    coastal_prox = (
        lat_f <= 22.5 and (lon_f <= 74.5 or lon_f >= 79.5)
    ) or (lat_f <= 13.5)
    is_arid = (lon_f <= 74.5 and 24.0 <= lat_f <= 30.5)
    is_mountain = lat_f >= 30.0 or (lat_f >= 27.0 and lon_f >= 88.0)

    return {
        "region_id": region_id,
        "region_name": region_name,
        "latitude": round(lat_f, 4),
        "longitude": round(lon_f, 4),
        "area_km2": round(float(area_km2), 1) if area_km2 is not None else None,
        "climate_zone": climate_zone,
        "biome_zone": _classify_latitude_band(lat_f),
        "coastal_proximity": coastal_prox,
        "arid_or_semiarid": is_arid,
        "high_elevation_or_himalayan": is_mountain,
    }


def _deterministic_variable_suggestions(
    features: dict[str, Any],
    registry_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    """Deterministic feature-driven variable suggestions using only valid registry IDs."""
    candidates: list[tuple[str, str, str]] = []

    if features.get("high_elevation_or_himalayan"):
        candidates.append((
            "T2M",
            "High-elevation Himalayan and northern regions exhibit amplified warming signals and cryosphere-albedo feedbacks.",
            "increasing",
        ))
        candidates.append((
            "MOD11C3",
            "Satellite land surface temperature captures elevation-dependent surface warming across complex terrain.",
            "increasing",
        ))
    if features.get("arid_or_semiarid"):
        candidates.append((
            "MOD13C2",
            "MODIS NDVI tracks vegetation greening or degradation driven by irrigation and monsoon variability in arid/semi-arid basins.",
            "increasing",
        ))
        candidates.append((
            "GWETROOT",
            "Root-zone soil moisture directly reflects agricultural water stress and irrigation trends.",
            "variable",
        ))
    if features.get("coastal_proximity"):
        candidates.append((
            "GPM_3IMERGM",
            "GPM IMERG satellite precipitation resolves coastal monsoon intensity and extreme rainfall shifts.",
            "variable",
        ))
        candidates.append((
            "QV2M",
            "Specific humidity tracks marine boundary-layer moisture transport along coastal belts.",
            "increasing",
        ))

    defaults = [
        (
            "T2M",
            "2m air temperature provides a continuous baseline for long-term regional warming detection.",
            "increasing",
        ),
        (
            "GPM_3IMERGM",
            "Satellite precipitation measures monsoon and seasonal rainfall trends across the selected region.",
            "variable",
        ),
        (
            "MOD13C2",
            "MODIS NDVI monitors vegetation health and land-cover response to climate and land-use change.",
            "variable",
        ),
        (
            "OMNO2d",
            "OMI tropospheric NO2 tracks urban, industrial, and transport emissions trends.",
            "increasing",
        ),
    ]

    seen: set[str] = set()
    output: list[dict[str, str]] = []
    for var_id, reason, direction in [*candidates, *defaults]:
        if var_id in registry_by_id and var_id not in seen:
            seen.add(var_id)
            output.append({
                "variable_id": var_id,
                "reason": reason,
                "expected_direction": direction,
            })
        if len(output) >= 4:
            break
    return output


def validate_suggested_variables(
    raw_items: Any,
    registry_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    """Validate structured AI variable suggestions against TREND_VARIABLE_REGISTRY."""
    if not isinstance(raw_items, list):
        return []
    valid_directions = {"increasing", "decreasing", "variable"}
    validated: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        var_id = str(item.get("variable_id", "")).strip()
        reason = str(item.get("reason", "")).strip()
        direction = str(item.get("expected_direction", "variable")).strip().lower()
        if var_id not in registry_by_id or var_id in seen or not reason:
            continue
        if direction not in valid_directions:
            direction = "variable"
        seen.add(var_id)
        validated.append({
            "variable_id": var_id,
            "reason": reason,
            "expected_direction": direction,
        })
    return validated


async def suggest_variables_for_region(
    region_id: str | None,
    region_name: str,
    lat: float,
    lon: float,
    area_km2: float | None = None,
) -> dict[str, Any]:
    """Suggest Earth observation variables for an Indian region using computed features + Gemini (with deterministic fallback)."""
    features = compute_region_features(region_id, region_name, lat, lon, area_km2=area_km2)
    registry = get_trend_variable_registry()
    registry_by_id = {entry["id"]: entry for entry in registry}
    fallback = _deterministic_variable_suggestions(features, registry_by_id)

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {
            "region_features": features,
            "suggestions": fallback,
            "ai_enhanced": False,
            "model_used": None,
        }

    allowed_catalog = [
        {"id": e["id"], "label": e["label"], "source_type": e["source_type"], "mission": e["mission"]}
        for e in registry
    ]
    prompt = (
        "You are an Earth observation scientist selecting variables to investigate long-term trends in India.\n"
        f"Computed region features: {json.dumps(features)}\n"
        f"Allowed variable catalog (ONLY choose variable_id from this list): {json.dumps(allowed_catalog)}\n"
        "Return ONLY a JSON array of 3 to 4 objects with keys: variable_id, reason, expected_direction "
        "(one of 'increasing', 'decreasing', 'variable'). Do NOT invent any numeric slopes, p-values, or unknown variable_id."
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }

    async with httpx.AsyncClient(timeout=8.0) as client:
        url = f"{GEMINI_API_BASE_URL}/models/{GEMINI_MODEL}:generateContent?key={api_key}"
        try:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            data = resp.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(raw_text)
            validated = validate_suggested_variables(parsed, registry_by_id)
            if validated:
                return {
                    "region_features": features,
                    "suggestions": validated,
                    "ai_enhanced": True,
                    "model_used": GEMINI_MODEL,
                }
        except Exception:
            pass

    return {
        "region_features": features,
        "suggestions": fallback,
        "ai_enhanced": False,
        "model_used": None,
    }
