# TerraShift — Phase 0 Data Acquisition Audit

**Audit Date:** 2026-11-15  
**Scope:** Baseline inspection of `README.md`, `RULES.md`, `backend/main.py`, `backend/nasa_service.py`, `backend/stats_engine.py`, `backend/requirements.txt`, `backend/tests/*`, and `frontend/src/*` prior to implementing the `backend/acquisition/` subsystem.

---

## 1. Existing Data Integrations Summary

| Source / Service | Module | Current Capability | Auth Used |
| :--- | :--- | :--- | :--- |
| **NASA POWER Monthly API** | `backend/nasa_service.py` | Live monthly JSON point retrieval (`T2M`, `PRECTOTCORR`, `GWETROOT`, `GWETPROF`, `WS10M`, `QV2M`, `ALLSKY_SFC_SW_DWN`, `PS`) routed to `AG` community with local `cases_cache.json` caching and bounded (`<= 500 km`) fallback. | Zero-auth |
| **NASA CMR Collections** | `backend/nasa_service.py` (`fetch_cmr_collections`) | Queries `collections.json` for up to 3 collection summaries per bounding box/keyword (`SWOT`, `SeaWiFS`, `MODIS`, `GPM`, `GLDAS`). Does not search granules or download files. | Zero-auth (discovery) |
| **NASA AppEEARS** | `backend/nasa_service.py` (`fetch_appeears_products`) | Lists public products via `/api/v1/product` and parses manually uploaded AppEEARS CSVs via `POST /api/import-series`. Does not submit AppEEARS extraction tasks or poll/download task bundles. | None wired (task API needs Earthdata Login) |
| **NASA Giovanni & GES DISC Hydrology** | `backend/nasa_service.py` (`build_partner_deep_links`, `parse_external_timeseries`) | Generates coordinate-parameterized external portal links (`Manual Export -> Import`) and parses user-exported CSVs. No programmatic GES DISC OPeNDAP/granule download. | N/A (manual portal) |
| **KNMI Climate Explorer & NOAA CDO** | `backend/nasa_service.py` | Deep links + 13-column KNMI `.dat` parser + optional `NOAA_CDO_TOKEN` station lookup. | Optional `NOAA_CDO_TOKEN` |
| **CSA / Geo.ca MSC GeoMet** | `backend/nasa_service.py` (`fetch_csa_geomet_stations`) | Live station lookup for Canadian monthly climate and hydrometric means. | Zero-auth |
| **Copernicus CDS / CDSE** | N/A | Not integrated yet (`cdsapi` not installed, no ERA5/CAMS download client). | Needs `CDSAPI_KEY` |

---

## 2. Capability Classification Matrix

### A. Fully Implemented and Tested
- **NASA POWER Monthly Point Time Series** (`fetch_nasa_monthly` in `backend/nasa_service.py`): Live retrieval, MERRA-2 provenance builder (`build_series_provenance`), coordinate validation, and bounded (`<= 500 km`) offline fallback.
- **CSV / ASCII Multi-Agency Importer** (`parse_external_timeseries`, `POST /api/import-series`): Parses NASA Giovanni CSV, GES DISC Hydrology CSV, AppEEARS CSV, NOAA CDO CSV, and KNMI 13-column `.dat` files with synthetic demo detection (`# SYNTHETIC_DEMO_DATA`).
- **Statistical Time-Series Engine** (`backend/stats_engine.py`): Complete monthly date indexing (`MS`), duplicate timestamp averaging, missing-data percentage & `<= 3` month gap guard, STL decomposition (`period=12`), Standard & Hamed-Rao Mann-Kendall (`S`, `tau`, `Z`, `p`), Sen's slope with 95% CI, OLS regression & Student's t-test (`t`, `df`, `p`), lag-1 autocorrelation check, and non-destructive outlier flagging.

### B. Partially Implemented
- **NASA CMR Integration**: Currently only fetches 3 collection titles via `fetch_cmr_collections`. Lacks full 19-variable concept-ID mapping, granule search, pagination, size/checksum inspection, and OPeNDAP/download URL extraction.
- **NASA AppEEARS Integration**: Currently only lists catalog products (`fetch_appeears_products`) and imports user-uploaded CSVs. Lacks Earthdata token login, point/area task submission, and result download.
- **Data Quality Control & Validation**: Enforced for 1D monthly CSV/JSON point time series (`stats_engine.py` and `-990` fill filter in `nasa_service.py`), but lacks multi-dimensional NetCDF (`xarray`), HDF5/HDF-EOS5 (`h5py`), and GeoTIFF inspection or product-specific bitmask QC filtering.
- **Local Caching**: Single-file JSON cache (`backend/cases_cache.json`) for 1D point responses only; no raw/validated/processed directory hierarchy, no download manifest, and no Zarr/NetCDF binary management.

### C. Discovered but Not Downloadable
- **Satellite & Gridded Collections in Partner Hub**: `SWOT`, `SeaWiFS`, `MODIS` (`MOD11C3`, `MOD13C2`, `MOD08_M3`), `GPM_3IMERGM`, `GLDAS_NOAH025_M`, `MOPITT` (`MOP03JM`), `SMAP` (`SPL3SMP_E`), and `MERRA-2` collections are referenced or discovered at collection level, without a granule/subset download pipeline.
- **NASA Giovanni / GES DISC Hydrology / KNMI**: Linked as external `Manual Export -> Import` web portals.

### D. Missing
- Dedicated modular `backend/acquisition/` Python package (`dataset_registry.py`, `cmr_client.py`, `earthdata_auth.py`, `download_manager.py`, `spatial_subset.py`, `temporal_subset.py`, `file_validator.py`, `netcdf_inspector.py`, `hdf5_inspector.py`, `quality_control.py`, `manifest_manager.py`, `storage_manager.py`, `appeears_client.py`, `gesdisc_client.py`, `copernicus_client.py`, `models.py`).
- Authoritative 19-variable environmental catalog (`CO`, `BC`, `OC`, `SO4`, `AOD`, `CH4`, `T2M`, `LST`, `PRECTOT`, `WIND`, `QV2M`, `RH`, `SSM`, `RZSM`, `RUNOFF`, `ET`, `NDVI`, `EVI`, `GPP`) & `metadata/dataset_catalog.csv`.
- Scientific binary dependencies (`xarray`, `netCDF4`, `h5py`, `shapely`, `earthaccess`, `cdsapi`, `zarr`) in the environment and `backend/requirements.txt`.
- Authoritative India boundary polygons (country, 6 macro-regions: North, South, East, West, Central, Northeast, states, and districts) with true polygon masking (`shapely`) and cosine-latitude area weighting.
- Multi-format validation reports (`metadata/validation_report.csv`), download manifests (`metadata/download_manifest.csv`), and acquisition logs (`logs/{downloads,validation,errors}/`).
- First Pilot Acquisition workflow (`MOPITT` L3 CO `MOP03JM` sample over India).
- Frontend Data Acquisition Explorer, Auth Diagnostics, Download Configurator, and Manifest UI.

### E. Requires External Authentication
- **NASA Earthdata Login (`EARTHDATA_TOKEN` or `EARTHDATA_USERNAME`/`EARTHDATA_PASSWORD` / `~/.netrc`)**: Required to download protected DAAC granules from ASDC (`LARC_CLOUD` MOPITT `MOP03JM`), `GES_DISC` (`M2TMNX*`, `GPM_3IMERGM`, `GLDAS_NOAH025_M`), `LPCLOUD` (`MOD11C3`, `MOD13C2`), and `NSIDC_CPRD` (`SPL3SMP_E`), and to submit AppEEARS tasks.
- **Copernicus Climate Data Store (`CDSAPI_KEY` / `~/.cdsapirc`)**: Required for `ERA5` and `CAMS` global reanalysis downloads.
- **NOAA NCEI CDO (`NOAA_CDO_TOKEN`)**: Required for live NOAA CDO API v2 station queries.

---

## 3. Environment & Baseline Check Results (Pre-Upgrade)
- **Installed packages**: `fastapi`, `uvicorn`, `numpy`, `pandas`, `scipy`, `statsmodels`, `httpx`, `requests`, `pydantic`, `pytest`, `pymannkendall`.
- **Missing packages (to install in Step 2)**: `xarray`, `netCDF4`, `h5py`, `shapely`, `earthaccess`, `cdsapi`, `zarr`.
- **Host credential check**: `HAS_NETRC: False`, `HAS_EDL_ENV: False`, `HAS_CDS: False`.
- **Baseline pytest**: Executed prior to code edits (20 existing unit & integration tests verified).
