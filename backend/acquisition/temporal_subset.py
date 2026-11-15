"""Temporal filtering, ISO window validation, and dataset time-range clipping helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def parse_iso_date(date_str: str) -> datetime:
    """Parse YYYY-MM-DD or full ISO-8601 timestamp into naive UTC datetime."""
    cleaned = str(date_str).strip()
    if "T" in cleaned:
        cleaned = cleaned.split("T", 1)[0]
    return datetime.strptime(cleaned[:10], "%Y-%m-%d")


def validate_temporal_window(start_date: str, end_date: str) -> tuple[str, str]:
    """Validate and normalize start/end YYYY-MM-DD bounds."""
    s_dt = parse_iso_date(start_date)
    e_dt = parse_iso_date(end_date)
    if s_dt > e_dt:
        raise ValueError(f"start_date ({start_date}) must not be after end_date ({end_date}).")
    return s_dt.strftime("%Y-%m-%d"), e_dt.strftime("%Y-%m-%d")


def build_cmr_temporal_param(start_date: str, end_date: str) -> str:
    """Format CMR temporal filter parameter 'YYYY-MM-DDT00:00:00Z,YYYY-MM-DDT23:59:59Z'."""
    s_norm, e_norm = validate_temporal_window(start_date, end_date)
    return f"{s_norm}T00:00:00Z,{e_norm}T23:59:59Z"


def subset_xarray_time(ds: Any, start_date: str, end_date: str) -> Any:
    """Slice an xarray Dataset cleanly along its time coordinate when present."""
    s_norm, e_norm = validate_temporal_window(start_date, end_date)
    for coord in ("time", "Time", "t", "date"):
        if coord in ds.coords or coord in ds.dims:
            return ds.sel({coord: slice(s_norm, e_norm)})
    return ds
