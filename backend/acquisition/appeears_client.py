"""NASA AppEEARS API client for product lookup and authenticated task preparation."""

from __future__ import annotations

from typing import Any
import httpx

from .earthdata_auth import get_earthdata_credentials


APPEEARS_BASE_URL = "https://appeears.earthdatacloud.nasa.gov/api/v1"


async def list_appeears_products() -> list[dict[str, Any]]:
    """Fetch public AppEEARS product catalog (no authentication needed for listing)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{APPEEARS_BASE_URL}/product")
        resp.raise_for_status()
        products = resp.json()
    return [
        {
            "product_and_version": p.get("ProductAndVersion"),
            "description": p.get("Description"),
            "platform": p.get("Platform"),
            "resolution": p.get("Resolution"),
            "temporal_granularity": p.get("TemporalGranularity"),
        }
        for p in products
        if isinstance(p, dict)
    ]


def build_area_task_payload(
    *,
    task_name: str,
    product_and_version: str,
    layers: list[str],
    start_date: str,
    end_date: str,
    geojson_feature: dict[str, Any],
    output_format: str = "netcdf4",
) -> dict[str, Any]:
    """Build a standard AppEEARS area extraction task payload (MM-DD-YYYY format)."""
    s_mmddyyyy = f"{start_date[5:7]}-{start_date[8:10]}-{start_date[:4]}"
    e_mmddyyyy = f"{end_date[5:7]}-{end_date[8:10]}-{end_date[:4]}"
    return {
        "task_type": "area",
        "task_name": task_name,
        "params": {
            "dates": [{"startDate": s_mmddyyyy, "endDate": e_mmddyyyy}],
            "layers": [{"product": product_and_version, "layer": layer} for layer in layers],
            "output": {
                "format": {"type": output_format},
                "projection": "geographic",
            },
            "geo": geojson_feature,
        },
    }


async def login_appeears() -> tuple[bool, str | None, str]:
    """Authenticate against AppEEARS using EARTHDATA_USERNAME/PASSWORD; never expose token in logs."""
    creds = get_earthdata_credentials()
    if not creds:
        return False, None, "AppEEARS task submission requires EARTHDATA_USERNAME and EARTHDATA_PASSWORD."
    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.post(f"{APPEEARS_BASE_URL}/login", auth=creds)
        if resp.status_code != 200:
            return False, None, f"AppEEARS login failed with HTTP {resp.status_code}"
        token = resp.json().get("token")
        return bool(token), token, "AppEEARS authenticated"
