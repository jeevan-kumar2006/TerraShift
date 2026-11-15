"""HDF5 and HDF-EOS5 (.h5 / .he5 / .hdf5) read-only structural and geolocation inspector."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import h5py
import numpy as np


def inspect_hdf5(file_path: Path) -> dict[str, Any]:
    """Inspect an HDF5 / HDF-EOS5 file without modifying it and return ValidationReport-compatible dict."""
    errors: list[str] = []
    warnings: list[str] = []

    if not file_path.exists() or file_path.stat().st_size == 0:
        return {
            "file_path": str(file_path),
            "file_format": "HDF5",
            "file_size_bytes": file_path.stat().st_size if file_path.exists() else 0,
            "passed": False,
            "errors": ["File does not exist or is empty (0 bytes)."],
            "warnings": [],
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }

    try:
        fh = h5py.File(file_path, "r")
    except Exception as exc:
        return {
            "file_path": str(file_path),
            "file_format": "HDF5",
            "file_size_bytes": int(file_path.stat().st_size),
            "passed": False,
            "errors": [f"Corrupt or unreadable HDF5 file: {type(exc).__name__}: {exc}"],
            "warnings": [],
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }

    with fh:
        variables: list[str] = []
        dims: dict[str, int] = {}
        coords: dict[str, Any] = {}
        units: dict[str, str] = {}
        fill_values: dict[str, Any] = {}
        quality_flags: list[str] = []
        lat_bounds: dict[str, float] | None = None
        lon_bounds: dict[str, float] | None = None
        total_cells = 0
        missing_cells = 0

        def _attr_val(obj: h5py.Dataset, keys: tuple[str, ...]) -> Any:
            for k in keys:
                if k in obj.attrs:
                    v = obj.attrs[k]
                    if isinstance(v, (bytes, bytearray)):
                        return v.decode("utf-8", errors="ignore")
                    if isinstance(v, np.ndarray) and v.size == 1:
                        item = v.reshape(-1)[0]
                        return item.decode("utf-8", errors="ignore") if isinstance(item, (bytes, bytearray)) else item
                    return v
            return None

        def _visit(name: str, obj: Any) -> None:
            nonlocal total_cells, missing_cells, lat_bounds, lon_bounds
            if not isinstance(obj, h5py.Dataset):
                return

            variables.append(name)
            shape_tuple = tuple(int(s) for s in obj.shape)
            dims[name] = int(np.prod(shape_tuple)) if shape_tuple else 1

            unit_attr = _attr_val(obj, ("units", "Units", "UNIT"))
            units[name] = str(unit_attr).strip() if unit_attr is not None else "unspecified"

            fv = _attr_val(obj, ("_FillValue", "missing_value", "MissingValue"))
            if fv is not None:
                try:
                    fill_values[name] = float(fv) if np.isscalar(fv) else str(fv)
                except Exception:
                    fill_values[name] = str(fv)

            leaf = name.split("/")[-1].lower()
            if any(tok in leaf for tok in ("qc", "qa", "qual", "flag", "error", "anomaly", "reliability")):
                quality_flags.append(name)

            # Inspect numeric contents for geolocation bounds and missing fraction (guard size <= 5M cells)
            if obj.dtype.kind in ("f", "i", "u") and int(np.prod(shape_tuple or (1,))) <= 5_000_000:
                arr = obj[...].astype(float, copy=False)
                invalid = ~np.isfinite(arr)
                if fv is not None and isinstance(fv, (int, float, np.number)):
                    invalid = invalid | np.isclose(arr, float(fv), equal_nan=False)
                valid_vals = arr[~invalid]

                if leaf in ("lat", "latitude", "ydim") or leaf.endswith("latitude"):
                    if valid_vals.size > 0:
                        lat_bounds = {"min": float(np.min(valid_vals)), "max": float(np.max(valid_vals)), "size": int(valid_vals.size)}
                        coords["latitude"] = lat_bounds
                elif leaf in ("lon", "longitude", "xdim") or leaf.endswith("longitude"):
                    if valid_vals.size > 0:
                        lon_bounds = {"min": float(np.min(valid_vals)), "max": float(np.max(valid_vals)), "size": int(valid_vals.size)}
                        coords["longitude"] = lon_bounds
                else:
                    total_cells += int(arr.size)
                    missing_cells += int(np.sum(invalid))

        fh.visititems(_visit)

        if not variables:
            errors.append("HDF5 file contains zero datasets.")

        missing_pct = round(100.0 * missing_cells / total_cells, 2) if total_cells > 0 else 0.0
        spatial_cov: dict[str, Any] = {}
        if lat_bounds and lon_bounds:
            spatial_cov = {
                "lat_min": lat_bounds["min"],
                "lat_max": lat_bounds["max"],
                "lon_min": lon_bounds["min"],
                "lon_max": lon_bounds["max"],
            }
        else:
            warnings.append("Explicit 1D/2D geolocation arrays (lat/lon) were not found inside HDF5 groups.")

        time_cov: dict[str, Any] = {}
        for tkey in ("RangeBeginningDate", "StartDate", "time_coverage_start"):
            if tkey in fh.attrs:
                raw_t = fh.attrs[tkey]
                time_cov["start"] = raw_t.decode("utf-8", errors="ignore") if isinstance(raw_t, (bytes, bytearray)) else str(raw_t)
                break
        for tkey in ("RangeEndingDate", "EndDate", "time_coverage_end"):
            if tkey in fh.attrs:
                raw_t = fh.attrs[tkey]
                time_cov["end"] = raw_t.decode("utf-8", errors="ignore") if isinstance(raw_t, (bytes, bytearray)) else str(raw_t)
                break

        return {
            "file_path": str(file_path),
            "file_format": "HDF5",
            "file_size_bytes": int(file_path.stat().st_size),
            "passed": len(errors) == 0,
            "dimensions": dims,
            "coordinates": coords,
            "variables": variables,
            "units": units,
            "fill_values": fill_values,
            "time_coverage": time_cov,
            "spatial_coverage": spatial_cov,
            "duplicate_timestamps_count": 0,
            "missing_timestamps_count": 0,
            "missing_value_pct": missing_pct,
            "quality_flags_detected": quality_flags,
            "errors": errors,
            "warnings": warnings,
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }
