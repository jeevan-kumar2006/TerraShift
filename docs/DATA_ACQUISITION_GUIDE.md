# TerraShift Data Acquisition Architecture Guide

## Overview

TerraShift separates lightweight interactive point-series exploration (`backend/nasa_service.py`) from full gridded scientific dataset acquisition, validation, quality control, and India polygon extraction (`backend/acquisition/`).

All existing statistical analysis (`backend/stats_engine.py`), AI synthesis (`backend/ai_explainer.py`), and API endpoints (`/api/investigate`, `/api/import-series`, `/api/partner-intel`) remain intact and unmodified.

## Storage Hierarchy

```text
data/
├── raw/
│   ├── atmospheric/<VAR>/<SOURCE>/   # Unmodified source NetCDF / HDF5 granules
│   ├── climate/<VAR>/<SOURCE>/
│   ├── hydrology/<VAR>/<SOURCE>/
│   └── vegetation/<VAR>/<SOURCE>/
├── validated/
│   └── <domain>/                     # QC-cleaned NetCDF files (*_validated.nc)
├── processed/
│   ├── india/                        # Cosine-latitude weighted India subsets
│   ├── north/ south/ east/ west/ central/ northeast/
└── boundaries/
    ├── india/india_outline.geojson   # Real India country boundary polygon
    ├── states/india_states.geojson   # 36 Indian States/UTs grouped by macro-zone
    └── districts/india_sample_districts.geojson

metadata/
├── dataset_catalog.csv               # Full 25-entry Earth observation dataset catalog
├── variable_metadata.json            # Full 19-variable registry with physical distinctions
├── download_manifest.csv             # SHA-256 hashes, granule IDs, retrieval & validation status
└── validation_report.csv             # Structural validation metrics per inspected file

logs/
├── downloads/activity.log
├── validation/activity.log
└── errors/activity.log
```

> **Raw Immutability Guarantee:** Files inside `data/raw/` are never modified in-place. Resumable `.part` staging files are verified via size and SHA-256/MD5 checksums before moving into `data/raw/`. Quality-controlled outputs are saved exclusively to `data/validated/`, and GeoJSON polygon masks to `data/processed/`.

## Module Architecture (`backend/acquisition/`)

- `dataset_registry.py` & `catalog_service.py`: Official 19-variable registry across Atmospheric Composition, Climate, Hydrology, and Vegetation/Land with verified NASA CMR Concept IDs and physical distinction notes.
- `earthdata_auth.py`: Multi-method credential resolver (`EARTHDATA_TOKEN`, `EARTHDATA_USERNAME`/`EARTHDATA_PASSWORD`, `~/.netrc` / `_netrc`, `earthaccess`, `CDSAPI_KEY` / `~/.cdsapirc`) with safe non-secret diagnostics.
- `cmr_client.py`, `appeears_client.py`, `gesdisc_client.py`, `copernicus_client.py`: Official discovery, spatial/temporal subset URL builders, and client wrappers.
- `download_manager.py`: Resumable HTTP Range downloader (`If-Range` / `.part`), retries, concurrency throttling, duplicate manifest protection, and direct unauthenticated NASA POWER Regional NetCDF downloader (`<= 10° × 10°`, 1 parameter per request).
- `netcdf_inspector.py`, `hdf5_inspector.py`, `file_validator.py`: Deep read-only validation of NetCDF (including NASA POWER `YYYYMM`/`YYYY13`), HDF5/HDF-EOS5, GeoTIFF, and CSV archives.
- `quality_control.py`: Product-specific QC masking (`MOPITT_CO`, `MERRA2_AER_CHM`, `MODIS_LST_VI`, `GPM_IMERG`, `SMAP_GLDAS`, `NASA_POWER`).
- `spatial_subset.py`: `shapely` point-in-polygon grid masking over real India/state/district boundaries with cosine-latitude area weighting and native resolution preservation.

## FastAPI Endpoints

- `GET /api/acquisition/catalog`
- `GET /api/acquisition/auth-status`
- `GET /api/acquisition/boundaries`
- `GET /api/acquisition/cmr-search`
- `GET /api/acquisition/manifest`
- `POST /api/acquisition/download` (enforces confirmation when spanning >12 months or >12 granules)
