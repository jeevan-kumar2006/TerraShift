# NASA Earthdata Login & Copernicus CDS Authentication Setup

> **Security Rule:** Never commit credentials, `.netrc`, `_netrc`, `.cdsapirc`, or bearer tokens into Git. TerraShift `.gitignore` blocks all secret files automatically.

## 1. NASA Earthdata Login (Required for MOPITT, MERRA-2, MODIS, GPM, SMAP, GLDAS, AppEEARS)

### Option A: EDL Bearer Token (Recommended)
1. Sign in or register at https://urs.earthdata.nasa.gov/
2. Generate an Earthdata Login token (`Generate Token` under User Profile).
3. Export as an environment variable before running the backend:

**PowerShell (Windows):**
```powershell
$env:EARTHDATA_TOKEN = "<your-edl-bearer-token>"
```

**macOS / Linux:**
```bash
export EARTHDATA_TOKEN="<your-edl-bearer-token>"
```

### Option B: `.netrc` / `_netrc` (Used automatically by `earthaccess` & `httpx` workflows)
- Windows path: `%USERPROFILE%\_netrc`
- Linux / macOS path: `~/.netrc` (must have `chmod 600 ~/.netrc`)

```text
machine urs.earthdata.nasa.gov
login YOUR_EARTHDATA_USERNAME
password YOUR_EARTHDATA_PASSWORD
```

### Checking Authentication Status Safely
```bash
python -c "from backend.acquisition import get_auth_diagnostics; import json; print(json.dumps(get_auth_diagnostics(), indent=2))"
```
Or inspect `GET http://127.0.0.1:8000/api/acquisition/auth-status` (returns only booleans and provider names — never secrets).

---

## 2. Copernicus Climate Data Store (Required for ERA5 Monthly & CAMS CH4)

1. Register at https://cds.climate.copernicus.eu/ and obtain your Personal Access Token.
2. Create `~/.cdsapirc` (`%USERPROFILE%\.cdsapirc` on Windows):

```yaml
url: https://cds.climate.copernicus.eu/api
key: YOUR_CDS_API_KEY
```

---

## 3. Unauthenticated Workflows (Work Out-of-the-Box Without Keys)
- **NASA CMR Collection & Granule Discovery** (`cmr.earthdata.nasa.gov/search/*`)
- **NASA POWER Monthly Point & Regional NetCDF API** (`<= 10° × 10°` spatial tile, 1 parameter per NetCDF call)
- **Local GeoJSON India Polygon Extraction, File Validation & QC Pipelines** (`backend/acquisition/`)
