"""NetCDF deep file inspector built on xarray without modifying raw files."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr


def inspect_netcdf(file_path: Path) -> dict[str, Any]:
    """Open a NetCDF file read-only with xarray and return structural, metadata, and timestamp checks."""
    errors: list[str] = []
    warnings: list[str] = []

    if not file_path.exists() or file_path.stat().st_size == 0:
        return {
            "file_path": str(file_path),
            "file_format": "NETCDF",
            "file_size_bytes": file_path.stat().st_size if file_path.exists() else 0,
            "passed": False,
            "errors": ["File does not exist or is empty (0 bytes)."],
            "warnings": [],
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }

    ds = None
    try:
        ds = xr.open_dataset(file_path, mask_and_scale=True)
    except Exception as exc:
        return {
            "file_path": str(file_path),
            "file_format": "NETCDF",
            "file_size_bytes": file_path.stat().st_size,
            "passed": False,
            "errors": [f"Corrupt or unreadable NetCDF file: {type(exc).__name__}: {exc}"],
            "warnings": [],
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }

    try:
        dims = {str(k): int(v) for k, v in ds.sizes.items()}
        coords: dict[str, Any] = {}
        for cname, cvar in ds.coords.items():
            arr = cvar.to_numpy()
            if arr.size == 0:
                continue
            coords[str(cname)] = {
                "size": int(arr.size),
                "min": str(arr[0]) if not np.issubdtype(arr.dtype, np.number) else float(np.nanmin(arr)),
                "max": str(arr[-1]) if not np.issubdtype(arr.dtype, np.number) else float(np.nanmax(arr)),
            }

        variables = [str(v) for v in ds.data_vars]
        if not variables:
            errors.append("NetCDF file contains zero data variables.")

        units: dict[str, str] = {}
        fill_values: dict[str, Any] = {}
        total_cells = 0
        missing_cells = 0

        for vname in variables:
            da = ds[vname]
            unit_str = str(da.attrs.get("units", "")).strip()
            if not unit_str:
                warnings.append(f"Variable '{vname}' is missing a 'units' attribute.")
            units[vname] = unit_str or "missing"

            fv = da.encoding.get("_FillValue", da.attrs.get("_FillValue", da.attrs.get("missing_value")))
            if fv is not None:
                try:
                    if np.isscalar(fv) and isinstance(fv, (float, np.floating)) and not np.isfinite(float(fv)):
                        fill_values[vname] = "NaN"
                    else:
                        fill_values[vname] = float(fv) if np.isscalar(fv) else str(fv)
                except Exception:
                    fill_values[vname] = str(fv)

            vals = da.to_numpy()
            if vals.size > 0 and np.issubdtype(vals.dtype, np.number):
                total_cells += int(vals.size)
                missing_cells += int(np.sum(~np.isfinite(vals)))

        missing_pct = round(100.0 * missing_cells / total_cells, 2) if total_cells > 0 else 0.0

        # Temporal coverage, duplicates & gaps
        time_cov: dict[str, Any] = {}
        dup_count = 0
        missing_ts_count = 0
        time_coord = next((c for c in ("time", "Time", "t") if c in ds.coords), None)
        if time_coord is not None and ds[time_coord].size > 0:
            raw_t = ds[time_coord].to_numpy()
            if np.issubdtype(raw_t.dtype, np.number) and np.all((raw_t >= 190001) & (raw_t <= 210013)):
                t_ints = [int(x) for x in raw_t]
                monthly_ints = [str(x) for x in t_ints if (x % 100) <= 12]
                has_annual_13 = any((x % 100) == 13 for x in t_ints)
                valid_ts = pd.to_datetime(monthly_ints, format="%Y%m", errors="coerce").dropna()
                if has_annual_13:
                    warnings.append("Dataset includes NASA POWER month-13 annual summary slice (YYYY13) alongside monthly slices.")
            else:
                valid_ts = pd.to_datetime(raw_t, errors="coerce").dropna()
            if len(valid_ts) == 0:
                errors.append(f"Time coordinate '{time_coord}' contains no parseable timestamps.")
            else:
                dup_count = int(valid_ts.duplicated().sum())
                if dup_count > 0:
                    errors.append(f"Detected {dup_count} duplicate timestamps in coordinate '{time_coord}'.")
                t_min, t_max = valid_ts.min(), valid_ts.max()
                time_cov = {"start": t_min.strftime("%Y-%m-%d"), "end": t_max.strftime("%Y-%m-%d"), "count": int(len(valid_ts))}
                if len(valid_ts) >= 2:
                    expected_months = pd.date_range(t_min.to_period("M").to_timestamp(), t_max.to_period("M").to_timestamp(), freq="MS")
                    actual_months = pd.DatetimeIndex(valid_ts.to_period("M").to_timestamp().unique())
                    missing_ts_count = int(max(0, len(expected_months) - len(actual_months)))
                    if missing_ts_count > 0:
                        warnings.append(f"Detected {missing_ts_count} missing monthly timestamps between {time_cov['start']} and {time_cov['end']}.")

        # Spatial coverage
        spatial_cov: dict[str, Any] = {}
        lat_c = next((c for c in ("lat", "latitude", "Lat") if c in ds.coords), None)
        lon_c = next((c for c in ("lon", "longitude", "Lon") if c in ds.coords), None)
        if lat_c and lon_c:
            lat_arr = ds[lat_c].to_numpy().astype(float)
            lon_arr = ds[lon_c].to_numpy().astype(float)
            spatial_cov = {
                "lat_min": float(np.nanmin(lat_arr)),
                "lat_max": float(np.nanmax(lat_arr)),
                "lon_min": float(np.nanmin(lon_arr)),
                "lon_max": float(np.nanmax(lon_arr)),
                "lat_count": int(len(lat_arr)),
                "lon_count": int(len(lon_arr)),
            }
        else:
            warnings.append("Standard lat/lon coordinates were not explicitly identified.")

        quality_flags = [
            v for v in variables if any(tok in v.lower() for tok in ("qc", "qual", "flag", "error", "anomaly", "reliability"))
        ]

        return {
            "file_path": str(file_path),
            "file_format": "NETCDF",
            "file_size_bytes": int(file_path.stat().st_size),
            "passed": len(errors) == 0,
            "dimensions": dims,
            "coordinates": coords,
            "variables": variables,
            "units": units,
            "fill_values": fill_values,
            "time_coverage": time_cov,
            "spatial_coverage": spatial_cov,
            "duplicate_timestamps_count": dup_count,
            "missing_timestamps_count": missing_ts_count,
            "missing_value_pct": missing_pct,
            "quality_flags_detected": quality_flags,
            "errors": errors,
            "warnings": warnings,
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        if ds is not None:
            ds.close()
