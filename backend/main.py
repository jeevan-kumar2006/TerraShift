"""FastAPI router for TerraShift — Earth System Trend Detective."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Literal

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from nasa_service import (
    PARAMETER_METADATA,
    compute_bounding_box,
    fetch_nasa_monthly,
    fetch_partner_intel,
    get_parameter_metadata,
    get_preset_case_series,
    list_preset_cases,
    parse_external_timeseries,
)
from stats_engine import analyze_series

app = FastAPI(
    title="TerraShift API",
    description="Earth System Trend Detective — STL decomposition, Mann-Kendall, Sen's slope, and Multi-Agency NASA / NOAA / KNMI / CSA integration.",
    version="2.0.0",
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


class ImportSeriesRequest(BaseModel):
    raw_text: str = Field(..., description="Raw CSV, ASCII, or KNMI 13-col text exported from Giovanni, GES DISC, AppEEARS, KNMI, or NOAA CDO")
    source_hint: str = Field(default="auto")
    region_name: str = Field(default="Imported Agency Series")
    lat: float = Field(default=0.0, ge=-90.0, le=90.0)
    lon: float = Field(default=0.0, ge=-180.0, le=180.0)
    unit: str | None = Field(default=None)
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

    if case_id == "case_1_enso":
        mechanism = (
            f"Across {region_name} and {comparison_name or 'Maritime Continent Indonesia'}, shifts in the Pacific "
            "Walker Circulation govern tropical moisture transport. Episodic El Nino warm-pool displacements trigger "
            "convective bursts along coastal Peru while subsiding air alters Indonesian monsoon precipitation, "
            f"producing inverse monthly rainfall anomalies (r = {cross_correlation_r if cross_correlation_r is not None else 'N/A'}) "
            f"and diverging multi-decade slopes ({decade_rate:+.3f} vs {(comparison_slope_per_year or 0)*10:+.3f} {meta['unit']}/decade)."
        )
        reference = "NASA Earth Observatory / Giovanni — El Nino & Global Precipitation Patterns (GPM / MERRA-2)"
    elif case_id == "case_2_dipole":
        mechanism = (
            f"In the {region_name} ({band_label}), poleward expansion of the subtropical Hadley cell descending limb "
            f"and warmer atmospheric evaporative demand have driven sustained root-zone soil drying ({decade_rate:+.4f} {meta['unit']}/decade). "
            f"Simultaneously, shifting mid-latitude storm tracks have moistened {comparison_name or 'the Upper Midwest'} "
            f"({(comparison_slope_per_year or 0)*10:+.4f} {meta['unit']}/decade), creating a classic continental hydrological dipole."
        )
        reference = "NASA GES DISC Hydrology Time Series & GLDAS/SMAP — North American Soil Moisture Dipole"
    elif case_id == "case_3_arctic":
        mechanism = (
            f"{region_name} ({lat:.1f}°N) exhibits textbook Arctic Amplification ({decade_rate:+.2f} °C/decade): "
            "declining sea-ice and snow cover lower surface albedo, exposing darker ocean and tundra that absorb "
            "additional solar radiation and accelerate winter heat flux. By contrast, freshening and slowing of the "
            f"Atlantic Meridional Overturning Circulation (AMOC) near {comparison_name or 'the Subpolar North Atlantic'} "
            "suppresses regional surface warming (the North Atlantic 'Cold Blob')."
        )
        reference = "NASA GISS / KNMI Climate Explorer — Arctic Amplification & The North Atlantic Warming Hole"
    elif case_id == "case_4_amazon":
        mechanism = (
            f"Along the {region_name}, forest fragmentation and agricultural clearing weaken evapotranspiration-driven "
            "moisture recycling, lengthening the dry season and accelerating deep profile soil drying "
            f"({decade_rate:+.4f} {meta['unit']}/decade) compared to the more intact {comparison_name or 'Central Amazon Core'} "
            f"({(comparison_slope_per_year or 0)*10:+.4f} {meta['unit']}/decade)."
        )
        reference = "NASA AppEEARS / MODIS NDVI & GLDAS — Amazon Basin Canopy Stress & Moisture Recycling"
    elif case_id == "case_5_seawifs_coastal":
        mechanism = (
            f"In the {region_name}, spring/summer watershed precipitation and river discharge pulses deliver nutrient-rich "
            f"freshwater plumes that drive strong seasonal chlorophyll-a and runoff cycles ({decade_rate:+.3f} {meta['unit']}/decade), "
            f"contrasting sharply with the stratified oligotrophic waters of {comparison_name or 'the Offshore Gulf Loop Current'} "
            f"(r = {cross_correlation_r if cross_correlation_r is not None else 'N/A'}). Removing the strong annual river-discharge cycle "
            "via STL is essential before testing for multi-decade eutrophication or hydro-climatic trends."
        )
        reference = "NASA NTRS 20090042747 — Time-Series Analysis of Remotely-Sensed SeaWiFS Chlorophyll in River-Influenced Coastal Regions"
    elif case_id == "case_6_csa_swot_rcm":
        mechanism = (
            f"Across {region_name} ({lat:.1f}°N), high-latitude cryosphere warming ({decade_rate:+.2f} °C/decade) accelerates "
            "permafrost thaw, river ice breakup, and coastal wetland transformation monitored by Canada's RADARSAT Constellation "
            "Mission (RCM) Synthetic Aperture Radar and the NASA/CNES/CSA SWOT surface-water elevation mission, outpacing the "
            f"temperate {comparison_name or 'Great Lakes / St. Lawrence Corridor'} ({(comparison_slope_per_year or 0)*10:+.2f} °C/decade)."
        )
        reference = "Canadian Space Agency (CSA) RCM, SWOT Mission & Geo.ca / MSC GeoMet Climate & Hydrometric Archive"
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
            reference = "NASA GISTEMP / MERRA-2 & NOAA NCEI CDO — Global Surface Temperature Anomaly Analysis"
        elif param in ("PRECTOTCORR", "QV2M"):
            mechanism = (
                f"In this {band_label} ({lat:.2f}°, {lon:.2f}°), thermodynamic Clausius-Clapeyron moistening (~7% more "
                "water vapor per °C of warming) interacts with shifting Hadley and storm-track convergence zones, "
                f"driving a deseasonalized rate of {decade_rate:+.4f} {meta['unit']}/decade."
            )
            reference = "NASA GPM / Giovanni & SWOT Mission — Global Water Cycle & Surface Hydrology"
        elif param in ("GWETROOT", "GWETPROF"):
            mechanism = (
                f"In this {band_label} ({lat:.2f}°, {lon:.2f}°), soil moisture balance reflects the competition between "
                "precipitation supply and rising vapor-pressure-deficit evapotranspiration, yielding a net trend of "
                f"{decade_rate:+.4f} {meta['unit']}/decade."
            )
            reference = "NASA GES DISC Hydrology Time Series, AppEEARS & SMAP/GLDAS — Global Soil Moisture"
        else:
            mechanism = (
                f"In this {band_label} ({lat:.2f}°, {lon:.2f}°), regional baroclinic wave activity and thermal expansion "
                f"shift surface anomalies at {decade_rate:+.4f} {meta['unit']}/decade."
            )
            reference = "NASA MERRA-2 & KNMI Climate Explorer — Global Atmospheric Reanalysis Reference"

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
        "You are a NASA & CSA Earth System Science communicator writing a concise 1-page Field Dossier.\n"
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
    """Return metadata for the 6 curated Detective Case Files plus parameter registry."""
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


@app.get("/api/partner-intel")
async def partner_intel_endpoint(
    lat: float = Query(default=78.22, ge=-90.0, le=90.0),
    lon: float = Query(default=15.63, ge=-180.0, le=180.0),
    parameter: str = Query(default="T2M"),
    start_year: int = Query(default=1990, ge=1981, le=2025),
    end_year: int = Query(default=2025, ge=1981, le=2025),
) -> dict[str, Any]:
    """Query live NASA CMR (SWOT/SeaWiFS/MODIS), AppEEARS, CSA GeoMet, NOAA CDO, and deep links."""
    return await fetch_partner_intel(lat, lon, parameter, start_year, end_year)


@app.post("/api/import-series")
def import_series_endpoint(req: ImportSeriesRequest) -> dict[str, Any]:
    """Parse external CSV/ASCII/.dat from Giovanni, GES DISC Hydrology, AppEEARS, KNMI, or NOAA CDO and analyze."""
    try:
        timestamps, values, detected_meta = parse_external_timeseries(req.raw_text, req.source_hint)
        analysis = analyze_series(
            timestamps=timestamps,
            values=values,
            mk_variant=req.mk_variant,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    unit = req.unit.strip() if req.unit and req.unit.strip() else detected_meta["unit"]
    meta = {
        "parameter_code": detected_meta["parameter_code"],
        "parameter_name": detected_meta["parameter_name"],
        "unit": unit,
        "mission_source": detected_meta["mission_source"],
        "resolution": "Imported Point / Regional Time Series",
        "plain_definition": f"User-imported monthly time series from {detected_meta['mission_source']}.",
        "question": "Custom Multi-Agency Time-Series Import",
        "positive_label": "Upward Trend",
        "negative_label": "Downward Trend",
    }

    ps = analysis["primary_stats"]
    s_yr = int(timestamps[0][:4])
    e_yr = int(timestamps[-1][:4])
    brief = _build_deterministic_brief(
        lat=req.lat,
        lon=req.lon,
        parameter=meta["parameter_code"],
        sens_slope_per_year=ps["sens_slope_per_year"],
        p_value=ps["p_value"],
        variance_reduction_pct=ps["variance_reduction_pct"],
        years_to_significance=ps["years_to_significance"],
        observation_years=ps["observation_years"],
        region_name=req.region_name,
    )

    return {
        "request": {
            "case_id": "imported_agency_series",
            "parameter": meta["parameter_code"],
            "primary_point": {"name": req.region_name, "lat": req.lat, "lon": req.lon},
            "comparison_point": None,
            "start_year": s_yr,
            "end_year": e_yr,
            "mk_variant": req.mk_variant,
        },
        "response": {
            "metadata": meta,
            "data_status": "live",
            "fallback_note": f"Analyzed {len(timestamps)} monthly records imported from {detected_meta['mission_source']}.",
            "primary_bounding_box": compute_bounding_box(req.lat, req.lon),
            "comparison_bounding_box": None,
            "primary_series": analysis["primary_series"],
            "primary_stats": analysis["primary_stats"],
            "comparison_series": None,
            "comparison_stats": None,
            "teleconnection": analysis["teleconnection"],
            "detective_brief": brief,
        },
    }


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
