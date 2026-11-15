"""Reusable authenticated download manager with retries, Range resume, checksums, concurrency limits, and duplicate protection."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any
import httpx

from .earthdata_auth import get_auth_headers_for_url, get_earthdata_token
from .manifest_manager import (
    append_manifest_entry,
    compute_sha256,
    find_existing_manifest_entry,
    write_acquisition_log,
)
from .storage_manager import get_raw_path


async def download_file_resumable(
    *,
    url: str,
    dest_path: Path,
    expected_size_bytes: int | None = None,
    expected_sha256: str | None = None,
    expected_md5: str | None = None,
    max_retries: int = 3,
    timeout_seconds: float = 60.0,
    chunk_size: int = 65536,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """
    Download a remote file to dest_path using a .part staging file.
    - Never overwrites an existing complete file at dest_path.
    - Resumes from existing .part file via HTTP Range header when supported (206 Partial Content).
    - Retries transient errors / interruptions with exponential backoff.
    - Verifies file size and SHA-256/MD5 checksum when provided.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if dest_path.exists() and dest_path.stat().st_size > 0:
        sha = compute_sha256(dest_path)
        write_acquisition_log(
            "downloads",
            "download_skipped_existing",
            {"file_path": str(dest_path), "size_bytes": dest_path.stat().st_size},
        )
        return {
            "status": "skipped_existing",
            "file_path": str(dest_path),
            "size_bytes": dest_path.stat().st_size,
            "sha256": sha,
            "resumed_bytes": 0,
        }

    part_path = dest_path.with_suffix(dest_path.suffix + ".part")
    last_error: str | None = None

    for attempt in range(1, max_retries + 1):
        existing_part_size = part_path.stat().st_size if part_path.exists() else 0
        headers = get_auth_headers_for_url(url)
        if existing_part_size > 0:
            headers["Range"] = f"bytes={existing_part_size}-"

        try:
            async with httpx.AsyncClient(
                timeout=timeout_seconds,
                follow_redirects=True,
                transport=transport,
            ) as client:
                async with client.stream("GET", url, headers=headers) as resp:
                    if resp.status_code in (401, 403):
                        msg = (
                            f"HTTP {resp.status_code} Unauthorized/Forbidden from {url}. "
                            "NASA Earthdata Login credentials (EARTHDATA_TOKEN or ~/.netrc) are required."
                        )
                        write_acquisition_log("errors", "auth_required", {"url": url, "status": resp.status_code})
                        return {"status": "auth_required", "error": msg, "http_status": resp.status_code}

                    if resp.status_code not in (200, 206):
                        resp.raise_for_status()

                    if resp.status_code == 200 and existing_part_size > 0:
                        # Server ignored Range header; restart staging file cleanly
                        existing_part_size = 0
                        mode = "wb"
                    elif resp.status_code == 206 and existing_part_size > 0:
                        mode = "ab"
                    else:
                        mode = "wb"

                    resumed_bytes = existing_part_size
                    with open(part_path, mode) as fh:
                        async for chunk in resp.aiter_bytes(chunk_size=chunk_size):
                            if chunk:
                                fh.write(chunk)

            final_size = part_path.stat().st_size
            if final_size == 0:
                raise ValueError("Downloaded file is 0 bytes.")
            if expected_size_bytes is not None and final_size != expected_size_bytes:
                raise ValueError(
                    f"Size verification failed: expected {expected_size_bytes} bytes, got {final_size} bytes."
                )

            actual_sha256 = compute_sha256(part_path)
            if expected_sha256 and actual_sha256.lower() != expected_sha256.lower():
                raise ValueError(
                    f"SHA-256 verification failed: expected {expected_sha256}, got {actual_sha256}."
                )

            if expected_md5:
                md5_h = hashlib.md5()
                with open(part_path, "rb") as mfh:
                    for block in iter(lambda: mfh.read(65536), b""):
                        md5_h.update(block)
                if md5_h.hexdigest().lower() != expected_md5.lower():
                    raise ValueError(f"MD5 verification failed for {dest_path.name}")

            part_path.replace(dest_path)
            write_acquisition_log(
                "downloads",
                "download_completed",
                {
                    "file_path": str(dest_path),
                    "size_bytes": final_size,
                    "resumed_bytes": resumed_bytes,
                    "attempts": attempt,
                },
            )
            return {
                "status": "downloaded",
                "file_path": str(dest_path),
                "size_bytes": final_size,
                "sha256": actual_sha256,
                "resumed_bytes": resumed_bytes,
                "attempts": attempt,
            }

        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            write_acquisition_log(
                "errors",
                "download_attempt_failed",
                {"url": url, "attempt": attempt, "error": last_error},
            )
            if attempt < max_retries:
                await asyncio.sleep(0.25 * (2 ** (attempt - 1)))

    return {
        "status": "failed",
        "error": last_error or "Unknown download failure",
        "file_path": str(part_path if part_path.exists() else dest_path),
    }


async def download_granules_parallel(
    *,
    dataset_id: str,
    collection_concept_id: str | None,
    variable_code: str,
    domain: str,
    source_tag: str,
    region_id: str,
    start_date: str,
    end_date: str,
    granules: list[dict[str, Any]],
    max_workers: int = 3,
    manifest_path: Path | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[dict[str, Any]]:
    """Download multiple granules concurrently with duplicate-manifest checking."""
    sem = asyncio.Semaphore(max(1, min(max_workers, 8)))

    async def _worker(granule: dict[str, Any]) -> dict[str, Any]:
        g_id = granule.get("granule_id") or granule.get("title") or "granule"
        url = granule.get("download_url") or granule.get("opendap_url")
        if not url:
            return {"granule_id": g_id, "status": "no_download_url"}

        existing = find_existing_manifest_entry(
            dataset_id=dataset_id,
            granule_id=g_id,
            manifest_path=manifest_path,
        )
        if existing is not None:
            return {
                "granule_id": g_id,
                "status": "skipped_duplicate",
                "file_path": existing["file_path"],
                "sha256": existing["sha256"],
            }

        raw_name = Path(str(granule.get("title") or url.split("/")[-1])).name
        if "." not in raw_name:
            raw_name += ".nc4"
        dest = get_raw_path(domain, variable_code, source_tag, raw_name)

        async with sem:
            res = await download_file_resumable(
                url=url,
                dest_path=dest,
                expected_sha256=granule.get("checksum")
                if (granule.get("checksum_algorithm") or "").upper() == "SHA256"
                else None,
                expected_md5=granule.get("checksum")
                if (granule.get("checksum_algorithm") or "").upper() == "MD5"
                else None,
                transport=transport,
            )

        if res["status"] in ("downloaded", "skipped_existing"):
            ext = dest.suffix.lstrip(".").upper() or "NETCDF"
            append_manifest_entry(
                {
                    "dataset_id": dataset_id,
                    "granule_id": g_id,
                    "collection_concept_id": collection_concept_id or "",
                    "variable_code": variable_code,
                    "region_id": region_id,
                    "start_date": start_date,
                    "end_date": end_date,
                    "file_path": str(dest),
                    "file_format": ext,
                    "file_size_bytes": res["size_bytes"],
                    "sha256": res["sha256"],
                    "retrieval_status": res["status"],
                    "validation_status": "pending",
                    "notes": f"Source URL: {url[:80]}",
                },
                manifest_path=manifest_path,
            )
        return {"granule_id": g_id, **res}

    return await asyncio.gather(*[_worker(g) for g in granules])


async def download_power_regional_netcdf(
    *,
    parameters: list[str],
    latitude_min: float,
    latitude_max: float,
    longitude_min: float,
    longitude_max: float,
    start_year: int,
    end_year: int,
    dest_path: Path,
    community: str = "AG",
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Download an unauthenticated NetCDF regional grid from NASA POWER Regional API."""
    # POWER regional box cannot span >10 degrees per call and accepts at most 1 parameter per NETCDF request
    if (latitude_max - latitude_min) > 10.0 or (longitude_max - longitude_min) > 10.0:
        raise ValueError("NASA POWER Regional API supports at most a 10° × 10° bounding box per request.")
    if not parameters:
        raise ValueError("At least one NASA POWER parameter must be specified.")
    if len(parameters) > 1:
        parameters = [parameters[0]]

    params_str = ",".join(parameters)
    url = (
        f"https://power.larc.nasa.gov/api/temporal/monthly/regional"
        f"?parameters={params_str}&community={community}"
        f"&latitude-min={latitude_min}&latitude-max={latitude_max}"
        f"&longitude-min={longitude_min}&longitude-max={longitude_max}"
        f"&start={start_year}&end={end_year}&format=NETCDF"
    )
    res = await download_file_resumable(url=url, dest_path=dest_path, timeout_seconds=45.0)
    if res["status"] in ("downloaded", "skipped_existing"):
        append_manifest_entry(
            {
                "dataset_id": "NASA_POWER_AG",
                "granule_id": dest_path.stem,
                "collection_concept_id": "POWER_MERRA2_GPM_AG",
                "variable_code": parameters[0],
                "region_id": f"bbox_{latitude_min}_{latitude_max}_{longitude_min}_{longitude_max}",
                "start_date": f"{start_year}-01-01",
                "end_date": f"{end_year}-12-31",
                "file_path": str(dest_path),
                "file_format": "NETCDF",
                "file_size_bytes": res["size_bytes"],
                "sha256": res["sha256"],
                "retrieval_status": res["status"],
                "validation_status": "pending",
                "notes": "Live NASA POWER Regional NetCDF download (unauthenticated)",
            },
            manifest_path=manifest_path,
        )
    return res
