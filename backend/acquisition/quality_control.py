"""Product-specific scientific quality control pipelines producing validated NetCDF files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

from .models import QualityControlReport
from .storage_manager import get_validated_path


QC_PROFILE_SPECS: dict[str, dict[str, Any]] = {
    "MOPITT_CO": {
        "fill_values": [-9999.0, -9999],
        "physical_bounds": (0.0, 2000.0),  # ppbv default; column molec/cm^2 adjusted dynamically if units indicate molec
        "flag_tokens": ("df", "error", "qual", "qc"),
        "description": "Remove MOPITT fill values (-9999), retrieval error flags, and non-physical CO concentrations.",
    },
    "MERRA2_AER_CHM": {
        "fill_values": [1e15, 9.999e14, -9999.0],
        "physical_bounds": (0.0, 25000.0),
        "flag_tokens": ("qc", "flag"),
        "description": "Mask MERRA-2 1e15 fill sentinel values and enforce non-negative atmospheric mass/AOD bounds.",
    },
    "MODIS_LST_VI": {
        "fill_values": [0, 65535, -3000, -32768, -9999.0],
        "physical_bounds": (-80.0, 360.0),  # Supports Celsius (-80..80), Kelvin (200..360), and scaled NDVI (-0.2..1.0)
        "flag_tokens": ("qc", "reliability", "qual"),
        "description": "Filter MODIS fill sentinels, QC bitmask/pixel-reliability thresholds (<=1), and physical LST/NDVI bounds.",
    },
    "GPM_IMERG": {
        "fill_values": [-9999.9, -9999.0, -999.0],
        "physical_bounds": (0.0, 6000.0),
        "flag_tokens": ("quality", "probability", "qc"),
        "description": "Remove GPM IMERG -9999.9 fill values, negative rainfall artifacts, and extreme invalid precipitation.",
    },
    "SMAP_GLDAS": {
        "fill_values": [-9999.0, -999.0, 9.999e20],
        "physical_bounds": (0.0, 5000.0),
        "flag_tokens": ("retrieval_qual_flag", "qc", "qual", "flag"),
        "description": "Apply SMAP/GLDAS retrieval quality bitmask where bit 0 == 0 indicates recommended retrieval and mask negative moisture.",
    },
    "NASA_POWER": {
        "fill_values": [-999.0, -999, -99.0],
        "physical_bounds": (-90.0, 500.0),
        "flag_tokens": ("qc", "flag"),
        "description": "Remove NASA POWER -999.0 sentinels and enforce physical ranges per variable.",
    },
}


def resolve_qc_profile(dataset_id: str) -> str:
    """Map dataset_id from the official TerraShift catalog to a product-specific QC profile."""
    did = dataset_id.upper()
    if did.startswith("MOP"):
        return "MOPITT_CO"
    if did.startswith("M2TMNX"):
        return "MERRA2_AER_CHM"
    if did.startswith(("MOD11", "MOD13", "MOD17", "MOD08")):
        return "MODIS_LST_VI"
    if did.startswith("GPM"):
        return "GPM_IMERG"
    if did.startswith(("SPL3", "GLDAS")):
        return "SMAP_GLDAS"
    if "POWER" in did:
        return "NASA_POWER"
    return "NASA_POWER"


def _variable_bounds(var_name: str, units: str, profile_name: str) -> tuple[float, float]:
    vn = var_name.upper()
    ul = (units or "").lower()
    if "molec" in ul:
        return (0.0, 1.0e20)
    if vn == "T2M" or ("temp" in vn.lower() and ("c" in ul or "deg" in ul)):
        return (-90.0, 65.0)
    if "kelvin" in ul or ul == "k":
        return (170.0, 360.0)
    if "ndvi" in vn.lower() or "evi" in vn.lower():
        return (-0.25, 1.0)
    if vn in ("GWETROOT", "GWETPROF") or "m3/m3" in ul or "m^3/m^3" in ul:
        return (0.0, 1.0)
    if "prectot" in vn.lower() or "precip" in vn.lower():
        return (0.0, 6000.0)
    if "aod" in vn.lower() or "optical" in vn.lower():
        return (0.0, 10.0)
    if "co" == vn or "co_" in vn.lower() or "column" in vn.lower():
        return (0.0, 5000.0)
    return tuple(QC_PROFILE_SPECS[profile_name]["physical_bounds"])


def apply_quality_control(
    raw_file: Path,
    *,
    dataset_id: str,
    domain: str,
    qc_profile: str | None = None,
    variable_name: str | None = None,
    validated_dir_override: Path | None = None,
) -> QualityControlReport:
    """Apply product-specific QC to a validated raw NetCDF file and save cleaned copy to data/validated/."""
    profile_name = qc_profile or resolve_qc_profile(dataset_id)
    spec = QC_PROFILE_SPECS.get(profile_name, QC_PROFILE_SPECS["NASA_POWER"])

    ds = xr.open_dataset(raw_file, mask_and_scale=True)
    try:
        candidate_vars = [
            str(v)
            for v in ds.data_vars
            if not any(tok in str(v).lower() for tok in ("qc", "qual", "flag", "error", "crs", "spatial_ref"))
        ]
        target_var = variable_name if (variable_name and variable_name in ds.data_vars) else (candidate_vars[0] if candidate_vars else None)
        if not target_var:
            raise ValueError(f"No scientific data variable found in {raw_file} for QC.")

        da = ds[target_var].copy(deep=True)
        arr = da.to_numpy().astype(float, copy=True)
        total_obs = int(arr.size)

        applied_filters: list[str] = []
        notes: list[str] = []

        # 1. Explicit fill value removal
        fill_mask = ~np.isfinite(arr)
        raw_fv = da.encoding.get("_FillValue", da.attrs.get("_FillValue", da.attrs.get("missing_value")))
        fill_candidates = list(spec["fill_values"])
        if raw_fv is not None and isinstance(raw_fv, (int, float, np.number)):
            fill_candidates.append(float(raw_fv))
        for fv in fill_candidates:
            fill_mask = fill_mask | np.isclose(arr, float(fv), rtol=1e-5, atol=1e-8)

        filtered_fill_count = int(np.sum(fill_mask))
        arr[fill_mask] = np.nan
        applied_filters.append(f"fill_mask({len(fill_candidates)} sentinels)")

        # 2. Companion QC flag array filtering when shapes match
        filtered_qc_flag_count = 0
        flag_var = next(
            (str(v) for v in ds.data_vars if str(v) != target_var and any(tok in str(v).lower() for tok in spec["flag_tokens"])),
            None,
        )
        if flag_var is not None and ds[flag_var].shape == da.shape:
            flag_arr = ds[flag_var].to_numpy()
            if profile_name == "MODIS_LST_VI":
                bad_qc = np.isfinite(arr) & (flag_arr > 1)
                applied_filters.append(f"modis_qc_flag({flag_var} <= 1)")
            elif profile_name == "SMAP_GLDAS":
                bad_qc = np.isfinite(arr) & ((flag_arr.astype(int) & 1) != 0)
                applied_filters.append(f"smap_bitmask({flag_var} & 1 == 0)")
            else:
                bad_qc = np.isfinite(arr) & (flag_arr > 0)
                applied_filters.append(f"companion_qc_flag({flag_var} == 0)")
            filtered_qc_flag_count = int(np.sum(bad_qc))
            arr[bad_qc] = np.nan

        # 3. Physical range validation
        units = str(da.attrs.get("units", "unspecified")).strip() or "unspecified"
        lo, hi = _variable_bounds(target_var, units, profile_name)
        range_mask = np.isfinite(arr) & ((arr < lo) | (arr > hi))
        filtered_out_of_range_count = int(np.sum(range_mask))
        arr[range_mask] = np.nan
        applied_filters.append(f"physical_bounds([{lo}, {hi}] for {target_var})")

        valid_after_qc = int(np.sum(np.isfinite(arr)))

        cleaned_ds = ds.copy(deep=True)
        cleaned_ds[target_var] = xr.DataArray(arr, dims=da.dims, coords=da.coords, attrs=dict(da.attrs))
        cleaned_ds.attrs["qc_profile"] = profile_name
        cleaned_ds.attrs["qc_applied_filters"] = "; ".join(applied_filters)
        cleaned_ds.attrs["qc_raw_source"] = str(raw_file)
        cleaned_ds.attrs["qc_valid_observations"] = valid_after_qc

        out_name = f"{raw_file.stem}_validated.nc"
        if validated_dir_override is not None:
            validated_dir_override.mkdir(parents=True, exist_ok=True)
            out_path = validated_dir_override / out_name
        else:
            out_path = get_validated_path(domain, out_name)

        cleaned_ds.to_netcdf(out_path)
        cleaned_ds.close()

        if valid_after_qc == 0:
            notes.append("All observations were masked after QC; verify units or variable bounds.")

        return QualityControlReport(
            dataset_id=dataset_id,
            qc_profile=profile_name,
            raw_file_path=str(raw_file),
            validated_file_path=str(out_path),
            total_observations=total_obs,
            valid_after_qc=valid_after_qc,
            filtered_fill_count=filtered_fill_count,
            filtered_out_of_range_count=filtered_out_of_range_count,
            filtered_qc_flag_count=filtered_qc_flag_count,
            applied_filters=applied_filters,
            units_verified=units,
            passed=valid_after_qc > 0,
            notes=notes,
        )
    finally:
        ds.close()
