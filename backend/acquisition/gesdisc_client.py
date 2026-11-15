"""NASA GES DISC OPeNDAP subset URL builder and variable subset helpers."""

from __future__ import annotations

from typing import Any


def build_gesdisc_opendap_netcdf_url(
    base_opendap_url: str,
    variables: list[str] | None = None,
) -> str:
    """Build a GES DISC OPeNDAP NetCDF4 subset URL when base OPeNDAP endpoint is available."""
    cleaned = base_opendap_url.rstrip("/")
    if not cleaned.endswith(".nc4") and not cleaned.endswith(".nc"):
        nc4_url = f"{cleaned}.nc4"
    else:
        nc4_url = cleaned
    if variables:
        var_expr = ",".join(variables)
        return f"{nc4_url}?{var_expr}"
    return nc4_url


def describe_gesdisc_subset_capabilities(dataset_id: str) -> dict[str, Any]:
    """Describe official GES DISC server-side spatial/variable subset support honestly."""
    opendap_datasets = {
        "M2TMNXCHM",
        "M2TMNXAER_BC",
        "M2TMNXAER_OC",
        "M2TMNXAER_SO4",
        "M2TMNXAER_AOD",
        "M2TMNXSLV_T2M",
        "M2TMNXFLX_PRECTOT",
        "M2TMNXSLV_WIND",
        "M2TMNXSLV_QV2M",
        "M2TMNXLND_GWETROOT",
        "GPM_3IMERGM",
        "GLDAS_NOAH025_M_RZSM",
        "GLDAS_NOAH025_M_RUNOFF",
        "GLDAS_NOAH025_M_ET",
        "AIRX3STM_CH4",
        "AIRX3STM_RH",
    }
    supported = dataset_id in opendap_datasets
    return {
        "dataset_id": dataset_id,
        "provider": "NASA GES DISC",
        "supports_opendap_subsetting": supported,
        "output_format": "NetCDF-4 (.nc4)" if supported else "Native Granule",
        "requires_earthdata_login": True,
    }
