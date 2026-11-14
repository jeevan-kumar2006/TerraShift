"""FastAPI router for TerraShift — Earth System Trend Detective."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Literal


def _load_local_env() -> None:
    """Load key=value pairs from backend/.env into os.environ without overwriting existing vars."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_local_env()

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from ai_explainer import build_deterministic_brief, maybe_enhance_with_gemini
from nasa_service import (
    PARAMETER_METADATA,
    build_series_provenance,
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


def _get_cors_origins() -> list[str]:
    """Retrieve allowed CORS origins from environment variable or standard defaults."""
    raw = os.environ.get("CORS_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]


_origins = _get_cors_origins()
_has_wildcard = "*" in _origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins if not _has_wildcard else ["*"],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$" if not _has_wildcard else None,
    allow_credentials=not _has_wildcard,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Standardized API Error Handlers
# ---------------------------------------------------------------------------


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Format Pydantic request validation errors into a human-readable and structured payload."""
    errors = exc.errors()
    error_messages = []
    for err in errors:
        loc = ".".join(str(x) for x in err.get("loc", []) if x != "body")
        msg = err.get("msg", "Validation error")
        error_messages.append(f"{loc}: {msg}" if loc else msg)
    combined_detail = "; ".join(error_messages) if error_messages else "Request validation failed."
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": combined_detail,
            "error": True,
            "error_type": "validation_error",
            "errors": jsonable_encoder(errors),
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Standardize HTTP exception format across all endpoints."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error": True,
            "status_code": exc.status_code,
        },
    )


# ---------------------------------------------------------------------------
# Data Models: Request & Response Schemas
# ---------------------------------------------------------------------------


class GeoPoint(BaseModel):
    name: str = Field(default="Selected Region", max_length=120)
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)


class BoundingBoxModel(BaseModel):
    south: float
    north: float
    west: float
    east: float


class ParameterMetaModel(BaseModel):
    parameter_code: str
    parameter_name: str
    unit: str
    mission_source: str
    collection: str | None = None
    data_type: str | None = None
    temporal_resolution: str | None = None
    resolution: str
    plain_definition: str
    question: str
    positive_label: str
    negative_label: str


class PresetCaseMetaModel(BaseModel):
    case_id: str
    title: str
    short_title: str
    mechanism_teaser: str
    parameter: str
    parameter_name: str
    unit: str
    mission_label: str
    primary_point: GeoPoint
    comparison_point: GeoPoint | None = None
    default_window: list[int]
    data_source: str
    cached: bool


class AnalyzedSeriesModel(BaseModel):
    timestamps: list[str]
    raw_values: list[float | None]
    seasonal_cycle: list[float | None]
    deseasonalized_anomalies: list[float | None]
    trend_line: list[float | None]
    ci_upper: list[float | None]
    ci_lower: list[float | None]


class SeriesStatsModel(BaseModel):
    mann_kendall_tau: float
    z_score: float
    p_value: float
    t_test_p_value: float
    raw_p_value: float
    is_significant: bool
    sens_slope_per_year: float
    sens_slope_per_decade: float
    sens_slope_ci_lower: float | None = None
    sens_slope_ci_upper: float | None = None
    ols_slope_per_year: float
    years_to_significance: int
    estimated_additional_observation_years: int | None = None
    variance_reduction_pct: float
    seasonal_amplitude: float
    observation_months: int
    observation_years: float
    mk_variant: str
    valid_months: int | None = None
    missing_months: int | None = None
    missing_pct: float | None = None
    interpolated_months: int | None = None
    max_consecutive_missing: int | None = None
    duplicate_timestamps_merged: int | None = None
    ci_methodology: str | None = None
    horizon_assumptions: str | None = None


class TeleconnectionSummaryModel(BaseModel):
    enabled: bool
    comparison_anomalies: list[float | None]
    comparison_sens_slope_per_year: float | None = None
    comparison_sens_slope_per_decade: float | None = None
    comparison_is_significant: bool = False
    comparison_p_value: float | None = None
    cross_correlation_r: float | None = None
    cross_correlation_p_value: float | None = None


class DetectiveBriefModel(BaseModel):
    verdict_headline: str
    physical_mechanism: str
    seasonality_note: str
    horizon_note: str
    reference: str
    biome_zone: str
    methodology_note: str | None = None
    limitations_note: str | None = None
    ai_enhanced: bool


class SeriesProvenanceModel(BaseModel):
    source: str
    collection: str
    data_type: str
    community: str
    parameter: str
    parameter_name: str
    units: str
    temporal_resolution: str
    spatial_resolution: str
    start_date: str | None = None
    end_date: str | None = None
    requested_coordinates: dict[str, float]
    actual_coordinates: dict[str, float]
    retrieval_status: str
    dataset_tag: str
    fallback_used: bool
    fallback_distance_km: float
    is_synthetic: bool


class InvestigateDataModel(BaseModel):
    metadata: ParameterMetaModel
    data_status: Literal["live", "cache", "cached", "offline_fallback", "imported", "synthetic"]
    dataset_tag: Literal["live", "cached", "offline_fallback", "imported", "synthetic"] | None = None
    fallback_note: str | None = None
    primary_bounding_box: BoundingBoxModel
    comparison_bounding_box: BoundingBoxModel | None = None
    primary_provenance: SeriesProvenanceModel | None = None
    comparison_provenance: SeriesProvenanceModel | None = None
    primary_series: AnalyzedSeriesModel
    primary_stats: SeriesStatsModel
    comparison_series: AnalyzedSeriesModel | None = None
    comparison_stats: SeriesStatsModel | None = None
    teleconnection: TeleconnectionSummaryModel
    detective_brief: DetectiveBriefModel


class InvestigateResponseModel(BaseModel):
    request: dict[str, Any]
    response: InvestigateDataModel


class AnalyzeRequest(BaseModel):
    timestamps: list[str] = Field(..., description="Monthly YYYY-MM timestamps")
    values: list[float | None] = Field(..., description="Monthly observation values")
    comparison_values: list[float | None] | None = Field(
        default=None, description="Optional comparison region values for teleconnection cross-correlation"
    )
    comparison_timestamps: list[str] | None = Field(
        default=None, description="Optional timestamps for comparison series"
    )
    start_year: int | None = Field(default=None, ge=1800, le=2100)
    end_year: int | None = Field(default=None, ge=1800, le=2100)
    mk_variant: Literal["standard", "hamed_rao"] = Field(default="standard")

    @model_validator(mode="after")
    def validate_lengths_and_window(self) -> AnalyzeRequest:
        if len(self.timestamps) != len(self.values):
            raise ValueError(
                f"timestamps and values must have identical lengths (got {len(self.timestamps)} vs {len(self.values)})."
            )
        if len(self.timestamps) < 24:
            raise ValueError(
                f"At least 24 monthly observations are required for STL decomposition (got {len(self.timestamps)})."
            )
        if self.comparison_values is not None and self.comparison_timestamps is not None:
            if len(self.comparison_values) != len(self.comparison_timestamps):
                raise ValueError("comparison_timestamps and comparison_values must have identical lengths.")
        if self.start_year is not None and self.end_year is not None:
            if self.start_year >= self.end_year:
                raise ValueError("start_year must be strictly less than end_year.")
        return self


class AnalyzeResponseModel(BaseModel):
    primary_series: AnalyzedSeriesModel
    primary_stats: SeriesStatsModel
    teleconnection: TeleconnectionSummaryModel
    comparison_series: AnalyzedSeriesModel | None = None
    comparison_stats: SeriesStatsModel | None = None


class InvestigateRequest(BaseModel):
    case_id: str | None = Field(default=None)
    parameter: str = Field(default="T2M")
    primary_point: GeoPoint
    comparison_point: GeoPoint | None = Field(default=None)
    start_year: int = Field(default=1990, ge=1981, le=2025)
    end_year: int = Field(default=2025, ge=1981, le=2025)
    mk_variant: Literal["standard", "hamed_rao"] = Field(default="standard")

    @field_validator("parameter")
    @classmethod
    def clean_parameter(cls, v: str) -> str:
        s = v.strip().upper()
        if not s:
            raise ValueError("parameter cannot be empty.")
        return s

    @model_validator(mode="after")
    def check_years(self) -> InvestigateRequest:
        if self.start_year >= self.end_year:
            raise ValueError("start_year must be strictly less than end_year.")
        return self


class ImportSeriesRequest(BaseModel):
    raw_text: str = Field(..., description="Raw CSV, ASCII, or KNMI 13-col text exported from Giovanni, GES DISC, AppEEARS, KNMI, or NOAA CDO")
    source_hint: str = Field(default="auto")
    region_name: str = Field(default="Imported Agency Series")
    lat: float = Field(default=0.0, ge=-90.0, le=90.0)
    lon: float = Field(default=0.0, ge=-180.0, le=180.0)
    unit: str | None = Field(default=None)
    mk_variant: Literal["standard", "hamed_rao"] = Field(default="standard")
    start_year: int | None = Field(default=None, ge=1800, le=2100)
    end_year: int | None = Field(default=None, ge=1800, le=2100)

    @field_validator("raw_text")
    @classmethod
    def validate_raw_text(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Uploaded time-series file is empty.")
        return v

    @model_validator(mode="after")
    def check_years(self) -> ImportSeriesRequest:
        if self.start_year is not None and self.end_year is not None:
            if self.start_year >= self.end_year:
                raise ValueError("start_year must be strictly less than end_year.")
        return self


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
    provenance: dict[str, Any] | None = None
    sens_slope_ci_lower: float | None = None
    sens_slope_ci_upper: float | None = None
    missing_pct: float | None = None

    @field_validator("parameter")
    @classmethod
    def clean_parameter(cls, v: str) -> str:
        return v.strip().upper()


class HealthResponseModel(BaseModel):
    status: str
    service: str
    version: str
    cache_available: bool
    timestamp: str | None = None


class StatusResponseModel(BaseModel):
    status: str
    service: str
    version: str
    cache_available: bool
    cases_count: int
    live_cache_count: int
    parameters: list[str]
    environment: str


class CasesListResponseModel(BaseModel):
    cases: list[PresetCaseMetaModel]
    parameters: dict[str, Any]


class PartnerDeepLinkModel(BaseModel):
    id: str
    agency: str
    title: str
    category: str
    description: str
    url: str


class CmrCollectionModel(BaseModel):
    short_name: str
    title: str
    data_center: str
    summary: str


class AppeearsProductModel(BaseModel):
    product_id: str
    platform: str
    description: str
    resolution: str


class CsaStationModel(BaseModel):
    type: str
    station_name: str
    station_id: str
    province: str
    sample_date: str
    sample_metric: str


class PartnerIntelResponseModel(BaseModel):
    coordinates: dict[str, Any]
    cmr_collections: list[CmrCollectionModel]
    appeears_products: list[AppeearsProductModel]
    csa_geomet_stations: list[CsaStationModel]
    noaa_cdo_status: str
    deep_links: list[PartnerDeepLinkModel]


# ---------------------------------------------------------------------------
# Physics-Grounded Brief Synthesis & Optional Gemini Augmentation (delegated to ai_explainer.py)
# ---------------------------------------------------------------------------


def _build_deterministic_brief(**kwargs: Any) -> dict[str, Any]:
    return build_deterministic_brief(**kwargs)


async def _maybe_enhance_with_gemini(req: ExplainRequest, baseline: dict[str, Any]) -> dict[str, Any]:
    return await maybe_enhance_with_gemini(
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
        baseline=baseline,
        provenance=req.provenance,
        sens_slope_ci_lower=req.sens_slope_ci_lower,
        sens_slope_ci_upper=req.sens_slope_ci_upper,
        missing_pct=req.missing_pct,
    )


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


@app.get("/")
def root_info() -> dict[str, str]:
    """Root info endpoint describing TerraShift service and primary links."""
    return {
        "service": "TerraShift API",
        "description": "Earth System Trend Detective API with STL decomposition, Mann-Kendall, and Multi-Agency integration.",
        "version": "2.0.0",
        "status": "ok",
        "docs": "/docs",
        "health": "/api/health",
        "cases": "/api/cases",
    }


@app.get("/api/health", response_model=HealthResponseModel)
@app.get("/health", response_model=HealthResponseModel)
def health_check() -> dict[str, Any]:
    """Liveness and readiness check endpoint."""
    cache_path = Path(__file__).resolve().parent / "cases_cache.json"
    cache_ok = cache_path.is_file()
    return {
        "status": "ok" if cache_ok else "degraded",
        "service": "TerraShift API",
        "version": "2.0.0",
        "cache_available": cache_ok,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/status", response_model=StatusResponseModel)
def status_endpoint() -> dict[str, Any]:
    """Detailed system diagnostic status endpoint."""
    cache_path = Path(__file__).resolve().parent / "cases_cache.json"
    cache_ok = cache_path.is_file()
    cases_count = 0
    live_cache_count = 0
    if cache_ok:
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                c_data = json.load(f)
                cases_count = len(c_data.get("cases", []))
                live_cache_count = len(c_data.get("live_cache", {}))
        except Exception:
            pass

    return {
        "status": "ok" if cache_ok else "degraded",
        "service": "TerraShift API",
        "version": "2.0.0",
        "cache_available": cache_ok,
        "cases_count": cases_count,
        "live_cache_count": live_cache_count,
        "parameters": list(PARAMETER_METADATA.keys()),
        "environment": os.environ.get("ENVIRONMENT", "development"),
    }


@app.get("/api/parameters")
def get_parameters() -> dict[str, Any]:
    """Return student-friendly NASA parameter translator metadata."""
    return {"parameters": PARAMETER_METADATA}


@app.get("/api/cases", response_model=CasesListResponseModel)
def get_cases() -> dict[str, Any]:
    """Return metadata for the 6 curated Detective Case Files plus parameter registry."""
    return {"cases": list_preset_cases(), "parameters": PARAMETER_METADATA}


@app.get("/api/cases/{case_id}", response_model=InvestigateResponseModel)
async def get_case_detail(
    case_id: str,
    start_year: int | None = Query(default=None, ge=1981, le=2025),
    end_year: int | None = Query(default=None, ge=1981, le=2025),
    mk_variant: Literal["standard", "hamed_rao"] = Query(default="standard"),
) -> dict[str, Any]:
    """Run full investigation on a pre-cached Detective Case File with optional window slicing."""
    if start_year is not None and end_year is not None and start_year >= end_year:
        raise HTTPException(status_code=400, detail="start_year must be strictly less than end_year.")

    preset = get_preset_case_series(case_id, start_year, end_year)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")
    c = preset["case"]
    win = c.get("default_window", [1990, 2025])
    s_yr = start_year if start_year is not None else win[0]
    e_yr = end_year if end_year is not None else win[1]

    req = InvestigateRequest(
        case_id=case_id,
        parameter=c["parameter"],
        primary_point=GeoPoint(**c["primary_point"]),
        comparison_point=GeoPoint(**c["comparison_point"]) if c.get("comparison_point") else None,
        start_year=s_yr,
        end_year=e_yr,
        mk_variant=mk_variant,
    )
    return await investigate_endpoint(req)


@app.get("/api/partner-intel", response_model=PartnerIntelResponseModel)
async def partner_intel_endpoint(
    lat: float = Query(default=78.22, ge=-90.0, le=90.0),
    lon: float = Query(default=15.63, ge=-180.0, le=180.0),
    parameter: str = Query(default="T2M"),
    start_year: int = Query(default=1990, ge=1981, le=2025),
    end_year: int = Query(default=2025, ge=1981, le=2025),
) -> dict[str, Any]:
    """Query live NASA CMR (SWOT/SeaWiFS/MODIS), AppEEARS, CSA GeoMet, NOAA CDO, and deep links."""
    if start_year >= end_year:
        raise HTTPException(status_code=400, detail="start_year must be strictly less than end_year.")
    clean_param = parameter.strip().upper() or "T2M"
    return await fetch_partner_intel(lat, lon, clean_param, start_year, end_year)


@app.post("/api/import-series", response_model=InvestigateResponseModel)
def import_series_endpoint(req: ImportSeriesRequest) -> dict[str, Any]:
    """Parse external CSV/ASCII/.dat from Giovanni, GES DISC Hydrology, AppEEARS, KNMI, or NOAA CDO and analyze."""
    try:
        timestamps, values, detected_meta = parse_external_timeseries(req.raw_text, req.source_hint)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if req.start_year is not None or req.end_year is not None:
        s_yr = req.start_year or 1800
        e_yr = req.end_year or 2100
        filtered = [
            (ts, val)
            for ts, val in zip(timestamps, values)
            if s_yr <= int(ts[:4]) <= e_yr
        ]
        if len(filtered) < 24:
            raise HTTPException(
                status_code=400,
                detail=f"Selected window {s_yr}–{e_yr} contains {len(filtered)} records; at least 24 months are required.",
            )
        timestamps = [row[0] for row in filtered]
        values = [row[1] for row in filtered]

    try:
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
    is_synthetic = detected_meta.get("is_synthetic") == "true"
    data_status = "synthetic" if is_synthetic else "imported"
    dataset_tag = data_status

    primary_provenance = build_series_provenance(
        parameter=meta["parameter_code"],
        requested_lat=req.lat,
        requested_lon=req.lon,
        actual_lat=req.lat,
        actual_lon=req.lon,
        timestamps=timestamps,
        retrieval_status="synthetic_demo" if is_synthetic else "imported_user_file",
        fallback_distance_km=0.0,
        source_override=detected_meta.get("mission_source", meta.get("mission_source", "External Agency Import")),
        collection_override=detected_meta.get("collection", meta.get("collection", "Imported CSV/Text")),
        data_type_override=meta.get("data_type", "External Time Series"),
        unit_override=meta["unit"],
        spatial_resolution_override=meta.get("spatial_resolution", "User-supplied point/region"),
        is_synthetic=is_synthetic,
    )

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
        provenance=primary_provenance,
        sens_slope_ci_lower=ps.get("sens_slope_ci_lower"),
        sens_slope_ci_upper=ps.get("sens_slope_ci_upper"),
        missing_pct=ps.get("missing_pct"),
    )

    fallback_note = (
        "SYNTHETIC DEMO DATA: Generated for format demonstration and testing only — not real NASA or agency observations."
        if is_synthetic
        else f"Analyzed {len(timestamps)} monthly records imported from {detected_meta['mission_source']}."
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
            "data_status": data_status,
            "dataset_tag": dataset_tag,
            "fallback_note": fallback_note,
            "primary_bounding_box": compute_bounding_box(req.lat, req.lon),
            "comparison_bounding_box": None,
            "primary_provenance": primary_provenance,
            "comparison_provenance": None,
            "primary_series": analysis["primary_series"],
            "primary_stats": analysis["primary_stats"],
            "comparison_series": None,
            "comparison_stats": None,
            "teleconnection": analysis["teleconnection"],
            "detective_brief": brief,
        },
    }


@app.post("/api/analyze", response_model=AnalyzeResponseModel)
def analyze_endpoint(req: AnalyzeRequest) -> dict[str, Any]:
    """Run STL decomposition, Mann-Kendall, Sen's slope, Student's t-test, and horizon analysis."""
    timestamps = req.timestamps
    values = req.values
    comp_values = req.comparison_values
    comp_timestamps = req.comparison_timestamps

    if req.start_year is not None or req.end_year is not None:
        s_yr = req.start_year or 1800
        e_yr = req.end_year or 2100
        try:
            filtered = [
                (ts, val, comp_values[i] if comp_values and i < len(comp_values) else None)
                for i, (ts, val) in enumerate(zip(timestamps, values))
                if s_yr <= int(ts[:4]) <= e_yr
            ]
        except (ValueError, IndexError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid timestamp format encountered: {exc}") from exc

        if len(filtered) < 24:
            raise HTTPException(
                status_code=400,
                detail=f"Filtered window {s_yr}–{e_yr} leaves {len(filtered)} records; at least 24 months are required.",
            )

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


@app.post("/api/investigate", response_model=InvestigateResponseModel)
async def investigate_endpoint(req: InvestigateRequest) -> dict[str, Any]:
    """Hybrid NASA POWER fetch + STL & non-parametric trend investigation."""
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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Observation fetch error: {exc}") from exc

    if primary_data is None:
        raise HTTPException(status_code=500, detail="Failed to retrieve observation series for primary point.")

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
    primary_prov = primary_data.get("provenance")
    comp_prov = comp_data.get("provenance") if comp_data else None
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
        provenance=primary_prov,
        sens_slope_ci_lower=ps.get("sens_slope_ci_lower"),
        sens_slope_ci_upper=ps.get("sens_slope_ci_upper"),
        missing_pct=ps.get("missing_pct"),
    )
    if os.environ.get("GEMINI_API_KEY", "").strip():
        explain_req = ExplainRequest(
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
            provenance=primary_prov,
            sens_slope_ci_lower=ps.get("sens_slope_ci_lower"),
            sens_slope_ci_upper=ps.get("sens_slope_ci_upper"),
            missing_pct=ps.get("missing_pct"),
        )
        brief = await _maybe_enhance_with_gemini(explain_req, brief)

    statuses = [primary_data["data_status"]]
    if comp_data:
        statuses.append(comp_data["data_status"])
    if "offline_fallback" in statuses:
        overall_status = "offline_fallback"
        overall_dataset_tag = "offline_fallback"
    elif "live" in statuses:
        overall_status = "live"
        overall_dataset_tag = "live"
    else:
        overall_status = "cache"
        overall_dataset_tag = "cached"

    fallback_note = primary_data.get("fallback_note") or (comp_data.get("fallback_note") if comp_data else None)

    return {
        "request": req.model_dump(),
        "response": {
            "metadata": get_parameter_metadata(param),
            "data_status": overall_status,
            "dataset_tag": overall_dataset_tag,
            "fallback_note": fallback_note,
            "primary_bounding_box": primary_data["bounding_box"],
            "comparison_bounding_box": comp_data["bounding_box"] if comp_data else None,
            "primary_provenance": primary_prov,
            "comparison_provenance": comp_prov,
            "primary_series": analysis["primary_series"],
            "primary_stats": analysis["primary_stats"],
            "comparison_series": analysis["comparison_series"],
            "comparison_stats": analysis["comparison_stats"],
            "teleconnection": analysis["teleconnection"],
            "detective_brief": brief,
        },
    }


@app.post("/api/explain", response_model=DetectiveBriefModel)
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
        provenance=req.provenance,
        sens_slope_ci_lower=req.sens_slope_ci_lower,
        sens_slope_ci_upper=req.sens_slope_ci_upper,
        missing_pct=req.missing_pct,
    )
    return await _maybe_enhance_with_gemini(req, baseline)


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("ENVIRONMENT", "development").lower() == "development"
    uvicorn.run("main:app", host=host, port=port, reload=reload)
