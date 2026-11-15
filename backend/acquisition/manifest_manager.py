"""CSV manifest and log writers for downloads, validations, and errors."""

from __future__ import annotations

import csv
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .storage_manager import LOGS_DIR, METADATA_DIR, ensure_storage_layout


MANIFEST_COLUMNS = [
    "manifest_id",
    "timestamp",
    "dataset_id",
    "granule_id",
    "collection_concept_id",
    "variable_code",
    "region_id",
    "start_date",
    "end_date",
    "file_path",
    "file_format",
    "file_size_bytes",
    "sha256",
    "retrieval_status",
    "validation_status",
    "notes",
]

VALIDATION_COLUMNS = [
    "timestamp",
    "file_path",
    "file_format",
    "file_size_bytes",
    "passed",
    "dimensions",
    "variables",
    "units",
    "duplicate_timestamps_count",
    "missing_timestamps_count",
    "missing_value_pct",
    "errors",
    "warnings",
]


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hex digest for any local file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _ensure_csv_header(csv_path: Path, columns: list[str]) -> None:
    ensure_storage_layout(create_gitkeep=False)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns)
            writer.writeheader()


def append_manifest_entry(entry: dict[str, Any], manifest_path: Path | None = None) -> dict[str, Any]:
    """Record a downloaded/registered dataset file into metadata/download_manifest.csv."""
    target = manifest_path or (METADATA_DIR / "download_manifest.csv")
    _ensure_csv_header(target, MANIFEST_COLUMNS)
    row = {
        "manifest_id": entry.get("manifest_id") or str(uuid.uuid4())[:12],
        "timestamp": entry.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        "dataset_id": entry.get("dataset_id", ""),
        "granule_id": entry.get("granule_id", ""),
        "collection_concept_id": entry.get("collection_concept_id", ""),
        "variable_code": entry.get("variable_code", ""),
        "region_id": entry.get("region_id", "india"),
        "start_date": entry.get("start_date", ""),
        "end_date": entry.get("end_date", ""),
        "file_path": str(entry.get("file_path", "")),
        "file_format": entry.get("file_format", ""),
        "file_size_bytes": int(entry.get("file_size_bytes", 0)),
        "sha256": entry.get("sha256", ""),
        "retrieval_status": entry.get("retrieval_status", "downloaded"),
        "validation_status": entry.get("validation_status", "pending"),
        "notes": entry.get("notes", ""),
    }
    with open(target, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_COLUMNS)
        writer.writerow(row)
    return row


def find_existing_manifest_entry(
    *,
    dataset_id: str,
    granule_id: str,
    manifest_path: Path | None = None,
) -> dict[str, Any] | None:
    """Return existing manifest row if granule is already downloaded and present on disk."""
    target = manifest_path or (METADATA_DIR / "download_manifest.csv")
    if not target.exists():
        return None
    with open(target, "r", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("dataset_id") == dataset_id and row.get("granule_id") == granule_id:
                fp = Path(row.get("file_path", ""))
                if fp.exists() and fp.stat().st_size > 0:
                    return row
    return None


def update_manifest_validation_status(
    file_path: str,
    validation_status: str,
    manifest_path: Path | None = None,
) -> None:
    """Update validation_status in download_manifest.csv for a matching file_path."""
    target = manifest_path or (METADATA_DIR / "download_manifest.csv")
    if not target.exists():
        return
    with open(target, "r", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    changed = False
    norm_target = str(Path(file_path))
    for r in rows:
        if str(Path(r.get("file_path", ""))) == norm_target:
            r["validation_status"] = validation_status
            changed = True
    if changed:
        with open(target, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=MANIFEST_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)


def read_manifest_entries(manifest_path: Path | None = None) -> list[dict[str, Any]]:
    """Read all rows from metadata/download_manifest.csv."""
    target = manifest_path or (METADATA_DIR / "download_manifest.csv")
    _ensure_csv_header(target, MANIFEST_COLUMNS)
    with open(target, "r", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def append_validation_report(report: dict[str, Any], report_path: Path | None = None) -> dict[str, Any]:
    """Append a structured validation outcome to metadata/validation_report.csv and logs/validation/."""
    target = report_path or (METADATA_DIR / "validation_report.csv")
    _ensure_csv_header(target, VALIDATION_COLUMNS)
    row = {
        "timestamp": report.get("validated_at") or datetime.now(timezone.utc).isoformat(),
        "file_path": str(report.get("file_path", "")),
        "file_format": report.get("file_format", ""),
        "file_size_bytes": int(report.get("file_size_bytes", 0)),
        "passed": str(bool(report.get("passed", False))),
        "dimensions": json.dumps(report.get("dimensions", {})),
        "variables": ";".join(report.get("variables", [])),
        "units": json.dumps(report.get("units", {})),
        "duplicate_timestamps_count": int(report.get("duplicate_timestamps_count", 0)),
        "missing_timestamps_count": int(report.get("missing_timestamps_count", 0)),
        "missing_value_pct": float(report.get("missing_value_pct", 0.0)),
        "errors": " | ".join(report.get("errors", [])),
        "warnings": " | ".join(report.get("warnings", [])),
    }
    with open(target, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=VALIDATION_COLUMNS)
        writer.writerow(row)
    return row


def read_validation_reports(report_path: Path | None = None) -> list[dict[str, Any]]:
    """Read all rows from metadata/validation_report.csv."""
    target = report_path or (METADATA_DIR / "validation_report.csv")
    _ensure_csv_header(target, VALIDATION_COLUMNS)
    with open(target, "r", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_acquisition_log(category: str, event: str, details: dict[str, Any]) -> None:
    """Append JSON-lines log entries to logs/<category>/activity.log (never includes secrets)."""
    ensure_storage_layout(create_gitkeep=False)
    safe_cat = category if category in ("downloads", "validation", "errors") else "downloads"
    log_file = LOGS_DIR / safe_cat / "activity.log"
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **details,
    }
    with open(log_file, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, default=str) + "\n")
