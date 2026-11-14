# TerraShift — Earth System Trend Detective

**TerraShift** is a NASA Earth observation trend-detection and teleconnection laboratory built with an 8-file FastAPI + React vertical architecture. It strips strong seasonal cycles via **STL decomposition**, validates multi-decade climate shifts using **Mann-Kendall**, **Sen's slope**, and **Student's t-tests**, computes **Time-to-Significance horizons** when short observation windows are inconclusive, and connects live to the zero-auth **NASA POWER Monthly API** with instant local JSON caching and offline fallback.

---

## 1. Architecture

```text
TerraShift/
├── RULES.md                  # Global schema, statistical, and caching guardrails
├── backend/
│   ├── main.py               # FastAPI endpoints (/api/cases, /api/investigate, /api/analyze, /api/explain)
│   ├── stats_engine.py       # STL decomposition (period=12), Mann-Kendall, Sen's slope, OLS t-test, r
│   ├── nasa_service.py       # Live NASA POWER fetcher, metadata registry, atomic JSON cache & fallback
│   ├── cases_cache.json      # 4 seeded Detective Case Files + live coordinate cache
│   ├── requirements.txt
│   └── tests/test_stats.py   # Pytest suite for synthetic trends, API endpoints & offline fallback
└── frontend/
    └── src/
        ├── App.tsx           # State orchestration & Guided Earth Detective Control Bar
        ├── SplitMap.tsx      # Dual-region Leaflet map (Marker A / B) & MERRA-2 grid bounding boxes
        ├── TrendLab.tsx      # Raw / Deseasonalized / Teleconnection chart switcher, window slider & Scorecard
        ├── DossierModal.tsx  # Physical mechanism synthesis & 1-page printable PDF Field Dossier
        └── types.ts          # Shared TypeScript API contracts
```

---

## 2. Quick Start

### Backend (FastAPI on port 8000)
```bash
pip install -r backend/requirements.txt
# Optional: re-seed the 4 preset Detective Case Files from live NASA POWER
python backend/nasa_service.py --seed

# Run automated tests
python -m pytest -v backend/tests/test_stats.py

# Start backend server
cd backend
uvicorn main:app --reload --port 8000
```

> **Optional AI Grounding**: Set `GEMINI_API_KEY` in your environment to enhance `/api/explain` briefs with Gemini 2.5 Flash. When unset or unreachable, TerraShift automatically uses its built-in NASA physics synthesis templates so demonstrations never depend on an API key.

### Frontend (Vite + React + Tailwind on port 5173)
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173` (Vite proxies `/api/*` directly to `http://127.0.0.1:8000`).

---

## 3. Curated Detective Case Files (Pre-Seeded from NASA POWER)
1. **Case 1 — ENSO Rainfall Seesaw (`PRECTOTCORR`)**: Northern Peru Coast vs. East Kalimantan, Indonesia.
2. **Case 2 — North American Hydrological Dipole (`GWETROOT`)**: US Southwest / Colorado Basin drying vs. Upper Midwest wetting.
3. **Case 3 — Polar Amplification vs. Atlantic Cold Blob (`T2M`)**: Svalbard Archipelago rapid warming vs. Subpolar North Atlantic.
4. **Case 4 — Amazon Canopy Moisture Stress (`GWETPROF`)**: Southeastern Amazon Deforestation Arc drying twice as fast as the Central Amazon Core.

---

## 4. Recommended Demo Walkthrough
1. Start on **Case 3 (Arctic Amplification)** in **`1. Raw Satellite Series`** mode to show how large winter-to-summer swings mask long-term warming (`raw_p_value` vs `p_value`).
2. Click **`Strip Seasonal Cycle (STL) →`** to reveal the deseasonalized anomaly slope (`+0.83 °C/decade`) and 95% confidence band.
3. Click **`5-Yr Test (2018–2022)`** on the Observation Window bar to turn the Verdict Scorecard amber (*Not Yet Significant — Needs ~18 More Years*), then click **`35-Yr Baseline (1990–2025)`** to flip it green (*Statistically Significant Trend*).
4. Switch to **`3. Teleconnection Overlay`** or load **Case 2 (Hydrological Dipole)** to show statistically significant opposite regional slopes (`drying` vs `wetting`).
5. Click **`Field Dossier (PDF)`** and **`Print / Save 1-Page PDF`** for a formatted single-page report.
