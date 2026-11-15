"""NASA Common Metadata Repository (CMR) official collection & granule search client with pagination."""

from __future__ import annotations

from typing import Any
import httpx

from .temporal_subset import build_cmr_temporal_param


CMR_COLLECTIONS_URL = "https://cmr.earthdata.nasa.gov/search/collections.json"
CMR_GRANULES_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"


async def search_collections(
    *,
    short_name: str | None = None,
    keyword: str | None = None,
    page_size: int = 10,
    page_num: int = 1,
) -> list[dict[str, Any]]:
    """Query NASA CMR collections catalog cleanly."""
    params: dict[str, Any] = {"page_size": page_size, "page_num": page_num}
    if short_name:
        params["short_name"] = short_name
    if keyword:
        params["keyword"] = keyword

    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.get(CMR_COLLECTIONS_URL, params=params)
        resp.raise_for_status()
        entries = resp.json().get("feed", {}).get("entry", [])

    results: list[dict[str, Any]] = []
    for e in entries:
        results.append(
            {
                "collection_concept_id": e.get("id"),
                "short_name": e.get("short_name"),
                "version_id": e.get("version_id"),
                "title": e.get("title"),
                "data_center": e.get("data_center"),
                "time_start": e.get("time_start"),
                "time_end": e.get("time_end"),
                "summary": (e.get("summary") or "")[:350],
                "online_access_flag": e.get("online_access_flag"),
            }
        )
    return results


def _extract_granule_links(entry: dict[str, Any]) -> tuple[str | None, str | None]:
    download_url: str | None = None
    opendap_url: str | None = None
    for link in entry.get("links", []):
        href = str(link.get("href", ""))
        rel = str(link.get("rel", ""))
        title = str(link.get("title", "")).lower()
        if not href.startswith("http"):
            continue
        if ("opendap" in href.lower() or "opendap" in title) and opendap_url is None:
            opendap_url = href
        elif rel.endswith("/data#") and download_url is None:
            download_url = href
    return download_url, opendap_url


async def search_granules(
    *,
    collection_concept_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    bounding_box: tuple[float, float, float, float] | None = None,
    page_size: int = 20,
    page_num: int = 1,
    max_pages: int = 3,
) -> list[dict[str, Any]]:
    """Query NASA CMR granules with temporal, spatial bounding box, and pagination support."""
    all_granules: list[dict[str, Any]] = []
    current_page = page_num

    async with httpx.AsyncClient(timeout=15.0) as client:
        while current_page < page_num + max_pages:
            params: dict[str, Any] = {
                "collection_concept_id": collection_concept_id,
                "page_size": page_size,
                "page_num": current_page,
                "sort_key": "start_date",
            }
            if start_date and end_date:
                params["temporal"] = build_cmr_temporal_param(start_date, end_date)
            if bounding_box is not None:
                # CMR bounding_box format: west,south,east,north
                w, s, e, n = bounding_box
                params["bounding_box"] = f"{w},{s},{e},{n}"

            resp = await client.get(CMR_GRANULES_URL, params=params)
            resp.raise_for_status()
            entries = resp.json().get("feed", {}).get("entry", [])
            if not entries:
                break

            for g in entries:
                dl_url, opendap_url = _extract_granule_links(g)
                raw_size = g.get("granule_size")
                try:
                    size_mb = round(float(raw_size), 4) if raw_size is not None else None
                except (TypeError, ValueError):
                    size_mb = None
                all_granules.append(
                    {
                        "granule_id": g.get("id", ""),
                        "title": g.get("title", ""),
                        "collection_concept_id": collection_concept_id,
                        "time_start": g.get("time_start"),
                        "time_end": g.get("time_end"),
                        "size_mb": size_mb,
                        "checksum": g.get("checksum"),
                        "checksum_algorithm": g.get("checksum_algorithm"),
                        "download_url": dl_url,
                        "opendap_url": opendap_url,
                        "format": g.get("original_format"),
                    }
                )

            if len(entries) < page_size:
                break
            current_page += 1

    return all_granules
