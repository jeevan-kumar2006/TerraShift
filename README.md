# TerraShift — India Earth System Trend Detective

**TerraShift** is an India-exclusive Earth observation trend analysis platform built for the **NASA Space Apps 2026 Challenge: Earth System Trend Detective**. It separates long-term climate and environmental trends from strong seasonal cycles across India's 36 states & Union Territories, 753 districts, and 10 physiographic regions.

---

## 1. Scientific Problem & Design Principles

Raw monthly satellite and meteorological records over India are dominated by the monsoon cycle (DJF, MAM, JJAS, ON). TerraShift prevents false trend claims by:
- **Never faking or hardcoding data**: every slope, p-value, confidence interval, legend range, and region average is computed at runtime from real NASA Earthdata / NASA POWER observations or user-imported Giovanni/AppEEARS CSVs.
- **Explicit uncertainty & statistical power**: insignificant trends (`p >= 0.05`) are never labeled as significant; TerraShift estimates the additional observation years required to reach statistical significance under stationary noise.
- **Strict satellite vs. model/reanalysis separation**: every chart and dossier displays a clear source badge (`Satellite: MODIS Terra` vs. `Model: NASA POWER / MERRA-2`).

---

## 2. Supported Datasets & DOIs

### Direct Satellite Missions (via NASA Earthdata / CMR / OPeNDAP)
| ID | Variable | Mission / Instrument | Spatial / Temporal | DOI |
| --- | --- | --- | --- | --- |
| `MOD13C2` | Monthly NDVI (Vegetation Health) | Terra / MODIS | 0.05° · Monthly (2000–present) | `10.5067/MODIS/MOD13C2.061` |
| `GPM_3IMERGM` | Monthly Precipitation | GPM / IMERG | 0.1° · Monthly (2000–present) | `10.5067/GPM/IMERG/3B-MONTH/07` |
| `OMNO2d` | Tropospheric NO₂ Column | Aura / OMI | 0.25° · Daily aggregated to Monthly (2004–present) | `10.5067/Aura/OMI/DATA3007` |
| `MOD11C3` | Monthly Land Surface Temperature | Terra / MODIS | 0.05° · Monthly (2000–present) | `10.5067/MODIS/MOD11C3.061` |

### Model / Reanalysis (via NASA POWER / MERRA-2)
- `T2M` (2m Air Temperature, °C), `PRECTOTCORR` (Corrected Precipitation, mm/day), `GWETROOT` (Root-Zone Soil Wetness), `GWETPROF` (Profile Soil Moisture), `QV2M` (Specific Humidity, g/kg), `PS` (Surface Pressure, kPa).
- Citation: NASA POWER / MERRA-2 (`10.5067/QBZ6MG944HW0`).

---

## 3. Statistical & Spatial Methodology

- **STL Seasonal Decomposition**: Cleveland et al. (1990), period = 12 months.
- **Mann-Kendall Non-Parametric Trend Test**: Mann (1945) & Kendall (1975).
- **Autocorrelation-Adjusted Mann-Kendall**: Hamed & Rao (1998), *Journal of Hydrology*, 204(1–4), 182–196.
- **Seasonal Mann-Kendall Test**: Hirsch, Slack & Smith (1982), *Water Resources Research*, 18(1), 107–121, across India's 4 IMD seasons (`DJF`, `MAM`, `JJAS`, `ON`).
- **Theil-Sen Slope & 95% Confidence Interval**: Sen (1968), *JASA*, 63(324), 1379–1389.
- **Multiple-Testing Control (India Choropleth)**: Benjamini & Hochberg (1995) False Discovery Rate (`q < 0.05`).
- **Polygon Masking & Area Weighting**: Point-in-polygon masking over 36 Indian states/UTs and 753 districts with `cos(latitude)` grid-cell area weighting.

---

## 4. Running Locally

### Backend (FastAPI)
```bash
cd backend
pip install -r requirements.txt
# Set environment variables in your shell or deployment platform (never commit .env):
# EARTHDATA_TOKEN=...  (or EARTHDATA_USERNAME / EARTHDATA_PASSWORD)
# GEMINI_API_KEY=...   (optional, for AI brief & variable suggestions)
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### Frontend (React + TypeScript + Vite)
```bash
cd frontend
npm install
npm run dev
```

### Tests
```bash
python -m pytest -v backend/tests/
cd frontend && npm run build
```

---

## 5. Documentation

Detailed technical audits, dataset catalogues, Earthdata setup, and validation reports are organized under `docs/`.
