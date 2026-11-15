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

from ai_explainer import build_deterministic_brief, maybe_enhance_with_gemini, suggest_variables_for_region
from config import MIN_GRID_CELLS_WARNING
from nasa_service import (
    PARAMETER_METADATA,
    build_series_provenance,
    compute_bounding_box,
    INDIA_BOUNDS,
    fetch_nasa_monthly,
    fetch_partner_intel,
    fetch_region_power_monthly,
    get_parameter_metadata,
    get_preset_case_series,
    is_within_india_bounds,
    list_preset_cases,
    parse_external_timeseries,
)
from satellite_service import fetch_satellite_monthly, is_satellite_variable, normalize_satellite_id
from trend_map_service import compute_india_trend_map, get_trend_map_progress
from acquisition.dataset_registry import get_trend_variable_registry
from acquisition.spatial_subset import compute_terrain_quality_flags
try:
    from india_analytics import (
        INDIA_PHYSIOGRAPHIC_REGIONS,
        INDIA_SEASONS,
        analyze_india_seasons,
    )
except ImportError:
    from backend.india_analytics import (
        INDIA_PHYSIOGRAPHIC_REGIONS,
        INDIA_SEASONS,
        analyze_india_seasons,
    )
from stats_engine import analyze_series
import xarray as xr

try:
    from acquisition import (
        apply_quality_control,
        download_granules_parallel,
        download_power_regional_netcdf,
        extract_polygon_subset,
        get_auth_diagnostics,
        get_dataset_by_id,
        get_storage_summary,
        list_available_regions,
        list_catalog,
        load_region_polygon,
        read_manifest_entries,
        read_validation_reports,
        search_granules,
        validate_file,
    )
    from acquisition.models import DownloadRequest
    from acquisition.storage_manager import get_raw_path
    from acquisition.temporal_subset import parse_iso_date, validate_temporal_window
except ImportError:
    from backend.acquisition import (
        apply_quality_control,
        download_granules_parallel,
        download_power_regional_netcdf,
        extract_polygon_subset,
        get_auth_diagnostics,
        get_dataset_by_id,
        get_storage_summary,
        list_available_regions,
        list_catalog,
        load_region_polygon,
        read_manifest_entries,
        read_validation_reports,
        search_granules,
        validate_file,
    )
    from backend.acquisition.models import DownloadRequest
    from backend.acquisition.storage_manager import get_raw_path
    from backend.acquisition.temporal_subset import parse_iso_date, validate_temporal_window

app = FastAPI(
    title="TerraShift API",
    description="Earth System Trend Detective (India) — STL decomposition, Mann-Kendall, Sen's slope, and NASA Earth observation integration.",
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
    mann_kendall_s: float | None = None
    mann_kendall_tau: float
    z_score: float
    p_value: float
    t_statistic: float | None = None
    degrees_of_freedom: int | None = None
    t_test_p_value: float
    raw_p_value: float
    is_significant: bool
    sens_slope_per_year: float
    sens_slope_per_decade: float
    sens_slope_ci_lower: float | None = None
    sens_slope_ci_upper: float | None = None
    ols_slope_per_year: float
    ols_slope_per_decade: float | None = None
    ols_intercept: float | None = None
    lag1_autocorrelation: float | None = None
    autocorrelation_significant: bool | None = None
    outlier_count: int | None = None
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
    seasonal_mann_kendall: dict[str, Any] | None = None


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
    source_badge: str | None = None
    source_type: str | None = None
    region_coverage: dict[str, Any] | None = None
    quality_flags: list[str] | None = None
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
    primary_point: GeoPoint | None = Field(default=None)
    comparison_point: GeoPoint | None = Field(default=None)
    region_type: Literal["state", "district", "india"] | None = Field(default=None)
    region_id: str | None = Field(default=None)
    comparison_region_type: Literal["state", "district", "india"] | None = Field(default=None)
    comparison_region_id: str | None = Field(default=None)
    start_year: int = Field(default=1990, ge=1981, le=2025)
    end_year: int = Field(default=2025, ge=1981, le=2025)
    mk_variant: Literal["standard", "hamed_rao"] = Field(default="standard")

    @field_validator("parameter")
    @classmethod
    def clean_parameter(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("parameter cannot be empty.")
        return s

    @model_validator(mode="after")
    def check_years_and_target(self) -> InvestigateRequest:
        if self.start_year >= self.end_year:
            raise ValueError("start_year must be strictly less than end_year.")
        if self.primary_point is None and not self.region_id:
            raise ValueError("Either primary_point or region_id must be provided.")
        return self


class ImportSeriesRequest(BaseModel):
    raw_text: str = Field(..., description="Raw CSV or ASCII text exported from NASA Giovanni, GES DISC, or AppEEARS")
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


class PartnerIntelResponseModel(BaseModel):
    coordinates: dict[str, Any]
    cmr_collections: list[CmrCollectionModel]
    appeears_products: list[AppeearsProductModel]
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


_CASE_DETAIL_MEMO: dict[tuple[str, int | None, int | None, str], dict[str, Any]] = {}


@app.get("/api/cases", response_model=CasesListResponseModel)
async def get_cases() -> dict[str, Any]:
    """Return metadata for the 6 curated Detective Case Files plus parameter registry."""
    cases = list_preset_cases()
    if not _CASE_DETAIL_MEMO and not os.environ.get("GEMINI_API_KEY", "").strip():
        for c_item in cases:
            if c_item.get("cached"):
                try:
                    await get_case_detail(c_item["case_id"], start_year=None, end_year=None, mk_variant="standard")
                except Exception:
                    pass
    return {"cases": cases, "parameters": PARAMETER_METADATA}


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

    use_memo = not os.environ.get("GEMINI_API_KEY", "").strip()
    memo_key = (case_id, start_year, end_year, mk_variant)
    if use_memo and memo_key in _CASE_DETAIL_MEMO:
        return _CASE_DETAIL_MEMO[memo_key]

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
    res = await investigate_endpoint(req)
    if use_memo:
        _CASE_DETAIL_MEMO[memo_key] = res
    return res


@app.get("/api/partner-intel", response_model=PartnerIntelResponseModel)
async def partner_intel_endpoint(
    lat: float = Query(default=28.61, ge=-90.0, le=90.0),
    lon: float = Query(default=77.21, ge=-180.0, le=180.0),
    parameter: str = Query(default="T2M"),
    start_year: int = Query(default=1990, ge=1981, le=2025),
    end_year: int = Query(default=2025, ge=1981, le=2025),
) -> dict[str, Any]:
    """Query live NASA CMR (MODIS/GPM/OMI), AppEEARS, and Earthdata deep links."""
    if start_year >= end_year:
        raise HTTPException(status_code=400, detail="start_year must be strictly less than end_year.")
    clean_param = parameter.strip() or "T2M"
    return await fetch_partner_intel(lat, lon, clean_param, start_year, end_year)


@app.post("/api/import-series", response_model=InvestigateResponseModel)
def import_series_endpoint(req: ImportSeriesRequest) -> dict[str, Any]:
    """Parse external CSV/ASCII exported from NASA Giovanni, GES DISC Hydrology, or AppEEARS and analyze."""
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


def _resolve_region_point(region_id: str) -> tuple[GeoPoint, dict[str, Any]]:
    """Resolve a state/district/india region_id to its GeoPoint centroid and metadata."""
    try:
        geom, meta = load_region_polygon(region_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    centroid = geom.centroid
    point = GeoPoint(
        lat=round(float(centroid.y), 4),
        lon=round(float(centroid.x), 4),
        name=str(meta.get("name") or region_id),
    )
    return point, meta


def _build_source_badge(param: str) -> tuple[str, str]:
    """Return (source_badge, source_type) from TREND_VARIABLE_REGISTRY or metadata."""
    norm_sat = normalize_satellite_id(param)
    for item in get_trend_variable_registry():
        if item["id"] == norm_sat or item["id"].upper() == param.upper():
            if item["source_type"] == "satellite":
                return f"Satellite: {item['mission']} ({item['instrument']})", "satellite"
            return f"Model: {item['mission']}", "model/reanalysis"
    meta = get_parameter_metadata(param)
    return f"Model: {meta['mission_source']}", "model/reanalysis"


@app.post("/api/investigate", response_model=InvestigateResponseModel)
async def investigate_endpoint(req: InvestigateRequest) -> dict[str, Any]:
    """Hybrid NASA POWER + Earthdata satellite fetch + STL & non-parametric trend investigation."""
    primary_region_meta: dict[str, Any] | None = None
    comp_region_meta: dict[str, Any] | None = None

    primary_point = req.primary_point
    if primary_point is None and req.region_id:
        primary_point, primary_region_meta = _resolve_region_point(req.region_id)
    elif primary_point is not None and req.region_id:
        _, primary_region_meta = _resolve_region_point(req.region_id)

    if primary_point is None:
        raise HTTPException(status_code=422, detail="Either primary_point or region_id must be provided.")

    comp_point = req.comparison_point
    if comp_point is None and req.comparison_region_id:
        comp_point, comp_region_meta = _resolve_region_point(req.comparison_region_id)
    elif comp_point is not None and req.comparison_region_id:
        _, comp_region_meta = _resolve_region_point(req.comparison_region_id)

    if not is_within_india_bounds(primary_point.lat, primary_point.lon):
        raise HTTPException(
            status_code=422,
            detail="TerraShift scope is restricted exclusively to India (6.0°N–37.5°N, 68.0°E–97.5°E).",
        )
    if comp_point is not None:
        if not is_within_india_bounds(comp_point.lat, comp_point.lon):
            raise HTTPException(
                status_code=422,
                detail="TerraShift scope is restricted exclusively to India (6.0°N–37.5°N, 68.0°E–97.5°E).",
            )

    raw_param = req.parameter.strip()
    is_sat = is_satellite_variable(raw_param)
    param = normalize_satellite_id(raw_param) if is_sat else raw_param.upper()
    primary_data: dict[str, Any] | None = None
    comp_data: dict[str, Any] | None = None

    if req.case_id and not req.region_id and not is_sat:
        preset = get_preset_case_series(req.case_id, req.start_year, req.end_year)
        if preset is not None and preset["case"]["parameter"].upper() == param:
            c_primary = preset["case"]["primary_point"]
            if (
                abs(c_primary["lat"] - primary_point.lat) < 0.05
                and abs(c_primary["lon"] - primary_point.lon) < 0.05
            ):
                primary_data = preset["primary"]
                if comp_point is not None:
                    c_comp = preset["case"]["comparison_point"]
                    if (
                        abs(c_comp["lat"] - comp_point.lat) < 0.05
                        and abs(c_comp["lon"] - comp_point.lon) < 0.05
                    ):
                        comp_data = preset["comparison"]

    async def _fetch_target(pt: GeoPoint, reg_id: str | None) -> dict[str, Any]:
        if is_sat:
            return await fetch_satellite_monthly(
                dataset_id=param,
                start_year=req.start_year,
                end_year=req.end_year,
                lat=None if reg_id else pt.lat,
                lon=None if reg_id else pt.lon,
                region_id=reg_id,
            )
        if reg_id:
            return await fetch_region_power_monthly(
                region_id=reg_id,
                parameter=param,
                start_year=req.start_year,
                end_year=req.end_year,
            )
        return await fetch_nasa_monthly(pt.lat, pt.lon, param, req.start_year, req.end_year)

    try:
        if primary_data is None and comp_point is not None:
            primary_data, comp_data = await asyncio.gather(
                _fetch_target(primary_point, req.region_id),
                _fetch_target(comp_point, req.comparison_region_id),
            )
        elif primary_data is None:
            primary_data = await _fetch_target(primary_point, req.region_id)
        elif comp_point is not None and comp_data is None:
            comp_data = await _fetch_target(comp_point, req.comparison_region_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Observation fetch error: {exc}") from exc

    if primary_data is None:
        raise HTTPException(status_code=500, detail="Failed to retrieve observation series for primary target.")

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
        lat=primary_point.lat,
        lon=primary_point.lon,
        parameter=param,
        sens_slope_per_year=ps["sens_slope_per_year"],
        p_value=ps["p_value"],
        variance_reduction_pct=ps["variance_reduction_pct"],
        years_to_significance=ps["years_to_significance"],
        observation_years=ps["observation_years"],
        region_name=primary_point.name,
        comparison_name=comp_point.name if comp_point else None,
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
            lat=primary_point.lat,
            lon=primary_point.lon,
            parameter=param,
            sens_slope_per_year=ps["sens_slope_per_year"],
            p_value=ps["p_value"],
            variance_reduction_pct=ps["variance_reduction_pct"],
            years_to_significance=ps["years_to_significance"],
            observation_years=ps["observation_years"],
            region_name=primary_point.name,
            comparison_name=comp_point.name if comp_point else None,
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
    region_coverage = primary_data.get("region_coverage")
    quality_flags: list[str] = list(primary_data.get("quality_flags") or [])
    if region_coverage and isinstance(region_coverage.get("grid_cells_used"), int):
        if region_coverage["grid_cells_used"] < MIN_GRID_CELLS_WARNING:
            warn_msg = (
                f"Low grid coverage: only {region_coverage['grid_cells_used']} grid cell(s) "
                f"covered inside polygon (recommended >= {MIN_GRID_CELLS_WARNING})."
            )
            if warn_msg not in quality_flags:
                quality_flags.append(warn_msg)
    if not quality_flags and req.region_id:
        try:
            geom, _ = load_region_polygon(req.region_id)
            quality_flags = compute_terrain_quality_flags(
                region_id=req.region_id,
                geom=geom,
                grid_cells_used=int((region_coverage or {}).get("grid_cells_used", 1)),
            )
        except Exception:
            pass

    source_badge, source_type = _build_source_badge(param)

    return {
        "request": req.model_dump(),
        "response": {
            "metadata": get_parameter_metadata(param),
            "data_status": overall_status,
            "dataset_tag": overall_dataset_tag,
            "fallback_note": fallback_note,
            "source_badge": source_badge,
            "source_type": source_type,
            "region_coverage": region_coverage,
            "quality_flags": quality_flags or None,
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


@app.get("/api/satellite/variables")
def satellite_variables_endpoint() -> dict[str, Any]:
    """List all supported satellite & model/reanalysis trend variables with DOI/citations and units."""
    items = get_trend_variable_registry()
    return {
        "variables": items,
        "satellite_count": sum(1 for item in items if item["source_type"] == "satellite"),
        "model_count": sum(1 for item in items if item["source_type"] != "satellite"),
    }


@app.get("/api/trend-map")
async def trend_map_endpoint(
    variable: str = Query(default="T2M"),
    level: Literal["state", "district"] = Query(default="state"),
    start: int = Query(default=1990, ge=1981, le=2025),
    end: int = Query(default=2025, ge=1981, le=2025),
    season: Literal["annual", "DJF", "MAM", "JJAS", "ON"] = Query(default="annual"),
) -> dict[str, Any]:
    """Compute India choropleth trend map with Benjamini-Hochberg FDR and data-driven legend range."""
    if start >= end:
        raise HTTPException(status_code=400, detail="start must be strictly less than end.")
    try:
        return await compute_india_trend_map(
            variable=variable,
            level=level,
            start_year=start,
            end_year=end,
            season=season,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/trend-map/progress")
def trend_map_progress_endpoint(cache_id: str = Query(..., min_length=2)) -> dict[str, Any]:
    """Return progress for an in-flight /api/trend-map computation."""
    return get_trend_map_progress(cache_id)


@app.get("/api/suggest-variables")
async def suggest_variables_endpoint(
    region: str = Query(..., min_length=2, description="India region_id or state/district name"),
) -> dict[str, Any]:
    """Suggest relevant Earth observation variables for an Indian region from computed features."""
    try:
        point, meta = _resolve_region_point(region)
        area_km2 = meta.get("area_km2")
        return await suggest_variables_for_region(
            region_id=region,
            region_name=point.name,
            lat=point.lat,
            lon=point.lon,
            area_km2=float(area_km2) if area_km2 is not None else None,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Variable suggestion failed: {exc}") from exc


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


@app.get("/api/acquisition/catalog")
async def acquisition_catalog_endpoint(
    domain: str | None = Query(default=None),
    variable_code: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return official 19-variable Earth observation catalog, availability matrix, and storage layout."""
    payload = list_catalog(domain=domain, variable_code=variable_code)
    payload["storage_summary"] = get_storage_summary()
    return payload


@app.get("/api/acquisition/auth-status")
async def acquisition_auth_status_endpoint() -> dict[str, Any]:
    """Return non-secret NASA Earthdata Login and Copernicus CDS authentication readiness diagnostics."""
    return get_auth_diagnostics()


@app.get("/api/acquisition/boundaries")
async def acquisition_boundaries_endpoint() -> dict[str, Any]:
    """Return supported India polygon boundaries across macro-zones, states/UTs, and districts."""
    regions = list_available_regions()
    return {"count": len(regions), "regions": regions}


@app.get("/api/acquisition/cmr-search")
async def acquisition_cmr_search_endpoint(
    dataset_id: str | None = Query(default=None),
    collection_concept_id: str | None = Query(default=None),
    start_date: str = Query(default="2024-01-01"),
    end_date: str = Query(default="2024-03-31"),
    region_id: str = Query(default="india"),
    page_size: int = Query(default=10, ge=1, le=50),
) -> dict[str, Any]:
    """Search official NASA CMR granules constrained by dataset concept ID, temporal window, and India polygon bbox."""
    try:
        s_norm, e_norm = validate_temporal_window(start_date, end_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    concept = collection_concept_id
    entry = get_dataset_by_id(dataset_id) if dataset_id else None
    if dataset_id and entry is None:
        raise HTTPException(status_code=404, detail=f"Unknown dataset_id '{dataset_id}'.")
    if entry and not concept:
        concept = entry.get("collection_concept_id")

    if not concept:
        return {
            "dataset_id": dataset_id,
            "collection_concept_id": None,
            "region_id": region_id,
            "granules": [],
            "note": "Dataset uses direct regional/CDS API rather than NASA CMR granule search.",
        }

    try:
        geom, region_meta = load_region_polygon(region_id)
        bbox = geom.bounds  # (minx, miny, maxx, maxy)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        granules = await search_granules(
            collection_concept_id=concept,
            start_date=s_norm,
            end_date=e_norm,
            bounding_box=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
            page_size=page_size,
            max_pages=1,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"NASA CMR search failed for concept '{concept}': {type(exc).__name__}",
        ) from exc

    return {
        "dataset_id": dataset_id,
        "collection_concept_id": concept,
        "region_id": region_meta["region_id"],
        "region_name": region_meta["region_name"],
        "bounding_box": [round(float(x), 3) for x in bbox],
        "start_date": s_norm,
        "end_date": e_norm,
        "count": len(granules),
        "granules": granules,
    }


@app.get("/api/acquisition/manifest")
async def acquisition_manifest_endpoint() -> dict[str, Any]:
    """Return persisted download manifest, validation reports, and storage directory summary."""
    return {
        "manifest": read_manifest_entries(),
        "validations": read_validation_reports(),
        "storage": get_storage_summary(),
    }


def _clamp_power_box_for_region(geom: Any) -> tuple[float, float, float, float]:
    """Center a <= 8 deg x 8 deg bounding box inside India for NASA POWER Regional NetCDF queries."""
    minx, miny, maxx, maxy = (float(v) for v in geom.bounds)
    if (maxx - minx) <= 9.5 and (maxy - miny) <= 9.5:
        return round(miny, 2), round(maxy, 2), round(minx, 2), round(maxx, 2)
    cent = geom.centroid
    cx, cy = float(cent.x), float(cent.y)
    return round(cy - 4.0, 2), round(cy + 4.0, 2), round(cx - 4.0, 2), round(cx + 4.0, 2)


@app.post("/api/acquisition/download")
async def acquisition_download_endpoint(req: DownloadRequest) -> dict[str, Any]:
    """Run guarded dataset acquisition, structural validation, QC, and real India polygon extraction."""
    entry = get_dataset_by_id(req.dataset_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Unknown dataset_id '{req.dataset_id}'.")

    try:
        s_norm, e_norm = validate_temporal_window(req.start_date, req.end_date)
        geom, region_meta = load_region_polygon(req.region_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    s_dt = parse_iso_date(s_norm)
    e_dt = parse_iso_date(e_norm)
    months_spanned = max(1, (e_dt.year - s_dt.year) * 12 + (e_dt.month - s_dt.month) + 1)

    if (months_spanned > 12 or req.max_granules > 12) and not req.confirm_large_download:
        est_granules = min(months_spanned, req.max_granules)
        return {
            "status": "confirmation_required",
            "dataset_id": req.dataset_id,
            "region_id": region_meta["region_id"],
            "estimated_months": months_spanned,
            "estimated_granules": est_granules,
            "estimated_size_mb": round(est_granules * 12.0, 1),
            "message": (
                f"Requested range spans {months_spanned} months (up to {req.max_granules} granules). "
                "Set confirm_large_download=true to proceed with large archive retrieval."
            ),
        }

    # Path A: Live Unauthenticated NASA POWER Regional NetCDF Download + Validation + QC + Polygon Masking
    if entry["dataset_id"] == "NASA_POWER_AG":
        var_name = (req.variable or "T2M").upper()
        if var_name not in entry["variable_names"]:
            var_name = "T2M"
        lat_min, lat_max, lon_min, lon_max = _clamp_power_box_for_region(geom)
        raw_file = get_raw_path(
            entry["domain"],
            var_name,
            "NASA_POWER",
            f"POWER_Regional_{region_meta['region_id']}_{s_dt.year}_{e_dt.year}_{var_name}.nc",
        )
        dl_res = await download_power_regional_netcdf(
            parameters=[var_name],
            latitude_min=lat_min,
            latitude_max=lat_max,
            longitude_min=lon_min,
            longitude_max=lon_max,
            start_year=s_dt.year,
            end_year=e_dt.year,
            dest_path=raw_file,
            community="AG",
        )
        if dl_res.get("status") not in ("downloaded", "skipped_existing"):
            return {
                "status": dl_res.get("status", "failed"),
                "dataset_id": entry["dataset_id"],
                "auth_required": False,
                "download": dl_res,
                "message": dl_res.get("error", "NASA POWER Regional NetCDF download failed."),
            }

        val_report = validate_file(raw_file, expected_format="NETCDF")
        qc_report = apply_quality_control(
            raw_file,
            dataset_id=entry["dataset_id"],
            domain=entry["domain"],
            variable_name=var_name,
        )
        subset_result = None
        if qc_report.validated_file_path and Path(qc_report.validated_file_path).exists():
            with xr.open_dataset(qc_report.validated_file_path) as vds:
                # If polygon is country-wide and POWER box was clamped around centroid, mask by full polygon cleanly
                target_region_for_subset = region_meta["region_id"]
                subset_result = extract_polygon_subset(
                    ds=vds,
                    variable_name=var_name,
                    region_id=target_region_for_subset,
                    output_stem=f"POWER_{var_name}_{target_region_for_subset}_{s_dt.year}_{e_dt.year}",
                )

        return {
            "status": "completed",
            "dataset_id": entry["dataset_id"],
            "retrieval_mode": "live_nasa_power_regional_netcdf",
            "auth_required": False,
            "bounding_box_requested": [lon_min, lat_min, lon_max, lat_max],
            "download": dl_res,
            "validation": val_report.model_dump(),
            "qc": qc_report.model_dump(),
            "spatial_subset": subset_result,
        }

    # Path B: NASA Earthdata / CMR Datasets
    auth = get_auth_diagnostics()
    concept = entry.get("collection_concept_id")
    granules: list[dict[str, Any]] = []
    if concept:
        bbox = geom.bounds
        try:
            granules = await search_granules(
                collection_concept_id=concept,
                start_date=s_norm,
                end_date=e_norm,
                bounding_box=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
                page_size=min(20, req.max_granules),
                max_pages=1,
            )
        except Exception:
            granules = []

    if not auth["earthdata_authenticated"]:
        pilot_nc = get_raw_path("atmospheric", "CO", "MOPITT", "MOP03JM_202401_202403_India_pilot.nc")
        pilot_inspection = None
        if entry["dataset_id"] == "MOP03JM" and pilot_nc.exists():
            val_p = validate_file(pilot_nc, expected_format="NETCDF")
            qc_p = apply_quality_control(pilot_nc, dataset_id="MOP03JM", domain="atmospheric", variable_name="CO_Total_Column")
            sub_p = None
            if qc_p.validated_file_path:
                with xr.open_dataset(qc_p.validated_file_path) as pds:
                    try:
                        sub_p = extract_polygon_subset(
                            ds=pds,
                            variable_name="CO_Total_Column",
                            region_id=region_meta["region_id"],
                            output_stem=f"MOP03JM_CO_{region_meta['region_id']}_pilot",
                        )
                    except ValueError:
                        sub_p = None
            pilot_inspection = {
                "retrieval_mode": "pilot_cmr_fixture_due_to_missing_edl_auth",
                "validation": val_p.model_dump(),
                "qc": qc_p.model_dump(),
                "spatial_subset": sub_p,
            }

        return {
            "status": "auth_required",
            "dataset_id": entry["dataset_id"],
            "auth_required": True,
            "auth_status": auth,
            "cmr_granules_discovered": len(granules),
            "granules": granules[: req.max_granules],
            "pilot_inspection": pilot_inspection,
            "message": (
                f"NASA CMR discovered {len(granules)} real granule(s) for {entry['dataset_id']}, "
                "but protected granule download requires NASA Earthdata Login (EARTHDATA_TOKEN or ~/.netrc)."
            ),
        }

    # Authenticated CMR download path
    selected = granules[: req.max_granules]
    if not selected:
        return {
            "status": "no_granules_found",
            "dataset_id": entry["dataset_id"],
            "auth_required": False,
            "message": f"No CMR granules matched {entry['dataset_id']} in window {s_norm} to {e_norm}.",
        }

    dl_results = await download_granules_parallel(
        dataset_id=entry["dataset_id"],
        collection_concept_id=concept,
        variable_code=entry["variable_code"],
        domain=entry["domain"],
        source_tag=entry["dataset_id"],
        region_id=region_meta["region_id"],
        start_date=s_norm,
        end_date=e_norm,
        granules=selected,
    )
    validations = []
    for item in dl_results:
        fpath = item.get("file_path")
        if fpath and Path(fpath).exists() and item.get("status") in ("downloaded", "skipped_existing", "skipped_duplicate"):
            validations.append(validate_file(Path(fpath)).model_dump())

    return {
        "status": "completed",
        "dataset_id": entry["dataset_id"],
        "auth_required": False,
        "granules_requested": len(selected),
        "downloads": dl_results,
        "validations": validations,
    }


class IndiaSeasonalAnalysisRequest(BaseModel):
    case_id: str | None = None
    lat: float | None = None
    lon: float | None = None
    parameter: str = "T2M"
    start_year: int = 1981
    end_year: int = 2025
    baseline_start: int = 1991
    baseline_end: int = 2020
    timestamps: list[str] | None = None
    values: list[float | None] | None = None


@app.get("/api/india/regions")
def get_india_regions() -> dict[str, Any]:
    """Return India geographical bounds, IMD seasonal definitions, and physiographic regions."""
    return {
        "bounds": INDIA_BOUNDS,
        "seasons": {s["code"]: s for s in INDIA_SEASONS},
        "physiographic_regions": [
            {
                "id": r["region_id"],
                "name": r["name"],
                "lat": r["representative_point"]["lat"],
                "lon": r["representative_point"]["lon"],
                "focus": r["climate_profile"],
            }
            for r in INDIA_PHYSIOGRAPHIC_REGIONS
        ],
    }


@app.get("/api/india/boundaries-geojson")
def get_india_boundaries_geojson() -> dict[str, Any]:
    """Serve the India states GeoJSON boundary file for frontend map overlays."""
    repo_root = Path(__file__).resolve().parent.parent
    geojson_path = repo_root / "data" / "boundaries" / "states" / "india_states.geojson"
    if not geojson_path.exists():
        geojson_path = repo_root / "data" / "boundaries" / "india" / "india_outline.geojson"
    if not geojson_path.exists():
        raise HTTPException(status_code=404, detail="India boundary GeoJSON file not found.")
    with geojson_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


@app.post("/api/india/seasonal-analysis")
async def india_seasonal_analysis_endpoint(req: IndiaSeasonalAnalysisRequest) -> dict[str, Any]:
    """Run India-specific 4-season (JF, MAM, JJAS, OND) and annual anomaly trend analysis."""
    param = req.parameter.upper()
    series_meta: dict[str, Any] = {}

    if req.timestamps is not None and req.values is not None:
        if len(req.timestamps) != len(req.values):
            raise HTTPException(status_code=422, detail="timestamps and values must have equal length.")
        timestamps = req.timestamps
        values = req.values
        series_meta = {
            "source_mode": "custom_series",
            "parameter": param,
            "location": "Custom India Series",
        }
    elif req.case_id:
        case_payload = get_preset_case_series(req.case_id, req.start_year, req.end_year)
        if not case_payload:
            raise HTTPException(status_code=404, detail=f"Preset case '{req.case_id}' not found.")
        case_meta = case_payload["case"]
        primary = case_payload["primary"]
        timestamps = primary["timestamps"]
        values = primary["values"]
        param = case_meta.get("parameter", param)
        series_meta = {
            "case_id": req.case_id,
            "case_title": case_meta.get("title"),
            "location": case_meta.get("primary_point", {}).get("name", req.case_id),
            "lat": primary.get("lat"),
            "lon": primary.get("lon"),
            "parameter": param,
            "units": case_meta.get("unit"),
            "source_mode": primary.get("data_status", "cache"),
        }
    elif req.lat is not None and req.lon is not None:
        if not is_within_india_bounds(req.lat, req.lon):
            raise HTTPException(
                status_code=422,
                detail="TerraShift scope is restricted exclusively to India (6.0°N–37.5°N, 68.0°E–97.5°E).",
            )
        fetched = await fetch_nasa_monthly(
            lat=req.lat,
            lon=req.lon,
            parameter=param,
            start_year=req.start_year,
            end_year=req.end_year,
        )
        if not fetched or not fetched.get("timestamps"):
            raise HTTPException(status_code=502, detail="Failed to retrieve NASA POWER data for India coordinates.")
        timestamps = fetched["timestamps"]
        values = fetched["values"]
        series_meta = {
            "location": fetched.get("location") or f"{req.lat:.2f}°N, {req.lon:.2f}°E",
            "lat": req.lat,
            "lon": req.lon,
            "parameter": param,
            "units": fetched.get("units"),
            "source_mode": fetched.get("source_mode", "live"),
        }
    else:
        raise HTTPException(
            status_code=422,
            detail="Provide either (timestamps & values), case_id, or (lat & lon) within India.",
        )

    analysis = analyze_india_seasons(
        timestamps,
        values,
        baseline_start=req.baseline_start,
        baseline_end=req.baseline_end,
    )
    return {
        "meta": series_meta,
        "analysis": analysis,
    }


@app.get("/api/india/regional-comparison")
async def india_regional_comparison(
    start_year: int = 1990,
    end_year: int = 2025,
) -> dict[str, Any]:
    """Compute real seasonal & long-term trend comparison across all cached India case locations."""
    cases = list_preset_cases()
    rows: list[dict[str, Any]] = []
    for case in cases:
        cid = case["case_id"]
        payload = get_preset_case_series(cid, start_year, end_year)
        if not payload:
            continue
        case_meta = payload["case"]
        for role_key, point_key in (("primary", "primary_point"), ("comparison", "comparison_point")):
            loc_data = payload.get(role_key)
            if not loc_data or not loc_data.get("timestamps"):
                continue
            ts = loc_data["timestamps"]
            vals = loc_data["values"]
            seasonal = analyze_india_seasons(ts, vals, baseline_start=1991, baseline_end=2020)
            overall = analyze_series(ts, vals)
            p_stats = overall.get("primary_stats", {})
            rows.append({
                "case_id": cid,
                "case_title": case_meta.get("title"),
                "role": "primary" if role_key == "primary" else "compare",
                "location": case_meta.get(point_key, {}).get("name", cid),
                "lat": loc_data.get("lat"),
                "lon": loc_data.get("lon"),
                "parameter": case_meta.get("parameter"),
                "units": case_meta.get("unit"),
                "source_mode": loc_data.get("data_status", "cache"),
                "n_months": seasonal.get("eda", {}).get("n_valid", len(ts)),
                "mean_value": seasonal.get("eda", {}).get("mean"),
                "std_value": seasonal.get("eda", {}).get("std"),
                "sen_slope_per_decade": p_stats.get("sens_slope_per_decade"),
                "mk_p_value": p_stats.get("p_value"),
                "mk_significant": p_stats.get("is_significant"),
                "seasons": {
                    s_key: {
                        "name": s_val.get("name"),
                        "sen_slope_per_decade": s_val.get("sen_slope_per_decade"),
                        "ols_slope_per_decade": s_val.get("ols_slope_per_decade"),
                        "mk_p_value": s_val.get("mk_p_value"),
                        "holm_adjusted_p": s_val.get("holm_adjusted_p"),
                        "significant_holm": s_val.get("significant_holm"),
                    }
                    for s_key, s_val in (seasonal.get("seasons") or {}).items()
                },
            })
    return {
        "start_year": start_year,
        "end_year": end_year,
        "baseline_period": "1991-2020",
        "count": len(rows),
        "rows": rows,
    }


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("ENVIRONMENT", "development").lower() == "development"
    uvicorn.run("main:app", host=host, port=port, reload=reload)
