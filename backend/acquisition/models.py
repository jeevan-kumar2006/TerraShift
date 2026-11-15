"""Pydantic data models for the TerraShift Data Acquisition & Validation Subsystem."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class VariableSpec(BaseModel):
    variable_code: str
    variable_name: str
    domain: Literal["atmospheric", "climate", "hydrology", "vegetation"]
    primary_dataset_id: str
    secondary_dataset_ids: list[str] = Field(default_factory=list)
    scientific_justification: str
    physical_distinction_note: str
    canonical_units: str


class DatasetCatalogEntry(BaseModel):
    dataset_id: str
    dataset_name: str
    scientific_variable: str
    variable_code: str
    domain: Literal["atmospheric", "climate", "hydrology", "vegetation"]
    collection_concept_id: str | None = None
    product_version: str
    data_provider: str
    variable_names: list[str]
    units: str
    spatial_resolution: str
    temporal_resolution: str
    first_available_date: str
    last_available_date: str
    geographic_coverage: str
    file_format: str
    quality_flags: list[str] = Field(default_factory=list)
    authentication_required: bool
    auth_provider: str
    download_mechanism: str
    supports_spatial_subset: bool
    supports_temporal_subset: bool
    official_docs_url: str
    data_limitations: str
    scientific_justification: str


class AuthStatusReport(BaseModel):
    earthdata_authenticated: bool
    earthdata_method: str
    netrc_present: bool
    earthaccess_available: bool
    copernicus_configured: bool
    copernicus_method: str
    appeears_ready: bool
    missing_credentials: list[str] = Field(default_factory=list)
    setup_instructions: list[str] = Field(default_factory=list)


class GranuleMetadata(BaseModel):
    granule_id: str
    title: str
    collection_concept_id: str
    time_start: str | None = None
    time_end: str | None = None
    size_mb: float | None = None
    checksum: str | None = None
    checksum_algorithm: str | None = None
    download_url: str | None = None
    opendap_url: str | None = None
    format: str | None = None


class DownloadRequest(BaseModel):
    dataset_id: str = Field(..., min_length=2, max_length=64)
    variable: str | None = None
    start_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    region_id: str = Field(default="india", max_length=80)
    file_format: str | None = None
    max_granules: int = Field(default=3, ge=1, le=60)
    confirm_large_download: bool = Field(default=False)


class ValidationReport(BaseModel):
    file_path: str
    file_format: str
    file_size_bytes: int
    passed: bool
    dimensions: dict[str, int] = Field(default_factory=dict)
    coordinates: dict[str, Any] = Field(default_factory=dict)
    variables: list[str] = Field(default_factory=list)
    units: dict[str, str] = Field(default_factory=dict)
    fill_values: dict[str, Any] = Field(default_factory=dict)
    time_coverage: dict[str, Any] = Field(default_factory=dict)
    spatial_coverage: dict[str, Any] = Field(default_factory=dict)
    duplicate_timestamps_count: int = 0
    missing_timestamps_count: int = 0
    missing_value_pct: float = 0.0
    quality_flags_detected: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    validated_at: str


class QualityControlReport(BaseModel):
    dataset_id: str
    qc_profile: str
    raw_file_path: str
    validated_file_path: str | None = None
    total_observations: int = 0
    valid_after_qc: int = 0
    filtered_fill_count: int = 0
    filtered_out_of_range_count: int = 0
    filtered_qc_flag_count: int = 0
    applied_filters: list[str] = Field(default_factory=list)
    units_verified: str | None = None
    passed: bool = True
    notes: list[str] = Field(default_factory=list)


class SpatialSubsetResult(BaseModel):
    region_id: str
    region_name: str
    region_level: str
    boundary_file: str
    polygon_vertex_count: int
    grid_cells_total: int
    grid_cells_inside_mask: int
    original_resolution_preserved: bool
    weighting_method: str
    output_file: str
    variable_name: str
    units: str
    regional_mean: float | None = None
    regional_min: float | None = None
    regional_max: float | None = None
    valid_fraction: float = 0.0
    time_series: list[dict[str, Any]] = Field(default_factory=list)


class ManifestEntry(BaseModel):
    manifest_id: str
    timestamp: str
    dataset_id: str
    granule_id: str
    collection_concept_id: str | None = None
    variable_code: str
    region_id: str
    start_date: str
    end_date: str
    file_path: str
    file_format: str
    file_size_bytes: int
    sha256: str
    retrieval_status: str
    validation_status: str
    notes: str | None = None
