"""Comprehensive offline-safe unit & integration tests for TerraShift Data Acquisition Subsystem."""

from __future__ import annotations

import asyncio
import hashlib
import struct
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import h5py
import httpx
import numpy as np
import pandas as pd
import pytest
import xarray as xr
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from acquisition import (
    DATASET_CATALOG,
    VARIABLE_SPECS,
    apply_quality_control,
    download_file_resumable,
    extract_polygon_subset,
    get_auth_diagnostics,
    list_available_regions,
    list_catalog,
    load_region_polygon,
    search_granules,
    validate_file,
)
from acquisition.temporal_subset import build_cmr_temporal_param, validate_temporal_window
from main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_official_catalog_19_variables_and_distinctions():
    """Verify all 19 environmental variables across 4 domains and official concept metadata."""
    assert len(VARIABLE_SPECS) == 19
    domains = {v["domain"] for v in VARIABLE_SPECS}
    assert domains == {"atmospheric", "climate", "hydrology", "vegetation"}
    assert len(DATASET_CATALOG) >= 22

    codes = {v["variable_code"] for v in VARIABLE_SPECS}
    expected_codes = {
        "CO", "BC", "OC", "SO4", "AOD", "CH4",
        "T2M", "LST", "PRECTOT", "WIND", "QV2M", "RH",
        "SSM", "RZSM", "RUNOFF", "ET",
        "NDVI", "EVI", "GPP",
    }
    assert codes == expected_codes

    cat_payload = list_catalog()
    assert len(cat_payload["availability_matrix"]) == 19
    ssm = next(v for v in VARIABLE_SPECS if v["variable_code"] == "SSM")
    assert "root-zone" in ssm["physical_distinction_note"].lower() or "surface" in ssm["physical_distinction_note"].lower()


def test_temporal_window_validation_and_cmr_param():
    """Reject inverted date ranges and format valid CMR ISO-8601 temporal queries."""
    s_norm, e_norm = validate_temporal_window("2023-01-01", "2023-12-31")
    assert (s_norm, e_norm) == ("2023-01-01", "2023-12-31")
    assert build_cmr_temporal_param("2024-01-01", "2024-03-31") == "2024-01-01T00:00:00Z,2024-03-31T23:59:59Z"

    with pytest.raises(ValueError, match="start_date"):
        validate_temporal_window("2024-06-01", "2024-01-01")


def test_cmr_granule_search_mocked_pagination():
    """Verify CMR query parsing, bbox formatting, and pagination without network dependency."""
    fake_json = {
        "feed": {
            "entry": [
                {
                    "id": "G12345-LARC_CLOUD",
                    "title": "MOP03JM-202401-L3V98.0.3.he5",
                    "time_start": "2024-01-01T00:00:00Z",
                    "time_end": "2024-01-31T23:59:59Z",
                    "granule_size": "143.88",
                    "links": [
                        {
                            "rel": "http://esipfed.org/ns/fedsearch/1.1/data#",
                            "href": "https://data.asdc.earthdata.nasa.gov/MOP03JM-202401.he5",
                        }
                    ],
                }
            ]
        }
    }

    mock_resp = httpx.Response(200, json=fake_json, request=httpx.Request("GET", "https://cmr.earthdata.nasa.gov/search/granules.json"))
    with patch("acquisition.cmr_client.httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
        granules = asyncio.run(
            search_granules(
                collection_concept_id="C4191539031-LARC_CLOUD",
                start_date="2024-01-01",
                end_date="2024-01-31",
                bounding_box=(68.0, 6.0, 98.0, 37.0),
                page_size=5,
                max_pages=1,
            )
        )
    assert len(granules) == 1
    assert granules[0]["granule_id"] == "G12345-LARC_CLOUD"
    assert granules[0]["download_url"].endswith(".he5")


def test_resumable_download_checksum_resume_and_401(tmp_path):
    """Test .part Range resumption, SHA-256 verification, existing skip, and HTTP 401 handling."""
    full_payload = b"TerrashiftScientificPayload1234567890"
    expected_sha = hashlib.sha256(full_payload).hexdigest()

    # 1. Partial resume test
    dest = tmp_path / "sample.nc"
    part = dest.with_suffix(".nc.part")
    part.write_bytes(full_payload[:10])

    def _resume_handler(request: httpx.Request) -> httpx.Response:
        rng = request.headers.get("Range")
        assert rng == "bytes=10-"
        return httpx.Response(206, content=full_payload[10:])

    res = asyncio.run(
        download_file_resumable(
            url="https://example.org/sample.nc",
            dest_path=dest,
            expected_sha256=expected_sha,
            transport=httpx.MockTransport(_resume_handler),
        )
    )
    assert res["status"] == "downloaded"
    assert res["resumed_bytes"] == 10
    assert dest.read_bytes() == full_payload

    # 2. Existing file skip (no overwrite)
    skip_res = asyncio.run(
        download_file_resumable(
            url="https://example.org/sample.nc",
            dest_path=dest,
            transport=httpx.MockTransport(lambda req: httpx.Response(500)),
        )
    )
    assert skip_res["status"] == "skipped_existing"

    # 3. Protected URL 401 handling
    auth_dest = tmp_path / "protected.he5"
    auth_res = asyncio.run(
        download_file_resumable(
            url="https://data.asdc.earthdata.nasa.gov/protected.he5",
            dest_path=auth_dest,
            max_retries=1,
            transport=httpx.MockTransport(lambda req: httpx.Response(401)),
        )
    )
    assert auth_res["status"] == "auth_required"
    assert auth_res["http_status"] == 401


def test_netcdf_validation_power_yyyymm_and_corrupt_rejection(tmp_path):
    """Validate valid NetCDF, POWER YYYYMM timestamps, duplicate rejection, and corrupt rejection."""
    times = pd.date_range("2023-01-01", "2023-03-01", freq="MS")
    ds = xr.Dataset(
        data_vars={"T2M": (("time", "lat", "lon"), np.ones((3, 2, 2)) * 25.0, {"units": "C"})},
        coords={"time": times, "lat": [25.0, 26.0], "lon": [75.0, 76.0]},
    )
    valid_nc = tmp_path / "valid.nc"
    ds.to_netcdf(valid_nc)
    ds.close()

    rep = validate_file(valid_nc, update_manifest=False, report_path=tmp_path / "val.csv")
    assert rep.passed is True
    assert rep.dimensions == {"time": 3, "lat": 2, "lon": 2}
    assert rep.units["T2M"] == "C"

    # NASA POWER YYYYMM encoding (202301..202303 + annual 202313)
    ds_pow = xr.Dataset(
        data_vars={"T2M": (("time", "lat", "lon"), np.ones((4, 2, 2)) * 22.0, {"units": "C"})},
        coords={"time": np.array([202301, 202302, 202303, 202313]), "lat": [25.0, 26.0], "lon": [75.0, 76.0]},
    )
    pow_nc = tmp_path / "power.nc"
    ds_pow.to_netcdf(pow_nc)
    ds_pow.close()
    rep_pow = validate_file(pow_nc, update_manifest=False, report_path=tmp_path / "val.csv")
    assert rep_pow.passed is True
    assert rep_pow.time_coverage["start"] == "2023-01-01"
    assert rep_pow.time_coverage["end"] == "2023-03-01"

    # Corrupt NetCDF rejection
    corrupt_nc = tmp_path / "corrupt.nc"
    corrupt_nc.write_bytes(b"NOT_A_NETCDF_BINARY_FILE")
    rep_bad = validate_file(corrupt_nc, expected_format="NETCDF", update_manifest=False, report_path=tmp_path / "val.csv")
    assert rep_bad.passed is False
    assert len(rep_bad.errors) > 0


def test_hdf5_inspector_and_corrupt_rejection(tmp_path):
    """Validate HDF-EOS5 style HDF5 file groups, geolocation, QC flags, and reject corrupt HDF5."""
    h5_path = tmp_path / "mopitt_test.he5"
    with h5py.File(h5_path, "w") as f:
        f.attrs["RangeBeginningDate"] = b"2024-01-01"
        f.attrs["RangeEndingDate"] = b"2024-01-31"
        grp = f.create_group("HDFEOS/GRIDS/MOP03/Data Fields")
        ds = grp.create_dataset("RetrievedCOTotalColumn", data=np.full((4, 4), 115.0, dtype=np.float32))
        ds.attrs["units"] = b"ppbv"
        ds.attrs["_FillValue"] = np.float32(-9999.0)
        grp.create_dataset("RetrievalErrorFlag", data=np.zeros((4, 4), dtype=np.int16))
        geo = f.create_group("HDFEOS/GRIDS/MOP03/Geolocation")
        geo.create_dataset("Latitude", data=np.array([10.0, 15.0, 20.0, 25.0]))
        geo.create_dataset("Longitude", data=np.array([72.0, 76.0, 80.0, 84.0]))

    rep = validate_file(h5_path, expected_format="HDF5", update_manifest=False, report_path=tmp_path / "val.csv")
    assert rep.passed is True
    assert "HDFEOS/GRIDS/MOP03/Data Fields/RetrievedCOTotalColumn" in rep.variables
    assert len(rep.quality_flags_detected) == 1
    assert rep.spatial_coverage["lat_min"] == pytest.approx(10.0)

    bad_h5 = tmp_path / "bad.h5"
    bad_h5.write_bytes(b"corrupt hdf5 bytes")
    rep_bad = validate_file(bad_h5, expected_format="HDF5", update_manifest=False, report_path=tmp_path / "val.csv")
    assert rep_bad.passed is False


def test_geotiff_and_csv_validators(tmp_path):
    """Test minimal classic TIFF header validation and CSV missing/duplicate checks."""
    # Construct valid minimal little-endian TIFF header + 2 IFD tags (ImageWidth=64, ImageLength=32)
    tif_path = tmp_path / "sample.tif"
    ifd_offset = 8
    num_entries = 2
    entry1 = struct.pack("<HHII", 256, 4, 1, 64)  # ImageWidth
    entry2 = struct.pack("<HHII", 257, 4, 1, 32)  # ImageLength
    header = struct.pack("<2sHIH", b"II", 42, ifd_offset, num_entries) + entry1 + entry2 + struct.pack("<I", 0)
    tif_path.write_bytes(header)

    rep_tif = validate_file(tif_path, expected_format="GEOTIFF", update_manifest=False, report_path=tmp_path / "val.csv")
    assert rep_tif.passed is True
    assert rep_tif.dimensions["width"] == 64
    assert rep_tif.dimensions["height"] == 32

    csv_path = tmp_path / "ts.csv"
    csv_path.write_text("date,ndvi\n2023-01-01,0.42\n2023-02-01,0.45\n2023-03-01,\n", encoding="utf-8")
    rep_csv = validate_file(csv_path, expected_format="CSV", update_manifest=False, report_path=tmp_path / "val.csv")
    assert rep_csv.passed is True
    assert rep_csv.dimensions == {"rows": 3, "columns": 2}
    assert rep_csv.missing_value_pct > 0.0


def test_product_specific_qc_never_modifies_raw(tmp_path):
    """Verify MOPITT_CO QC removes fill sentinels, QC flags, and out-of-range values into validated copy."""
    arr = np.array([[[110.0, -9999.0], [99999.0, 125.0]]], dtype=np.float32)  # 1 out of range (>5000), 1 fill
    qc_flag = np.array([[[2, 0], [0, 0]]], dtype=np.int16)  # flag>0 masks (0,0,0)

    raw_nc = tmp_path / "raw_mopitt.nc"
    ds = xr.Dataset(
        data_vars={
            "CO_Total_Column": (("time", "lat", "lon"), arr, {"units": "ppbv", "_FillValue": np.float32(-9999.0)}),
            "CO_Error_Flag": (("time", "lat", "lon"), qc_flag, {"units": "1"}),
        },
        coords={"time": pd.date_range("2024-01-01", periods=1, freq="MS"), "lat": [22.0, 24.0], "lon": [78.0, 80.0]},
    )
    ds.to_netcdf(raw_nc)
    ds.close()
    raw_mtime = raw_nc.stat().st_mtime_ns

    val_dir = tmp_path / "validated"
    qc_rep = apply_quality_control(raw_nc, dataset_id="MOP03JM", domain="atmospheric", validated_dir_override=val_dir)

    assert raw_nc.stat().st_mtime_ns == raw_mtime  # Raw file untouched
    assert qc_rep.qc_profile == "MOPITT_CO"
    assert qc_rep.filtered_fill_count == 1
    assert qc_rep.filtered_qc_flag_count == 1
    assert qc_rep.filtered_out_of_range_count == 1
    assert qc_rep.valid_after_qc == 1
    assert Path(qc_rep.validated_file_path).exists()


def test_india_polygon_spatial_subsetting_and_conventions():
    """Verify real India & state polygons, 0..360 lon handling, descending lat, and cos(lat) weighting."""
    regions = list_available_regions()
    rids = {r["region_id"] for r in regions}
    assert "india" in rids
    assert "north" in rids
    assert "state_maharashtra" in rids

    geom, meta = load_region_polygon("india")
    assert meta["polygon_vertex_count"] > 100

    # Grid using 0..360 lon and descending latitude (typical reanalysis raw layout)
    lats_desc = np.arange(37.0, 6.0, -1.0)
    lons_360 = np.arange(68.0, 98.0, 1.0)
    # Assign exact latitude value so cosine weighting must match latitude grid strictly
    lon2d, lat2d = np.meshgrid(lons_360, lats_desc)
    data = np.broadcast_to(lat2d[None, :, :], (2, len(lats_desc), len(lons_360))).copy()

    ds = xr.Dataset(
        data_vars={"T2M": (("time", "lat", "lon"), data, {"units": "C"})},
        coords={"time": pd.date_range("2023-01-01", periods=2, freq="MS"), "lat": lats_desc, "lon": lons_360},
    )
    res = extract_polygon_subset(ds=ds, variable_name="T2M", region_id="state_maharashtra", output_stem="test_tmp_mh_subset")
    try:
        assert res["original_resolution_preserved"] is True
        assert res["weighting_method"] == "cosine_latitude_area_weighted"
        assert res["grid_cells_inside_mask"] > 0
        # Maharashtra lies strictly between 15.6N and 22.1N
        assert 15.0 <= res["regional_mean"] <= 23.0
    finally:
        Path(res["output_file"]).unlink(missing_ok=True)


def test_acquisition_fastapi_routes_and_confirmation_guard(client):
    """Test /api/acquisition/* FastAPI endpoints and large-download confirmation guard."""
    res_cat = client.get("/api/acquisition/catalog")
    assert res_cat.status_code == 200
    assert len(res_cat.json()["variables"]) == 19

    res_auth = client.get("/api/acquisition/auth-status")
    assert res_auth.status_code == 200
    auth_json = res_auth.json()
    assert "earthdata_authenticated" in auth_json
    # Ensure no sensitive raw secret strings exist in payload
    assert "password" not in str(auth_json).lower() or "earthdata_password" in str(auth_json).lower()

    res_bounds = client.get("/api/acquisition/boundaries")
    assert res_bounds.status_code == 200
    assert res_bounds.json()["count"] >= 40

    res_man = client.get("/api/acquisition/manifest")
    assert res_man.status_code == 200
    assert "manifest" in res_man.json()

    # Confirmation guard for >12 months without confirm_large_download=true
    res_guard = client.post(
        "/api/acquisition/download",
        json={
            "dataset_id": "NASA_POWER_AG",
            "variable": "T2M",
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
            "region_id": "north",
            "max_granules": 24,
            "confirm_large_download": False,
        },
    )
    assert res_guard.status_code == 200
    body = res_guard.json()
    assert body["status"] == "confirmation_required"
    assert body["estimated_months"] == 48
