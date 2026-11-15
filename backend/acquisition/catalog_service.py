"""Catalog discovery service combining local registry metadata with availability matrices."""

from __future__ import annotations

from typing import Any

from .dataset_registry import DATASET_CATALOG, VARIABLE_SPECS, export_catalog_files, get_dataset_by_id
from .earthdata_auth import get_auth_diagnostics


def list_catalog(domain: str | None = None, variable_code: str | None = None) -> dict[str, Any]:
    """Return full or filtered 19-variable catalog along with availability matrix."""
    export_catalog_files()
    datasets = DATASET_CATALOG
    variables = VARIABLE_SPECS
    if domain:
        d_low = domain.lower().strip()
        datasets = [d for d in datasets if d["domain"] == d_low]
        variables = [v for v in variables if v["domain"] == d_low]
    if variable_code:
        v_up = variable_code.upper().strip()
        datasets = [d for d in datasets if d["variable_code"] == v_up]
        variables = [v for v in variables if v["variable_code"] == v_up]

    availability_matrix = []
    for var in VARIABLE_SPECS:
        primary = get_dataset_by_id(var["primary_dataset_id"])
        availability_matrix.append(
            {
                "variable_code": var["variable_code"],
                "variable_name": var["variable_name"],
                "domain": var["domain"],
                "primary_dataset": var["primary_dataset_id"],
                "primary_provider": primary["data_provider"] if primary else "",
                "auth_required": primary["authentication_required"] if primary else True,
                "supports_spatial_subset": primary["supports_spatial_subset"] if primary else False,
                "canonical_units": var["canonical_units"],
                "physical_distinction_note": var["physical_distinction_note"],
            }
        )

    return {
        "variables": variables,
        "datasets": datasets,
        "availability_matrix": availability_matrix,
        "auth_status": get_auth_diagnostics(),
    }
