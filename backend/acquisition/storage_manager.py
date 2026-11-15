"""Storage directory manager for raw, validated, processed, boundary, metadata, and log files."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = Path(os.environ.get("TERRASHIFT_DATA_DIR", str(REPO_ROOT / "data")))
METADATA_DIR = Path(os.environ.get("TERRASHIFT_METADATA_DIR", str(REPO_ROOT / "metadata")))
LOGS_DIR = Path(os.environ.get("TERRASHIFT_LOGS_DIR", str(REPO_ROOT / "logs")))

DOMAINS = ("atmospheric", "climate", "hydrology", "vegetation")
INDIA_MACRO_ZONES = ("india", "north", "south", "east", "west", "central", "northeast")
BOUNDARY_LEVELS = ("india", "states", "districts")
LOG_CATEGORIES = ("downloads", "validation", "errors")


def ensure_storage_layout(create_gitkeep: bool = True) -> dict[str, str]:
    """Create the canonical TerraShift data, metadata, and log directory hierarchy."""
    paths: dict[str, Path] = {
        "data_root": DATA_DIR,
        "metadata_root": METADATA_DIR,
        "logs_root": LOGS_DIR,
    }

    for domain in DOMAINS:
        paths[f"raw_{domain}"] = DATA_DIR / "raw" / domain
        paths[f"validated_{domain}"] = DATA_DIR / "validated" / domain

    for zone in INDIA_MACRO_ZONES:
        paths[f"processed_{zone}"] = DATA_DIR / "processed" / zone

    for level in BOUNDARY_LEVELS:
        paths[f"boundaries_{level}"] = DATA_DIR / "boundaries" / level

    for log_cat in LOG_CATEGORIES:
        paths[f"logs_{log_cat}"] = LOGS_DIR / log_cat

    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
        if create_gitkeep and p not in (DATA_DIR, METADATA_DIR, LOGS_DIR):
            gitkeep = p / ".gitkeep"
            if not gitkeep.exists():
                gitkeep.touch()

    return {k: str(v) for k, v in paths.items()}


def get_raw_path(domain: str, variable_code: str, source_tag: str, filename: str) -> Path:
    """Return an immutable destination path under data/raw/<domain>/<variable>/<source>/."""
    ensure_storage_layout(create_gitkeep=False)
    safe_domain = domain if domain in DOMAINS else "atmospheric"
    target_dir = DATA_DIR / "raw" / safe_domain / variable_code.upper() / source_tag
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / filename


def get_validated_path(domain: str, filename: str) -> Path:
    """Return destination path under data/validated/<domain>/."""
    ensure_storage_layout(create_gitkeep=False)
    safe_domain = domain if domain in DOMAINS else "atmospheric"
    target_dir = DATA_DIR / "validated" / safe_domain
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / filename


def get_processed_path(region_zone: str, filename: str) -> Path:
    """Return destination path under data/processed/<region_zone>/."""
    ensure_storage_layout(create_gitkeep=False)
    zone = region_zone.lower()
    if zone not in INDIA_MACRO_ZONES:
        zone = "india"
    target_dir = DATA_DIR / "processed" / zone
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / filename


def get_storage_summary() -> dict[str, Any]:
    """Inspect storage backend configuration and local disk file counts."""
    ensure_storage_layout(create_gitkeep=False)
    cloud_bucket = os.environ.get("TERRASHIFT_OBJECT_STORAGE_BUCKET", "").strip() or None
    return {
        "backend": "s3_compatible" if cloud_bucket else "local_filesystem",
        "cloud_bucket": cloud_bucket,
        "data_dir": str(DATA_DIR),
        "metadata_dir": str(METADATA_DIR),
        "logs_dir": str(LOGS_DIR),
        "raw_files_count": sum(1 for p in (DATA_DIR / "raw").rglob("*") if p.is_file() and p.name != ".gitkeep"),
        "validated_files_count": sum(1 for p in (DATA_DIR / "validated").rglob("*") if p.is_file() and p.name != ".gitkeep"),
        "processed_files_count": sum(1 for p in (DATA_DIR / "processed").rglob("*") if p.is_file() and p.name != ".gitkeep"),
    }
