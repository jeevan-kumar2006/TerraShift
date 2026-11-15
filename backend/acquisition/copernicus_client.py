"""Copernicus Climate Data Store (CDS) client wrapper for ERA5 and CAMS monthly datasets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .earthdata_auth import get_auth_diagnostics


def build_era5_request(
    *,
    variables: list[str],
    years: list[int],
    months: list[int] | None = None,
    area_bbox_nwse: tuple[float, float, float, float] | None = (38.0, 68.0, 6.0, 98.0),
) -> dict[str, Any]:
    """Build an official Copernicus CDS request payload for ERA5 Monthly Means."""
    req: dict[str, Any] = {
        "product_type": ["monthly_averaged_reanalysis"],
        "variable": variables,
        "year": [str(y) for y in years],
        "month": [f"{m:02d}" for m in (months or list(range(1, 13)))],
        "time": ["00:00"],
        "data_format": "netcdf",
        "download_format": "unarchived",
    }
    if area_bbox_nwse is not None:
        # CDS area format: [North, West, South, East]
        req["area"] = list(area_bbox_nwse)
    return req


def download_cds_dataset(
    *,
    collection_id: str,
    request_payload: dict[str, Any],
    target_path: Path,
) -> tuple[bool, str]:
    """Execute a Copernicus CDS download when cdsapi and credentials are configured."""
    diag = get_auth_diagnostics()
    if not diag["copernicus_configured"]:
        return (
            False,
            "Copernicus CDS credentials missing. Set CDSAPI_KEY / ~/.cdsapirc from cds.climate.copernicus.eu.",
        )
    try:
        import cdsapi  # type: ignore
    except ImportError:
        return False, "cdsapi package is not installed."

    target_path.parent.mkdir(parents=True, exist_ok=True)
    client = cdsapi.Client()
    client.retrieve(collection_id, request_payload, str(target_path))
    return True, f"Downloaded Copernicus CDS dataset to {target_path}"
