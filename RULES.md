# TerraShift — Project Rules, Architecture & API Contracts

This document specifies the scientific contracts, core architectural responsibilities, API schemas, and statistical constraints governing the **TerraShift** codebase.

---

## 1. System Architecture & Core Modules

### Backend Modules (`backend/`)
- **`config.py`**: Central repository for all application constants (India bounding box `[6.0°N, 37.5°N, 68.0°E, 97.5°E]`, physical units, dataset identifiers, significance threshold $\alpha = 0.05$, API base URLs). **No scattered constants allowed.**
- **`main.py`**: Primary FastAPI application router exposing all REST endpoints (`/api/health`, `/api/parameters`, `/api/investigate`, `/api/trend-map`, `/api/import-series`, `/api/partner-intel`, `/api/explain`, `/api/suggest-variables`).
- **`stats_engine.py`**: Deterministic statistical core:
  - STL decomposition (LOESS smoothing, $T=12$ monthly cycle).
  - Mann-Kendall rank trend test with Hamed & Rao (1998) autocorrelation variance correction.
  - Seasonal Mann-Kendall (Hirsch et al., 1982) for IMD seasons (`DJF`, `MAM`, `JJAS`, `ON`).
  - Theil-Sen estimator for slope and non-parametric 95% confidence intervals.
  - Student's t-test on linear regression residuals.
  - Estimated Additional Observation Period ($N_{\text{needed}}$) for non-significant trends.
- **`satellite_service.py`**: NASA Earthdata client handling Level-3 gridded satellite datasets (`MOD13C2`, `GPM_3IMERGM`, `OMNO2d`, `MOD11C3`). Applies QA flags, scale factors, fill values, and disk caching.
- **`nasa_service.py`**: NASA POWER / MERRA-2 API client for meteorology and soil-moisture parameters. Implements caching and bounded nearest-coordinate fallback.
- **`india_analytics.py`**: Spatial analytics module handling 36 States/UTs and 753 Districts. Performs point-in-polygon raster masking with $\cos(\text{latitude})$ spherical area-weighting and terrain quality flags.
- **`trend_map_service.py`**: Orchestrates regional trend calculations across India and applies the Benjamini-Hochberg (1995) False Discovery Rate (FDR) procedure.
- **`ai_explainer.py`**: Physical reasoning engine combining deterministic rule-based synthesis with optional Gemini LLM grounding strictly restricted to verified computed statistics.

### Frontend Modules (`frontend/src/`)
- **`App.tsx`**: Central application state, top-level routing, and telemetry synchronization.
- **`HomePage.tsx`**: Landing experience with orbital observatory aesthetic, live telemetry monitor, and interactive feature showcases.
- **`ScrollTextOverlay.tsx`**: Scroll-driven overlay component with 0.5x speed background word drifting and 0.9x–1.1x foreground parallax scaling.
- **`IndiaRegionalView.tsx`**: All-India choropleth map with interactive region selection, FDR significance display, and computed opposite trend rankings.
- **`SplitMap.tsx`**: Dual-region comparative spatial view rendering current Survey of India geometries.
- **`TrendLab.tsx`**: Time-series visualization laboratory displaying raw vs. deseasonalized trends, confidence bands, seasonal cycles, and sensor provenance.
- **`DataAcquisitionView.tsx`**: Direct Earthdata download helper and Giovanni/AppEEARS CSV ingestion pipeline connected directly to the analysis engine via "Analyse this data".
- **`GuidedTour.tsx`**: Interactive multi-step walkthrough engine driven by live backend calculations, supporting URL parameter deep-linking (`?tour=<tour-id>`).
- **`DossierModal.tsx`**: Single-page printable PDF field dossier and standalone JSON exporter.

---

## 2. Non-Negotiable Scientific & Coding Rules

1. **Zero Hardcoded Analytical Values**:
   - Every slope, p-value, z-score, confidence interval, verdict, map legend range, and regional ranking must be calculated from real observations at runtime.
   - Mocking or placeholder figures are strictly forbidden in production code and API responses (test fixtures permitted only within `tests/`).
2. **Deseasonalization Prior to Trend Analysis**:
   - All trend evaluations must run on deseasonalized anomaly series (`raw - seasonal_cycle`), centered at zero, to eliminate false positive conclusions induced by the Indian monsoon.
3. **India-Exclusive Geographic Boundary**:
   - All map viewpoints, presets, regional masks, and default coordinates must reside strictly within the Republic of India boundaries (`[6.0°N, 37.5°N, 68.0°E, 97.5°E]`).
   - Default fallback coordinates must point to Indian locations (e.g., New Delhi: `28.61°N, 77.21°E`).
4. **Current Survey of India Geometries**:
   - State layer must accurately represent 28 States + 8 Union Territories (including merged Dadra & Nagar Haveli and Daman & Diu, Ladakh UT, and Jammu & Kashmir UT).
   - District layer must contain all 753 active districts properly linked to their parent state/UT.
5. **Satellite vs. Model Transparency**:
   - Data provenance must explicitly label the source as `Satellite: <Mission/Instrument>` or `Model: <System>` on all chart widgets, tooltips, and exported dossiers.
6. **Explicit Uncertainty Reporting**:
   - Insignificant trends (`p >= 0.05`) must never be described as conclusive. The UI must state the statistical power and display the estimated additional observation years needed.
7. **Environment Variable Security**:
   - Never commit or modify `.env` files. Access secrets (`EARTHDATA_TOKEN`, `GEMINI_API_KEY`) strictly from system environment variables at runtime.

---

## 3. API Contract Specifications

### `POST /api/investigate`
Accepts either a single geographic point or a regional polygon identifier.
```json
// Point Mode Request:
{
  "variable": "MOD13C2",
  "primary_point": { "lat": 26.91, "lon": 75.78, "name": "Jaipur" },
  "date_range": ["2000-01-01", "2024-12-31"],
  "season": "ALL"
}

// Region Mode Request:
{
  "variable": "GPM_3IMERGM",
  "region_type": "state",
  "region_id": "IN-RJ",
  "date_range": ["2001-01-01", "2024-12-31"],
  "season": "JJAS"
}
```

**Response Contract (`InvestigateResponse`):**
```json
{
  "metadata": {
    "variable": "string",
    "dataset_id": "string",
    "source_type": "satellite" | "model/reanalysis",
    "mission": "string",
    "units": "string",
    "doi": "string"
  },
  "spatial_summary": {
    "grid_cells_used": 42,
    "area_coverage_pct": 98.4,
    "quality_flags": []
  },
  "primary_series": {
    "timestamps": ["YYYY-MM"],
    "raw_values": [0.0],
    "seasonal_cycle": [0.0],
    "deseasonalized_anomalies": [0.0],
    "trend_line": [0.0],
    "ci_upper": [0.0],
    "ci_lower": [0.0]
  },
  "primary_stats": {
    "mann_kendall_tau": 0.0,
    "p_value": 0.0,
    "p_value_corrected": 0.0,
    "is_significant": true,
    "sens_slope_per_year": 0.0,
    "sens_slope_per_decade": 0.0,
    "ci_95_lower": 0.0,
    "ci_95_upper": 0.0,
    "years_to_significance": 0.0,
    "variance_reduction_pct": 0.0
  }
}
```

### `GET /api/trend-map`
Computes all-India regional trends with Benjamini-Hochberg FDR correction.
- **Query Parameters**: `variable` (string), `level` (`state` | `district`), `start` (YYYY-MM), `end` (YYYY-MM), `season` (`ALL` | `DJF` | `MAM` | `JJAS` | `ON`).
- **Response**: List of regions with slopes, raw p-values, corrected p-values (`fdr_significant`), computed robust symmetric color bounds, and ranked positive/negative opposite trend regions.
