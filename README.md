# TerraShift — India Earth System Trend Detective

**TerraShift** is an India-exclusive Earth observation trend analysis platform engineered for the **NASA Space Apps 2026 Challenge: Earth System Trend Detective**. It rigorously separates long-term climate and environmental signals from intense monsoonal seasonality across India's **36 States & Union Territories**, **753 Districts**, and **10 Physiographic Regions**.

---

## 1. System Architecture

TerraShift is built as a decoupled, type-safe full-stack application connecting NASA Earth observation archives with a deterministic statistical engine and an interactive React geospatial frontend.

```
                              ┌────────────────────────────────────────────────────────┐
                              │            NASA Earth Observation Archives             │
                              │  • NASA Earthdata / CMR / OPeNDAP (MODIS, GPM, OMI)    │
                              │  • NASA POWER / MERRA-2 (Meteorology & Soil Moisture)  │
                              └───────────────┬────────────────────────┬───────────────┘
                                              │                        │
                                      Satellite NetCDF/HDF       POWER JSON API
                                              │                        │
                                              ▼                        ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                              FASTAPI BACKEND ARCHITECTURE                            │
│                                                                                      │
│   ┌──────────────────────────┐    ┌─────────────────────────┐   ┌────────────────┐   │
│   │   satellite_service.py   │    │     nasa_service.py     │   │   config.py    │   │
│   │  MOD13C2, GPM, OMNO2d,   │    │  POWER API client,      │   │  All constants,│   │
│   │  MOD11C3 caching & masks │    │  bounded point fallback │   │  bounds, alpha │   │
│   └────────────┬─────────────┘    └────────────┬────────────┘   └───────┬────────┘   │
│                │                               │                        │            │
│                └───────────────────────┬───────┴────────────────────────┘            │
│                                        ▼                                             │
│                           ┌──────────────────────────┐                               │
│                           │    india_analytics.py    │                               │
│                           │  Point-in-polygon masks  │                               │
│                           │  cos(lat) area weighting │                               │
│                           │  36 States / 753 Dist.   │                               │
│                           └────────────┬─────────────┘                               │
│                                        ▼                                             │
│                           ┌──────────────────────────┐                               │
│                           │     stats_engine.py      │                               │
│                           │  • STL Decomposition     │                               │
│                           │  • Mann-Kendall          │                               │
│                           │  • Hamed-Rao Correction  │                               │
│                           │  • Sen's Slope & 95% CI  │                               │
│                           │  • Years to Significance │                               │
│                           │  • Holm-Bonferroni       │                               │
│                           └────────────┬─────────────┘                               │
│                                        ▼                                             │
│       ┌────────────────────────┬───────┴─────────────────────────┐                   │
│       ▼                        ▼                                 ▼                   │
│ ┌───────────────┐     ┌──────────────────┐             ┌───────────────────┐         │
│ │    main.py    │     │ trend_map_service│             │  ai_explainer.py  │         │
│ │ FastAPI APIs  │     │ India Choropleth │             │  Physical brief & │         │
│ │ /investigate  │     │ FDR (BH-95) Corr │             │  Gemini grounding │         │
│ └───────┬───────┘     └────────┬─────────┘             └─────────┬─────────┘         │
└─────────┼──────────────────────┼─────────────────────────────────┼───────────────────┘
          │                      │ JSON Responses                  │
          ▼                      ▼                                 ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                             REACT + TYPESCRIPT FRONTEND                              │
│                                                                                      │
│   ┌──────────────────────────────────────────────────────────────────────────────┐   │
│   │ App.tsx: State orchestration, navigation, telemetry hub, dataset acquisition │   │
│   └──────────────────────┬───────────────────────────────────────────────────────┘   │
│                          │                                                           │
│        ┌─────────────────┼──────────────────────────┬────────────────────────┐       │
│        ▼                 ▼                          ▼                        ▼       │
│ ┌──────────────┐  ┌──────────────┐           ┌──────────────┐         ┌───────────┐  │
│ │ HomePage.tsx │  │ SplitMap.tsx │           │ IndiaRegional│         │ TrendLab  │  │
│ │ • Hero Glow  │  │ • Dual Leaflet           │   View.tsx   │         │ • STL De- │  │
│ │ • Scroll-    │  │   Interactive│           │ • All-India  │         │   comp    │  │
│ │   Driven Text│  │   Region Map │           │   Choropleth │         │ • Sen's CI│  │
│ │   Overlay    │  │ • Survey of  │           │ • Benjamini- │         │ • Score-  │  │
│ │ • India      │  │   India      │           │   Hochberg   │         │   card    │  │
│ │   Default    │  │   Boundaries │           │   FDR map    │         │ • Proven- │  │
│ │   Readouts   │  │              │           │ • Opposites  │         │   ance    │  │
│ └──────────────┘  └──────────────┘           └──────────────┘         └───────────┘  │
│                          │                                                           │
│        ┌─────────────────┴──────────────────────────┬────────────────────────┐       │
│        ▼                                            ▼                        ▼       │
│ ┌──────────────┐                             ┌──────────────┐         ┌───────────┐  │
│ │ GuidedTour   │                             │ DataAcquisit-│         │ Dossier-  │  │
│ │ • Auto-play  │                             │   ionView    │         │ Modal     │  │
│ │ • Step flow  │                             │ • Earthdata  │         │ • 1-page  │  │
│ │ • Real stats │                             │ • CSV upload │         │   PDF     │  │
│ │ • URL deep-  │                             │ • "Analyse"  │         │ • JSON    │  │
│ │   link ?tour=│                             │   handoff    │         │   export  │  │
│ └──────────────┘                             └──────────────┘         └───────────┘  │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Scientific Problem & Core Tenets

Raw monthly satellite and meteorological records over the Indian subcontinent are heavily masked by monsoon cycles (DJF, MAM, JJAS, ON). TerraShift prevents false-positive trend detection through non-negotiable scientific constraints:

1. **Zero Hardcoded Data**: Slopes, p-values, trend directions, confidence intervals, map color scales, and regional metrics are computed dynamically at runtime from real NASA observations or validated user-imported series.
2. **Explicit Uncertainty & Power**: Insignificant trends (`p >= 0.05`) are never framed as conclusive. TerraShift calculates the *Estimated Additional Observation Period (years)* required to detect a true signal given the empirical noise structure.
3. **Sensor Provenance & Satellite vs. Model Integrity**: Satellite observations (`MODIS Terra`, `GPM IMERG`, `Aura OMI`) are strictly distinguished from reanalysis models (`NASA POWER / MERRA-2`) via dedicated badges, quality-control flags (QA masks, cloud fraction), and DOIs.
4. **Current Survey of India Geographic Integrity**: 28 States + 8 Union Territories (including merged Dadra & Nagar Haveli and Daman & Diu, Ladakh UT, and Jammu & Kashmir UT) and all 753 current districts with complete parent state attribution.

---

## 3. Supported Datasets & DOIs

### Direct Satellite Missions (via NASA Earthdata / CMR / OPeNDAP)
| ID | Variable | Mission / Instrument | Spatial / Temporal Resolution | Official DOI |
| --- | --- | --- | --- | --- |
| `MOD13C2` | Monthly NDVI (Vegetation Greenness) | Terra / MODIS | 0.05° × 0.05° · Monthly (2000–present) | `10.5067/MODIS/MOD13C2.061` |
| `GPM_3IMERGM` | Monthly Precipitation (Rainfall) | GPM / IMERG | 0.1° × 0.1° · Monthly (2000–present) | `10.5067/GPM/IMERG/3B-MONTH/07` |
| `OMNO2d` | Tropospheric NO₂ Column Density | Aura / OMI | 0.25° × 0.25° · Daily aggregated Monthly (2004–present) | `10.5067/Aura/OMI/DATA3007` |
| `MOD11C3` | Land Surface Temperature (Day/Night) | Terra / MODIS | 0.05° × 0.05° · Monthly (2000–present) | `10.5067/MODIS/MOD11C3.061` |

### Model / Reanalysis (via NASA POWER / MERRA-2)
- `T2M` (2m Air Temperature, °C), `PRECTOTCORR` (Precipitation, mm/day), `GWETROOT` (Root-Zone Soil Wetness), `GWETPROF` (Profile Soil Wetness), `QV2M` (Specific Humidity, g/kg), `PS` (Surface Pressure, kPa).
- DOI: `10.5067/QBZ6MG944HW0`.

---

## 4. Statistical & Spatial Methodology

- **STL Seasonal Decomposition**: Loess-based seasonal decomposition separating seasonal oscillation ($T = 12$) from trend and residual noise.
- **Autocorrelation-Adjusted Mann-Kendall**: Hamed & Rao (1998) variance-corrected test accounting for lag-1 to lag-$k$ autocorrelation in geophysical series.
- **Theil-Sen Robust Slope & 95% CI**: Median of all pairwise slopes, resilient against extreme weather outliers and sensor gaps.
- **Seasonal Mann-Kendall**: Hirsch, Slack & Smith (1982) evaluation across India's seasonal windows:
  - `DJF` (Winter: Dec–Feb)
  - `MAM` (Pre-monsoon / Summer: Mar–May)
  - `JJAS` (Southwest Monsoon: Jun–Sep)
  - `ON` (Post-monsoon / Northeast Monsoon: Oct–Nov)
- **Benjamini-Hochberg False Discovery Rate (FDR)**: Applied across all 36 states and 753 districts in the India Trend Choropleth (`/api/trend-map`) to control for false discovery in spatial multiple hypothesis testing.
- **Spherical Area Weighting**: Polygons masked with shapely and weighted by $\cos(\text{latitude})$ per grid cell to ensure area-accurate spatial averages.

---

## 5. UI Features & Interactions

- **HomePage**: Orbital observatory styling, hero typography, live telemetry readout defaulting to New Delhi coordinates (`28.61°N / 77.21°E`), and an interactive **scroll-driven text overlay** with 0.5x drifting telemetry words and 0.9x–1.1x foreground scaling parallax.
- **India Choropleth & Opposite Trends**: Diverging color palette centered at zero, robust 95th-percentile range bounds, hatched non-significant regions, and auto-ranked opposing trend anomalies.
- **Guided Walkthrough Tours**: Interactive multi-step tours (`?tour=thar-greening`, `?tour=delhi-no2`, `?tour=ne-monsoon`) backed by real computation.
- **Data Acquisition Handoff**: Upload Giovanni/AppEEARS CSVs or validate Earthdata files and jump directly into the analysis pipeline via **"Analyse this data"**.
- **1-Page Field Dossier**: Print-ready PDF report and self-contained JSON dossier export with full provenance and analytical scorecard.

---

## 6. Getting Started

### Prerequisites
- Python 3.10+
- Node.js 18+ and npm

### Backend Setup
```bash
cd backend
pip install -r requirements.txt

# Run the FastAPI server
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```
*Optional environment variables (pass via shell or system environment, never commit `.env`):*
- `EARTHDATA_TOKEN` or `EARTHDATA_USERNAME` / `EARTHDATA_PASSWORD`
- `GEMINI_API_KEY` (optional for generative physical briefs)

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Open **`http://localhost:5173`** in your browser.

### Test Execution
```bash
# Backend unit & integration tests
python -m pytest -v backend/tests/

# Frontend typecheck & production build
cd frontend && npm run build
```
