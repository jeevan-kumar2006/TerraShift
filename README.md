# TerraShift — Earth System Trend Detective

**TerraShift** is a multi-agency Earth observation trend-detection and regional comparison laboratory built with a FastAPI + React architecture. It enforces complete monthly indexing, strips strong seasonal cycles via **STL decomposition**, validates multi-decade climate shifts using **Mann-Kendall** (standard & Hamed-Rao), **Sen's slope** (with 95% CI), and **Student's t-tests**, computes **Estimated Additional Observation Periods**, and integrates **Mapbox / Leaflet**, **NASA POWER (MERRA-2 reanalysis & model-derived hydrology)**, **NASA CMR / AppEEARS discovery**, **NOAA CDO**, **KNMI**, and **CSA (Canadian Space Agency)** data and resources.

---

## 1. Architecture

```text
TerraShift/
├── RULES.md                  # Global schema, statistical, and caching guardrails
├── backend/
│   ├── main.py               # FastAPI endpoints (/api/health, /api/status, /api/cases, /api/investigate, /api/partner-intel, /api/import-series, /api/explain)
│   ├── stats_engine.py       # Monthly index + gap guard (<=3 mo), STL decomposition (period=12), Mann-Kendall, Sen's slope + 95% CI, OLS t-test, r
│   ├── nasa_service.py       # NASA POWER (RE/AG community routing), CMR/AppEEARS/CSA/NOAA discovery, provenance & bounded fallback (<=500 km), CSV/KNMI parser
│   ├── ai_explainer.py       # Modular deterministic & optional Gemini 2.5 Flash physical explanation engine (stats-grounded)
│   ├── cases_cache.json      # 6 seeded Detective Case Files + live coordinate cache
│   ├── requirements.txt
│   └── tests/
│       ├── test_stats.py           # Pytest suite for trends, Hamed-Rao, monthly indexing, provenance & importers
│       └── test_api_integration.py # Integration tests for CORS, validation, window slicing & health/status
└── frontend/
    └── src/
        ├── App.tsx           # State orchestration, 3-step workflow, Partner Telemetry Hub & Giovanni/KNMI CSV Importer
        ├── SplitMap.tsx      # Dual-region Mapbox (pk.* validated) / Leaflet OSM / Satellite / Terrain map + Reverse Geocoding
        ├── TrendLab.tsx      # Raw Monthly Data / Deseasonalized Trend Lab / Regional Anomaly Comparison, Provenance & Scorecard
        ├── DossierModal.tsx  # Physical mechanism synthesis, provenance/limitations, printable Field Dossier & JSON report export
        └── types.ts          # Shared TypeScript API & provenance contracts
```

---

## 2. Integrated Map & Space Agency APIs / Resources

- **Mapbox Map & Geocoding (`SplitMap.tsx`)**:
  - Supports **Mapbox Static Tiles API** (`mapbox/dark-v11`, `mapbox/satellite-streets-v12`, `mapbox/outdoors-v12`) and **Mapbox Reverse Geocoding v5** when `VITE_MAPBOX_TOKEN` is set or entered via the in-app **Mapbox Key** pill, with automatic fallback to CARTO Dark / Esri World Satellite / OpenTopoMap.
- **NASA Data & Resources**:
  - **NASA POWER Monthly API** (`power.larc.nasa.gov`) — Live zero-auth 1981–2025 monthly meteorology & soil hydrology.
  - **NASA CMR API** (`cmr.earthdata.nasa.gov`) — Live bounding-box satellite granule/collection matching for **SWOT**, **SeaWiFS**, **MODIS**, **GPM**, and **GLDAS**.
  - **NASA AppEEARS API** (`appeears.earthdatacloud.nasa.gov/api/v1/product`) — Live product catalog lookup + CSV time-series importer.
  - **NASA Giovanni & GES DISC Hydrology Time Series** — Coordinate-parameterized deep links + direct CSV/ASCII time-series importer (`POST /api/import-series`).
  - **NOAA Climate Data Online (CDO)** (`ncei.noaa.gov/cdo-web/api/v2`) — Station lookup (`NOAA_CDO_TOKEN`) + CSV importer.
  - **SeaWiFS Coastal Chlorophyll Reference** ([NASA NTRS 20090042747](https://ntrs.nasa.gov/api/citations/20090042747/downloads/20090042747.pdf)) — Grounded in Case 5 & methodology citations.
- **Space Agency Partner & Statistical Resources**:
  - **KNMI Climate Explorer** (`climexp.knmi.nl`) — Native 13-column `.dat` / `.txt` table parser in `POST /api/import-series` + portal links.
  - **Statistical Methodology Guides** — Embedded references to Mann-Kendall/Sen's slope trend detection ([Medium](https://medium.com/@snp.kriss/statistical-test-methods-to-detect-trends-in-time-series-data-b361a0ec530b)) and statistical significance ([Statsig](https://www.statsig.com/perspectives/a-comprehensive-guide-to-statistical-significance)).
- **CSA (Canadian Space Agency)**:
  - **Geo.ca / MSC GeoMet Open API** (`api.weather.gc.ca`) — Live zero-auth queries for Canadian monthly climate (`climate-monthly`) and hydrometric river/lake water-level & discharge (`hydrometric-monthly-mean`) stations.
  - **RADARSAT Constellation Mission (RCM)**, **SWOT Mission**, **CSA Ecosystem Monitoring**, and **CSA SAR Python Tutorial** integrated in Case 6 and the Partner Hub.

---

## 3. Curated Detective Case Files (Pre-Seeded in `cases_cache.json`)
1. **Case 1 — ENSO Rainfall Seesaw (`PRECTOTCORR`)**: Northern Peru Coast vs. East Kalimantan, Indonesia.
2. **Case 2 — North American Hydrological Dipole (`GWETROOT`)**: US Southwest / Colorado Basin drying vs. Upper Midwest wetting.
3. **Case 3 — Polar Amplification vs. Atlantic Cold Blob (`T2M`)**: Svalbard Archipelago rapid warming vs. Subpolar North Atlantic.
4. **Case 4 — Amazon Canopy Moisture Stress (`GWETPROF`)**: Southeastern Amazon Deforestation Arc vs. Central Amazon Core.
5. **Case 5 — SeaWiFS Coastal Plume Runoff Seesaw (`PRECTOTCORR`)**: Mississippi River Delta Plume vs. Offshore Gulf Loop Current (NASA NTRS `20090042747`).
6. **Case 6 — CSA SWOT & RCM Canadian Cryosphere/Water Shift (`T2M`)**: Mackenzie Delta / Beaufort Coast vs. Great Lakes / St. Lawrence Corridor.

---

## 4. Quick Start

```bash
# 1. Backend (FastAPI on :8000)
pip install -r backend/requirements.txt
python -m pytest -v backend/tests/test_stats.py backend/tests/test_api_integration.py
cd backend
python -m uvicorn main:app --reload --port 8000

# 2. Frontend (Vite on :5173)
cd frontend
npm install
npm run dev
```
