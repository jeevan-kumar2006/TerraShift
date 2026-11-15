"""TerraShift modular Earth-observation Data Acquisition, Validation & QC Subsystem."""

from .catalog_service import list_catalog
from .cmr_client import search_collections, search_granules
from .dataset_registry import DATASET_CATALOG, VARIABLE_SPECS, export_catalog_files, get_dataset_by_id
from .download_manager import download_file_resumable, download_granules_parallel, download_power_regional_netcdf
from .earthdata_auth import get_auth_diagnostics
from .file_validator import validate_file
from .hdf5_inspector import inspect_hdf5
from .manifest_manager import (
    append_manifest_entry,
    read_manifest_entries,
    read_validation_reports,
    write_acquisition_log,
)
from .netcdf_inspector import inspect_netcdf
from .quality_control import apply_quality_control, resolve_qc_profile
from .spatial_subset import extract_polygon_subset, list_available_regions, load_region_polygon
from .storage_manager import ensure_storage_layout, get_storage_summary

__all__ = [
    "DATASET_CATALOG",
    "VARIABLE_SPECS",
    "append_manifest_entry",
    "apply_quality_control",
    "download_file_resumable",
    "download_granules_parallel",
    "download_power_regional_netcdf",
    "ensure_storage_layout",
    "export_catalog_files",
    "extract_polygon_subset",
    "get_auth_diagnostics",
    "get_dataset_by_id",
    "get_storage_summary",
    "inspect_hdf5",
    "inspect_netcdf",
    "list_available_regions",
    "list_catalog",
    "load_region_polygon",
    "read_manifest_entries",
    "read_validation_reports",
    "resolve_qc_profile",
    "search_collections",
    "search_granules",
    "validate_file",
    "write_acquisition_log",
]
