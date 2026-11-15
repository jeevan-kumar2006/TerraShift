# TerraShift Acquisition, Validation & India Subsetting Workflow

## 1. End-to-End Pilot Verification (`MOP03JM` + Live `NASA POWER Regional NetCDF`)

Run the reproducible pilot script from the repository root:

```powershell
python -m backend.acquisition.pilot_mopitt_co
```

What this workflow performs:
1. Queries **live NASA CMR** (`C4191539031-LARC_CLOUD`) for `MOP03JM` v10 granules over India (`[68, 6, 98, 37]`, 2024-01 to 2024-03).
2. Checks Earthdata authentication cleanly and attempts protected ASDC `.he5` download (logs honest HTTP `401` when `EARTHDATA_TOKEN`/`.netrc` is absent).
3. Validates `data/raw/atmospheric/CO/MOPITT/MOP03JM_202401_202403_India_pilot.nc`, applies `MOPITT_CO` QC (`_FillValue=-9999`, companion `CO_Error_Flag == 0`, physical bounds) into `data/validated/atmospheric/`, and masks grid cells inside `data/boundaries/india/india_outline.geojson` with `cos(latitude)` weighting into `data/processed/india/`.
4. Executes a **live unauthenticated NASA POWER Regional NetCDF download** for North India (`24°–32°N, 72°–80°E`, `2023`, `T2M`), validates `YYYYMM`/`YYYY13` timestamps, applies `NASA_POWER` QC, and masks strictly inside the North India polygon into `data/processed/north/`.
5. Updates `metadata/download_manifest.csv`, `metadata/validation_report.csv`, `metadata/dataset_catalog.csv`, and `metadata/variable_metadata.json`.

---

## 2. Downloading New Data via the TerraShift UI

1. Open the **Data Acquisition** tab in the top navigation bar.
2. Select a domain filter (`Atmospheric`, `Climate`, `Hydrology`, or `Vegetation`) and click any dataset (`NASA_POWER_AG`, `MOP03JM`, `M2TMNXAER`, `MOD13C2`, etc.).
3. Choose an **India Polygon Boundary** (Country `india`, 6 Macro-Zones, 36 States/UTs, or 38 Districts) and target temporal dates.
4. Click **Discover NASA CMR Granules** to preview matching files and sizes without downloading.
5. Click **Acquire, Validate & Subset India**:
   - Windows spanning >12 months trigger a mandatory confirmation modal.
   - `NASA_POWER_AG` fetches live NetCDF immediately with zero credentials.
   - Protected NASA datasets return discovered CMR granules plus authentication instructions if credentials are not configured, and download/validate automatically once credentials are present.

---

## 3. Running Automated Tests

```powershell
python -m pytest -v backend/tests/test_stats.py backend/tests/test_api_integration.py backend/tests/test_acquisition.py
```

```powershell
cd frontend
npm run build
```
