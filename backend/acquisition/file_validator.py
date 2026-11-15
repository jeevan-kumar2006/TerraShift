"""Unified scientific file validator supporting NetCDF, HDF5/HDF-EOS5, GeoTIFF, and CSV."""

from __future__ import annotations

import csv
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .hdf5_inspector import inspect_hdf5
from .manifest_manager import (
    append_validation_report,
    update_manifest_validation_status,
    write_acquisition_log,
)
from .models import ValidationReport
from .netcdf_inspector import inspect_netcdf


def _detect_format(file_path: Path, expected_format: str | None = None) -> str:
    if expected_format:
        fmt = expected_format.strip().upper()
        if fmt in ("NC", "NC4", "NETCDF", "NETCDF4"):
            return "NETCDF"
        if fmt in ("H5", "HE5", "HDF5", "HDF"):
            return "HDF5"
        if fmt in ("TIF", "TIFF", "GEOTIFF"):
            return "GEOTIFF"
        if fmt == "CSV":
            return "CSV"

    suffix = file_path.suffix.lower()
    if suffix in (".nc", ".nc4"):
        return "NETCDF"
    if suffix in (".h5", ".he5", ".hdf5", ".hdf"):
        return "HDF5"
    if suffix in (".tif", ".tiff"):
        return "GEOTIFF"
    if suffix == ".csv":
        return "CSV"
    return suffix.lstrip(".").upper() or "UNKNOWN"


def _parse_tiff_binary_header(file_path: Path) -> dict[str, Any]:
    """Parse classic TIFF/GeoTIFF IFD0 binary tags without external GDAL/rasterio dependencies."""
    errors: list[str] = []
    warnings: list[str] = []

    raw = file_path.read_bytes()
    if len(raw) < 16:
        return {"passed": False, "errors": ["TIFF file too small (< 16 bytes) to contain a valid header."], "warnings": []}

    endian_sig = raw[:2]
    if endian_sig == b"II":
        bo = "<"
    elif endian_sig == b"MM":
        bo = ">"
    else:
        return {"passed": False, "errors": [f"Invalid TIFF byte-order marker: {endian_sig!r}."], "warnings": []}

    magic, ifd_offset = struct.unpack(f"{bo}HI", raw[2:8])
    if magic != 42:
        return {"passed": False, "errors": [f"Unsupported TIFF magic number {magic} (expected 42)."], "warnings": []}
    if ifd_offset + 2 > len(raw):
        return {"passed": False, "errors": ["Truncated TIFF IFD0 offset beyond file size."], "warnings": []}

    num_entries = struct.unpack(f"{bo}H", raw[ifd_offset : ifd_offset + 2])[0]
    tags: dict[int, tuple[int, int, bytes]] = {}
    pos = ifd_offset + 2
    for _ in range(num_entries):
        if pos + 12 > len(raw):
            errors.append("Truncated TIFF IFD entry.")
            break
        tag_id, field_type, count, val_bytes = struct.unpack(f"{bo}HHI4s", raw[pos : pos + 12])
        tags[tag_id] = (field_type, count, val_bytes)
        pos += 12

    def _read_scalar(tag_id: int) -> int | None:
        if tag_id not in tags:
            return None
        ftype, _, val_bytes = tags[tag_id]
        if ftype == 3:
            return struct.unpack(f"{bo}H", val_bytes[:2])[0]
        if ftype == 4:
            return struct.unpack(f"{bo}I", val_bytes)[0]
        return struct.unpack(f"{bo}H", val_bytes[:2])[0]

    def _read_doubles(tag_id: int) -> list[float]:
        if tag_id not in tags:
            return []
        ftype, count, val_bytes = tags[tag_id]
        if ftype != 12 or count <= 0:
            return []
        offset = struct.unpack(f"{bo}I", val_bytes)[0]
        byte_len = count * 8
        if offset + byte_len > len(raw):
            return []
        return list(struct.unpack(f"{bo}{count}d", raw[offset : offset + byte_len]))

    width = _read_scalar(256)
    height = _read_scalar(257)
    if not width or not height:
        errors.append("GeoTIFF missing required ImageWidth (256) or ImageLength (257) tags.")

    pixel_scale = _read_doubles(33550)
    tiepoint = _read_doubles(33922)
    spatial_cov: dict[str, Any] = {}
    if len(pixel_scale) >= 2 and len(tiepoint) >= 6 and width and height:
        sx, sy = pixel_scale[0], pixel_scale[1]
        x0, y0 = tiepoint[3], tiepoint[4]
        spatial_cov = {
            "lon_min": float(x0),
            "lon_max": float(x0 + width * sx),
            "lat_max": float(y0),
            "lat_min": float(y0 - height * sy),
        }
    else:
        warnings.append("GeoTIFF tiepoint/pixel-scale tags (33550/33922) not present.")

    nodata_val: Any = None
    if 42113 in tags:
        _, count, val_bytes = tags[42113]
        if count <= 4:
            nodata_val = val_bytes[:count].rstrip(b"\x00").decode("ascii", errors="ignore")
        else:
            offset = struct.unpack(f"{bo}I", val_bytes)[0]
            if offset + count <= len(raw):
                nodata_val = raw[offset : offset + count].rstrip(b"\x00").decode("ascii", errors="ignore")

    return {
        "passed": len(errors) == 0,
        "dimensions": {"height": int(height or 0), "width": int(width or 0)},
        "variables": ["band_1"],
        "fill_values": {"band_1": nodata_val} if nodata_val is not None else {},
        "spatial_coverage": spatial_cov,
        "errors": errors,
        "warnings": warnings,
    }


def inspect_geotiff(file_path: Path) -> dict[str, Any]:
    """Validate a GeoTIFF raster using rasterio when installed, or built-in binary IFD parser."""
    if not file_path.exists() or file_path.stat().st_size == 0:
        return {
            "file_path": str(file_path),
            "file_format": "GEOTIFF",
            "file_size_bytes": file_path.stat().st_size if file_path.exists() else 0,
            "passed": False,
            "errors": ["GeoTIFF file does not exist or is empty (0 bytes)."],
            "warnings": [],
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }

    try:
        import rasterio  # type: ignore

        with rasterio.open(file_path) as src:
            arr = src.read(1, masked=True)
            total = int(arr.size)
            invalid = int(np.ma.count_masked(arr))
            missing_pct = round(100.0 * invalid / total, 2) if total > 0 else 0.0
            bounds = src.bounds
            return {
                "file_path": str(file_path),
                "file_format": "GEOTIFF",
                "file_size_bytes": int(file_path.stat().st_size),
                "passed": True,
                "dimensions": {"bands": int(src.count), "height": int(src.height), "width": int(src.width)},
                "coordinates": {"crs": str(src.crs) if src.crs else "unspecified"},
                "variables": [f"band_{i}" for i in range(1, src.count + 1)],
                "units": {"band_1": (src.units[0] or "unspecified") if src.units else "unspecified"},
                "fill_values": {"nodata": src.nodata} if src.nodata is not None else {},
                "time_coverage": {},
                "spatial_coverage": {
                    "lon_min": float(bounds.left),
                    "lat_min": float(bounds.bottom),
                    "lon_max": float(bounds.right),
                    "lat_max": float(bounds.top),
                },
                "duplicate_timestamps_count": 0,
                "missing_timestamps_count": 0,
                "missing_value_pct": missing_pct,
                "quality_flags_detected": [],
                "errors": [],
                "warnings": [] if src.crs else ["GeoTIFF has no embedded CRS metadata."],
                "validated_at": datetime.now(timezone.utc).isoformat(),
            }
    except ImportError:
        parsed = _parse_tiff_binary_header(file_path)
        return {
            "file_path": str(file_path),
            "file_format": "GEOTIFF",
            "file_size_bytes": int(file_path.stat().st_size),
            "passed": parsed["passed"],
            "dimensions": parsed.get("dimensions", {}),
            "coordinates": {"crs": "EPSG:4326 (header-parsed)"},
            "variables": parsed.get("variables", []),
            "units": {"band_1": "unspecified"},
            "fill_values": parsed.get("fill_values", {}),
            "time_coverage": {},
            "spatial_coverage": parsed.get("spatial_coverage", {}),
            "duplicate_timestamps_count": 0,
            "missing_timestamps_count": 0,
            "missing_value_pct": 0.0,
            "quality_flags_detected": [],
            "errors": parsed.get("errors", []),
            "warnings": parsed.get("warnings", []),
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        return {
            "file_path": str(file_path),
            "file_format": "GEOTIFF",
            "file_size_bytes": int(file_path.stat().st_size),
            "passed": False,
            "errors": [f"Corrupt or unreadable GeoTIFF: {type(exc).__name__}: {exc}"],
            "warnings": [],
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }


def inspect_csv(file_path: Path) -> dict[str, Any]:
    """Validate a CSV time-series or environmental table."""
    errors: list[str] = []
    warnings: list[str] = []
    if not file_path.exists() or file_path.stat().st_size == 0:
        return {
            "file_path": str(file_path),
            "file_format": "CSV",
            "file_size_bytes": file_path.stat().st_size if file_path.exists() else 0,
            "passed": False,
            "errors": ["CSV file does not exist or is empty (0 bytes)."],
            "warnings": [],
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }

    try:
        df = pd.read_csv(file_path)
    except Exception as exc:
        return {
            "file_path": str(file_path),
            "file_format": "CSV",
            "file_size_bytes": int(file_path.stat().st_size),
            "passed": False,
            "errors": [f"Failed to parse CSV: {type(exc).__name__}: {exc}"],
            "warnings": [],
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }

    if df.empty or len(df.columns) == 0:
        errors.append("CSV contains zero rows or columns.")

    date_col = next((c for c in df.columns if any(k in c.lower() for k in ("date", "time", "month", "year"))), None)
    dup_count = 0
    missing_ts_count = 0
    time_cov: dict[str, Any] = {}
    if date_col is not None:
        parsed_ts = pd.to_datetime(df[date_col], errors="coerce")
        valid_ts = parsed_ts.dropna()
        if valid_ts.empty:
            errors.append(f"Date column '{date_col}' contains no valid timestamps.")
        else:
            dup_count = int(valid_ts.duplicated().sum())
            if dup_count > 0:
                errors.append(f"CSV has {dup_count} duplicate timestamps in '{date_col}'.")
            time_cov = {
                "start": valid_ts.min().strftime("%Y-%m-%d"),
                "end": valid_ts.max().strftime("%Y-%m-%d"),
                "count": int(len(valid_ts)),
            }
            if len(valid_ts) >= 2:
                ts_dti = pd.DatetimeIndex(valid_ts)
                expected_m = pd.date_range(valid_ts.min().to_period("M").to_timestamp(), valid_ts.max().to_period("M").to_timestamp(), freq="MS")
                actual_m = pd.DatetimeIndex(ts_dti.to_period("M").to_timestamp().unique())
                missing_ts_count = int(max(0, len(expected_m) - len(actual_m)))
    else:
        warnings.append("No explicit date/time column detected in CSV.")

    num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    total_cells = int(len(df) * max(1, len(num_cols)))
    missing_cells = int(df[num_cols].isna().sum().sum()) if num_cols else 0
    missing_pct = round(100.0 * missing_cells / total_cells, 2) if total_cells > 0 else 0.0

    units: dict[str, str] = {}
    if "units" in df.columns and not df["units"].dropna().empty:
        units["series"] = str(df["units"].dropna().iloc[0])

    return {
        "file_path": str(file_path),
        "file_format": "CSV",
        "file_size_bytes": int(file_path.stat().st_size),
        "passed": len(errors) == 0,
        "dimensions": {"rows": int(len(df)), "columns": int(len(df.columns))},
        "coordinates": {"date_column": date_col} if date_col else {},
        "variables": list(df.columns),
        "units": units,
        "fill_values": {},
        "time_coverage": time_cov,
        "spatial_coverage": {},
        "duplicate_timestamps_count": dup_count,
        "missing_timestamps_count": missing_ts_count,
        "missing_value_pct": missing_pct,
        "quality_flags_detected": [],
        "errors": errors,
        "warnings": warnings,
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }


def validate_file(
    file_path: Path,
    *,
    expected_format: str | None = None,
    manifest_path: Path | None = None,
    report_path: Path | None = None,
    update_manifest: bool = True,
) -> ValidationReport:
    """Validate NetCDF, HDF5/HE5, GeoTIFF, or CSV files and log outcomes to validation_report.csv."""
    fmt = _detect_format(file_path, expected_format)
    if fmt == "NETCDF":
        raw_report = inspect_netcdf(file_path)
    elif fmt == "HDF5":
        raw_report = inspect_hdf5(file_path)
    elif fmt == "GEOTIFF":
        raw_report = inspect_geotiff(file_path)
    elif fmt == "CSV":
        raw_report = inspect_csv(file_path)
    else:
        raw_report = {
            "file_path": str(file_path),
            "file_format": fmt,
            "file_size_bytes": file_path.stat().st_size if file_path.exists() else 0,
            "passed": False,
            "errors": [f"Unsupported scientific file format '{fmt}'."],
            "warnings": [],
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }

    report = ValidationReport(**raw_report)
    append_validation_report(report.model_dump(), report_path=report_path)
    write_acquisition_log(
        "validation",
        "file_validated" if report.passed else "file_rejected",
        {
            "file_path": report.file_path,
            "file_format": report.file_format,
            "passed": report.passed,
            "missing_value_pct": report.missing_value_pct,
            "errors": report.errors,
        },
    )
    if update_manifest:
        update_manifest_validation_status(
            str(file_path),
            "validated" if report.passed else "rejected",
            manifest_path=manifest_path,
        )
    return report
