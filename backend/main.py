"""FastAPI router for TerraShift — Earth System Trend Detective."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from nasa_service import (
    PARAMETER_METADATA,
    fetch_nasa_monthly,
    get_parameter_metadata,
    get_preset_case_series,
    list_preset_cases,
)
from stats_engine import analyze_series

app = FastAPI(
    title="TerraShift API",
    description="Earth System Trend Detective — STL decomposition, Mann-Kendall, Sen's slope, and NASA POWER integration.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GeoPoint(BaseModel):
    name: str = Field(default="Selected Region", max_length=120)
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)


class AnalyzeRequest(BaseModel):
    timestamps: list[str] = Field(..., description="Monthly YYYY-MM timestamps")
    values: list[float | None] = Field(..., description="Monthly observation values")
    comparison_values: list[float | None] | None = Field(
        default=None, description="Optional comparison region values for teleconnection cross-correlation"
    )
    comparison_timestamps: list[str] | None = Field(
        default=None, description="Optional timestamps for comparison series"
    )
    start_year: int | None = Field(default=None, ge=1981, le=2025)
    end_year: int | None = Field(default=None, ge=1981, le=2025)
    mk_variant: Literal["standard", "hamed_rao"] = Field(default="standard")


class InvestigateRequest(BaseModel):
    case_id: str | None = Field(default=None)
    parameter: str = Field(default="T2M")
    primary_point: GeoPoint
    comparison_point: GeoPoint | None = Field(default=None)
    start_year: int = Field(default=1990, ge=1981, le=2025)
    end_year: int = Field(default=2025, ge=1981, le=2025)
    mk_variant: Literal["standard", "hamed_rao"] = Field(default="standard")


class ExplainRequest(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    parameter: str
    sens_slope_per_year: float
    p_value: float
    variance_reduction_pct: float
    years_to_significance: int = 0
    observation_years: float = 35.0
    region_name: str = "Selected Region"
    comparison_name: str | None = None
    comparison_slope_per_year: float | None = None
    cross_correlation_r: float | None = None
    case_id: str | None = None


def _build_deterministic_brief(
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
) -> dict[str, Any]:
    """Synthesize a physically grounded Detective Brief without external API dependencies."""
    param = parameter.upper()
    meta = get_parameter_metadata(param)
    is_sig = p_value < 0.05
    decade_rate = sens_slope_per_year * 10.0
    abs_lat = abs(lat)

    if abs_lat >= 60.0:
        band_label = "Polar / Cryosphere Zone"
    elif abs_lat >= 35.0:
        band_label = "Mid-Latitude Storm Track Belt"
    elif abs_lat >= 15.0:
        band_label = "Subtropical Hadley Cell Limb"
    else:
        band_label = "Equatorial / ITCZ Tropical Belt"

    # Verdict headline
    if is_sig:
        if comparison_slope_per_year is not None and (
            (sens_slope_per_year > 0 and comparison_slope_per_year < 0)
            or (sens_slope_per_year < 0 and comparison_slope_per_year > 0)
        ):
            verdict_headline = (
                f"Statistically Significant Opposite Regional Trends Detected (p = {p_value:.4f})"
            )
        else:
            direction = "Upward" if sens_slope_per_year > 0 else "Downward" if sens_slope_per_year < 0 else "Flat"
            verdict_headline = (
                f"Statistically Significant {direction} {meta['parameter_name']} Shift (p = {p_value:.4f})"
            )
    else:
        if years_to_significance >= 90:
            verdict_headline = (
                f"No Detectable Long-Term Slope Over {observation_years:.0f} Years (p = {p_value:.3f})"
            )
        else:
            verdict_headline = (
                f"Noise / Insufficient Window — Needs ~{years_to_significance} More Years for 95% Confidence"
            )

    # Mechanism explanation
    if case_id == "case_1_enso":
        mechanism = (
            f"Across {region_name} and {comparison_name or 'Maritime Continent Indonesia'}, shifts in the Pacific "
            "Walker Circulation govern tropical moisture transport. Episodic El Nino warm-pool displacements trigger "
            "convective bursts along coastal Peru while subsiding air alters Indonesian monsoon precipitation, "
            f"producing inverse monthly rainfall anomalies (r = {cross_correlation_r if cross_correlation_r is not None else 'N/A'}) "
            f"and diverging multi-decade slopes ({decade_rate:+.3f} vs {(comparison_slope_per_year or 0)*10:+.3f} {meta['unit']}/decade)."
        )
        reference = "NASA Earth Observatory — El Nino and Global Precipitation Patterns (GPM / MERRA-2)"
    elif case_id == "case_2_dipole":
        mechanism = (
            f"In the {region_name} ({band_label}), poleward expansion of the subtropical Hadley cell descending limb "
            f"and warmer atmospheric evaporative demand have driven sustained root-zone soil drying ({decade_rate:+.4f} {meta['unit']}/decade). "
            f"Simultaneously, shifting mid-latitude storm tracks have moistened {comparison_name or 'the Upper Midwest'} "
            f"({(comparison_slope_per_year or 0)*10:+.4f} {meta['unit']}/decade), creating a classic continental hydrological dipole."
        )
        reference = "NASA Earth Science / GLDAS & GRACE — North American Drought & Soil Moisture Monitoring"
    elif case_id == "case_3_arctic":
        mechanism = (
            f"{region_name} ({lat:.1f}°N) exhibits textbook Arctic Amplification ({decade_rate:+.2f} °C/decade): "
            "declining sea-ice and snow cover lower surface albedo, exposing darker ocean and tundra that absorb "
            "additional solar radiation and accelerate winter heat flux. By contrast, freshening and slowing of the "
            f"Atlantic Meridional Overturning Circulation (AMOC) near {comparison_name or 'the Subpolar North Atlantic'} "
            "suppresses regional surface warming (the North Atlantic 'Cold Blob')."
        )
        reference = "NASA GISS / Earth Observatory — Arctic Amplification & The North Atlantic Warming Hole"
    elif case_id == "case_4_amazon":
        mechanism = (
            f"Along the {region_name}, forest fragmentation and agricultural clearing weaken evapotranspiration-driven "
            "moisture recycling, lengthening the dry season and accelerating deep profile soil drying "
            f"({decade_rate:+.4f} {meta['unit']}/decade) compared to the more intact {comparison_name or 'Central Amazon Core'} "
            f"({(comparison_slope_per_year or 0)*10:+.4f} {meta['unit']}/decade)."
        )
        reference = "NASA Earth Observatory / MODIS & SMAP — Amazon Basin Canopy Stress & Moisture Recycling"
    else:
        if param == "T2M":
            if abs_lat >= 60.0:
                mechanism = (
                    f"In this {band_label} ({lat:.2f}°, {lon:.2f}°), snow- and ice-albedo feedbacks amplify surface "
                    f"radiative forcing, producing a deseasonalized trend of {decade_rate:+.3f} °C/decade."
                )
            else:
                mechanism = (
                    f"In this {band_label} ({lat:.2f}°, {lon:.2f}°), greenhouse radiative forcing modulated by land-atmosphere "
                    f"heat flux and regional circulation yields a deseasonalized air temperature rate of {decade_rate:+.3f} °C/decade."
                )
            reference = "NASA GISTEMP / MERRA-2 — Global Surface Temperature Anomaly Analysis"
        elif param in ("PRECTOTCORR", "QV2M"):
            mechanism = (
                f"In this {band_label} ({lat:.2f}°, {lon:.2f}°), thermodynamic Clausius-Clapeyron moistening (~7% more "
                "water vapor per °C of warming) interacts with shifting Hadley and storm-track convergence zones, "
                f"driving a deseasonalized rate of {decade_rate:+.4f} {meta['unit']}/decade."
            )
            reference = "NASA GPM Mission & Earth Observatory — Global Water Cycle & Atmospheric Moisture"
        elif param in ("GWETROOT", "GWETPROF"):
            mechanism = (
                f"In this {band_label} ({lat:.2f}°, {lon:.2f}°), soil moisture balance reflects the competition between "
                "precipitation supply and rising vapor-pressure-deficit evapotranspiration, yielding a net trend of "
                f"{decade_rate:+.4f} {meta['unit']}/decade."
            )
            reference = "NASA SMAP / GLDAS — Global Root-Zone Soil Moisture & Agricultural Drought"
        else:
            mechanism = (
                f"In this {band_label} ({lat:.2f}°, {lon:.2f}°), regional baroclinic wave activity and thermal expansion "
                f"shift surface pressure anomalies at {decade_rate:+.4f} {meta['unit']}/decade."
            )
            reference = "NASA MERRA-2 — Global Atmospheric Reanalysis Reference"

    if variance_reduction_pct >= 20.0:
        seasonality_note = (
            f"Stripping the annual 12-month seasonal cycle via STL decomposition removed {variance_reduction_pct:.1f}% "
            "of total series variance, preventing summer/winter oscillations from masking the underlying multi-decade signal."
        )
    else:
        seasonality_note = (
            f"STL decomposition removed {variance_reduction_pct:.1f}% seasonal variance; in this low-seasonality regime, "
            "interannual oscillations (such as ENSO or storm variability) dominate month-to-month anomalies."
        )

    if not is_sig:
        horizon_note = (
            f"Over the selected {observation_years:.1f}-year window, natural climate variability outweighs the trend signal "
            f"(p = {p_value:.4f}). Holding current slope and variance constant, ~{years_to_significance} additional years "
            "of observations are needed to cross the 95% confidence threshold."
        )
    else:
        horizon_note = (
            f"The {observation_years:.1f}-year baseline provides sufficient statistical power (Mann-Kendall p = {p_value:.5f} < 0.05) "
            "to distinguish this physical trend from natural climate noise."
        )

    return {
        "verdict_headline": verdict_headline,
        "physical_mechanism": mechanism,
        "seasonality_note": seasonality_note,
        "horizon_note": horizon_note,
        "reference": reference,
        "biome_zone": band_label,
        "ai_enhanced": False,
    }


async def _maybe_enhance_with_gemini(req: ExplainRequest, baseline: dict[str, Any]) -> dict[str, Any]:
    """Optionally refine the deterministic brief using Gemini 2.5 Flash if GEMINI_API_KEY is configured."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return baseline

    meta = get_parameter_metadata(req.parameter)
    prompt = (
        "You are a NASA Earth System Science communicator writing a concise 1-page Field Dossier.\n"
        "Return ONLY valid JSON with keys: verdict_headline, physical_mechanism, seasonality_note, horizon_note, reference.\n"
        f"Data context:\n"
        f"- Region: {req.region_name} ({req.lat:.2f}, {req.lon:.2f}), Biome: {baseline['biome_zone']}\n"
        f"- Variable: {meta['parameter_name']} ({req.parameter}) in {meta['unit']}\n"
        f"- Deseasonalized Sen's slope: {req.sens_slope_per_year:.4f} {meta['unit']}/yr\n"
        f"- Mann-Kendall p-value: {req.p_value:.5f}, STL variance removed: {req.variance_reduction_pct:.1f}%\n"
        f"- Observation window: {req.observation_years:.1f} years, years_to_significance: {req.years_to_significance}\n"
        f"- Comparison region: {req.comparison_name or 'None'}, slope={req.comparison_slope_per_year}, r={req.cross_correlation_r}\n"
        f"- Physical grounding draft: {baseline['physical_mechanism']}\n"
        "Keep every sentence crisp, accurate to the numbers above, and student-accessible (max 2 sentences per field)."
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3},
    }

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            data = resp.json()
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(raw_text)
        for key in ("verdict_headline", "physical_mechanism", "seasonality_note", "horizon_note", "reference"):
            if not isinstance(parsed.get(key), str) or not parsed[key].strip():
                return baseline
        return {
            **baseline,
            "verdict_headline": parsed["verdict_headline"].strip(),
            "physical_mechanism": parsed["physical_mechanism"].strip(),
            "seasonality_note": parsed["seasonality_note"].strip(),
            "horizon_note": parsed["horizon_note"].strip(),
            "reference": parsed["reference"].strip(),
            "ai_enhanced": True,
        }
    except Exception:
        return baseline


@app.get("/api/health")
def health_check() -> dict[str, str]:
    """Liveness check endpoint."""
    return {"status": "ok", "service": "TerraShift API"}


@app.get("/api/parameters")
def get_parameters() -> dict[str, Any]:
    """Return student-friendly NASA parameter translator metadata."""
    return {"parameters": PARAMETER_METADATA}


@app.get("/api/cases")
def get_cases() -> dict[str, Any]:
    """Return metadata for the 4 curated Detective Case Files plus parameter registry."""
    return {"cases": list_preset_cases(), "parameters": PARAMETER_METADATA}


@app.get("/api/cases/{case_id}")
async def get_case_detail(case_id: str) -> dict[str, Any]:
    """Run full investigation on a pre-cached Detective Case File."""
    preset = get_preset_case_series(case_id)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")
    c = preset["case"]
    req = InvestigateRequest(
        case_id=case_id,
        parameter=c["parameter"],
        primary_point=GeoPoint(**c["primary_point"]),
        comparison_point=GeoPoint(**c["comparison_point"]),
        start_year=c["default_window"][0],
        end_year=c["default_window"][1],
    )
    return await investigate_endpoint(req)


@app.post("/api/analyze")
def analyze_endpoint(req: AnalyzeRequest) -> dict[str, Any]:
    """Run STL decomposition, Mann-Kendall, Sen's slope, Student's t-test, and horizon analysis."""
    timestamps = req.timestamps
    values = req.values
    comp_values = req.comparison_values
    comp_timestamps = req.comparison_timestamps

    if req.start_year is not None or req.end_year is not None:
        s_yr = req.start_year or 1900
        e_yr = req.end_year or 2100
        if s_yr >= e_yr:
            raise HTTPException(status_code=400, detail="start_year must be less than end_year.")
        filtered = [
            (ts, val, comp_values[i] if comp_values and i < len(comp_values) else None)
            for i, (ts, val) in enumerate(zip(timestamps, values))
            if s_yr <= int(ts[:4]) <= e_yr
        ]
        timestamps = [row[0] for row in filtered]
        values = [row[1] for row in filtered]
        if comp_values is not None:
            comp_values = [row[2] for row in filtered]
            comp_timestamps = timestamps

    try:
        return analyze_series(
            timestamps=timestamps,
            values=values,
            comparison_values=comp_values,
            comparison_timestamps=comp_timestamps,
            mk_variant=req.mk_variant,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/investigate")
async def investigate_endpoint(req: InvestigateRequest) -> dict[str, Any]:
    """Hybrid NASA POWER fetch + STL & non-parametric trend investigation."""
    if req.start_year >= req.end_year:
        raise HTTPException(status_code=400, detail="start_year must be strictly less than end_year.")

    param = req.parameter.upper()
    primary_data: dict[str, Any] | None = None
    comp_data: dict[str, Any] | None = None

    # Fast zero-latency cache path for preset Case Files
    if req.case_id:
        preset = get_preset_case_series(req.case_id, req.start_year, req.end_year)
        if preset is not None and preset["case"]["parameter"].upper() == param:
            c_primary = preset["case"]["primary_point"]
            if (
                abs(c_primary["lat"] - req.primary_point.lat) < 0.05
                and abs(c_primary["lon"] - req.primary_point.lon) < 0.05
            ):
                primary_data = preset["primary"]
                if req.comparison_point is not None:
                    c_comp = preset["case"]["comparison_point"]
                    if (
                        abs(c_comp["lat"] - req.comparison_point.lat) < 0.05
                        and abs(c_comp["lon"] - req.comparison_point.lon) < 0.05
                    ):
                        comp_data = preset["comparison"]

    # Live / live_cache path
    try:
        if primary_data is None and req.comparison_point is not None:
            primary_data, comp_data = await asyncio.gather(
                fetch_nasa_monthly(
                    req.primary_point.lat, req.primary_point.lon, param, req.start_year, req.end_year
                ),
                fetch_nasa_monthly(
                    req.comparison_point.lat, req.comparison_point.lon, param, req.start_year, req.end_year
                ),
            )
        elif primary_data is None:
            primary_data = await fetch_nasa_monthly(
                req.primary_point.lat, req.primary_point.lon, param, req.start_year, req.end_year
            )
        elif req.comparison_point is not None and comp_data is None:
            comp_data = await fetch_nasa_monthly(
                req.comparison_point.lat, req.comparison_point.lon, param, req.start_year, req.end_year
            )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        analysis = analyze_series(
            timestamps=primary_data["timestamps"],
            values=primary_data["values"],
            comparison_values=comp_data["values"] if comp_data else None,
            comparison_timestamps=comp_data["timestamps"] if comp_data else None,
            mk_variant=req.mk_variant,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    ps = analysis["primary_stats"]
    tc = analysis["teleconnection"]
    brief = _build_deterministic_brief(
        lat=req.primary_point.lat,
        lon=req.primary_point.lon,
        parameter=param,
        sens_slope_per_year=ps["sens_slope_per_year"],
        p_value=ps["p_value"],
        variance_reduction_pct=ps["variance_reduction_pct"],
        years_to_significance=ps["years_to_significance"],
        observation_years=ps["observation_years"],
        region_name=req.primary_point.name,
        comparison_name=req.comparison_point.name if req.comparison_point else None,
        comparison_slope_per_year=tc["comparison_sens_slope_per_year"],
        cross_correlation_r=tc["cross_correlation_r"],
        case_id=req.case_id,
    )

    statuses = [primary_data["data_status"]]
    if comp_data:
        statuses.append(comp_data["data_status"])
    if "offline_fallback" in statuses:
        overall_status = "offline_fallback"
    elif "live" in statuses:
        overall_status = "live"
    else:
        overall_status = "cache"

    fallback_note = primary_data.get("fallback_note") or (comp_data.get("fallback_note") if comp_data else None)

    return {
        "request": req.model_dump(),
        "response": {
            "metadata": get_parameter_metadata(param),
            "data_status": overall_status,
            "fallback_note": fallback_note,
            "primary_bounding_box": primary_data["bounding_box"],
            "comparison_bounding_box": comp_data["bounding_box"] if comp_data else None,
            "primary_series": analysis["primary_series"],
            "primary_stats": analysis["primary_stats"],
            "comparison_series": analysis["comparison_series"],
            "comparison_stats": analysis["comparison_stats"],
            "teleconnection": analysis["teleconnection"],
            "detective_brief": brief,
        },
    }


@app.post("/api/explain")
async def explain_endpoint(req: ExplainRequest) -> dict[str, Any]:
    """Generate structured physical grounding brief (deterministic template + optional Gemini)."""
    baseline = _build_deterministic_brief(
        lat=req.lat,
        lon=req.lon,
        parameter=req.parameter,
        sens_slope_per_year=req.sens_slope_per_year,
        p_value=req.p_value,
        variance_reduction_pct=req.variance_reduction_pct,
        years_to_significance=req.years_to_significance,
        observation_years=req.observation_years,
        region_name=req.region_name,
        comparison_name=req.comparison_name,
        comparison_slope_per_year=req.comparison_slope_per_year,
        cross_correlation_r=req.cross_correlation_r,
        case_id=req.case_id,
    )
    return await _maybe_enhance_with_gemini(req, baseline)
