"""Secure authentication & diagnostics for NASA Earthdata Login, earthaccess, AppEEARS, and Copernicus CDS."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _find_netrc_path() -> Path | None:
    for candidate in (Path.home() / ".netrc", Path.home() / "_netrc"):
        if candidate.exists() and candidate.is_file():
            try:
                content = candidate.read_text(encoding="utf-8", errors="ignore")
                if "urs.earthdata.nasa.gov" in content:
                    return candidate
            except OSError:
                continue
    return None


def _has_cds_config() -> tuple[bool, str]:
    if os.environ.get("CDSAPI_KEY", "").strip():
        return True, "env:CDSAPI_KEY"
    cdsapirc = Path.home() / ".cdsapirc"
    if cdsapirc.exists() and cdsapirc.is_file():
        return True, f"file:{cdsapirc.name}"
    return False, "unconfigured"


def get_earthdata_token() -> str | None:
    """Return EARTHDATA_TOKEN from environment if configured (never logged or returned in public dicts)."""
    tok = os.environ.get("EARTHDATA_TOKEN", "").strip()
    return tok or None


def get_earthdata_credentials() -> tuple[str, str] | None:
    """Return (username, password) from env variables if both are set (never logged)."""
    user = os.environ.get("EARTHDATA_USERNAME", "").strip()
    pwd = os.environ.get("EARTHDATA_PASSWORD", "").strip()
    if user and pwd:
        return user, pwd
    return None


def get_auth_headers_for_url(url: str) -> dict[str, str]:
    """Build Authorization headers for NASA Earthdata protected URLs when bearer token is available."""
    headers = {"User-Agent": "TerraShift-EO-Acquisition/1.0"}
    if "earthdata.nasa.gov" in url or "gesdisc" in url or "asdc" in url or "lpdaac" in url or "nsidc" in url:
        tok = get_earthdata_token()
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
    return headers


def get_auth_diagnostics() -> dict[str, Any]:
    """Return safe, credential-free authentication status and setup instructions."""
    tok = get_earthdata_token()
    creds = get_earthdata_credentials()
    netrc_path = _find_netrc_path()

    try:
        import earthaccess  # type: ignore
        earthaccess_available = True
    except ImportError:
        earthaccess_available = False

    if tok:
        edl_ok = True
        edl_method = "env:EARTHDATA_TOKEN"
    elif creds:
        edl_ok = True
        edl_method = "env:EARTHDATA_USERNAME/PASSWORD"
    elif netrc_path is not None:
        edl_ok = True
        edl_method = f"netrc:{netrc_path.name}"
    else:
        edl_ok = False
        edl_method = "unconfigured"

    cds_ok, cds_method = _has_cds_config()
    missing: list[str] = []
    instructions: list[str] = []

    if not edl_ok:
        missing.append("NASA Earthdata Login (EARTHDATA_TOKEN or EARTHDATA_USERNAME + EARTHDATA_PASSWORD or ~/.netrc)")
        instructions.append(
            "Set EARTHDATA_TOKEN (recommended EDL Bearer Token from urs.earthdata.nasa.gov) or create ~/.netrc (_netrc on Windows) for machine urs.earthdata.nasa.gov."
        )
    if not cds_ok:
        missing.append("Copernicus CDS API (CDSAPI_KEY or ~/.cdsapirc)")
        instructions.append(
            "Set CDSAPI_KEY and CDSAPI_URL or configure ~/.cdsapirc from cds.climate.copernicus.eu to download ERA5/CAMS data."
        )

    return {
        "earthdata_authenticated": edl_ok,
        "earthdata_method": edl_method,
        "netrc_present": netrc_path is not None,
        "earthaccess_available": earthaccess_available,
        "copernicus_configured": cds_ok,
        "copernicus_method": cds_method,
        "appeears_ready": edl_ok,
        "missing_credentials": missing,
        "setup_instructions": instructions,
    }


def login_with_earthaccess() -> tuple[bool, str]:
    """Attempt earthaccess login using environment or netrc without leaking credentials."""
    try:
        import earthaccess  # type: ignore
    except ImportError:
        return False, "earthaccess library is not installed."

    diag = get_auth_diagnostics()
    if not diag["earthdata_authenticated"]:
        return False, "NASA Earthdata credentials missing. Set EARTHDATA_TOKEN, EARTHDATA_USERNAME/PASSWORD, or ~/.netrc."

    strategy = "environment" if (get_earthdata_token() or get_earthdata_credentials()) else "netrc"
    try:
        auth = earthaccess.login(strategy=strategy)
        if getattr(auth, "authenticated", False):
            return True, f"Authenticated via earthaccess ({strategy})"
        return False, f"earthaccess login via {strategy} did not establish an authenticated session."
    except Exception as exc:
        return False, f"earthaccess login error: {type(exc).__name__}"
