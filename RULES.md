# TerraShift — Global Project Rules & Contracts

## 1. Architecture (Core Files)
- `RULES.md` — Global rules, API schema contract, and statistical guardrails
- `backend/main.py` — FastAPI API router (`/api/health`, `/api/status`, `/api/cases`, `/api/parameters`, `/api/analyze`, `/api/investigate`, `/api/import-series`, `/api/partner-intel`, `/api/explain`)
- `backend/stats_engine.py` — Complete monthly indexing, STL seasonal decomposition, Mann-Kendall (standard & Hamed-Rao), Sen's slope with 95% CI, OLS Student's t-test, Estimated Additional Observation Period, Pearson cross-correlation
- `backend/nasa_service.py` — NASA POWER monthly API client (`RE`/`AG` community routing), parameter metadata & provenance builder, local JSON cache & bounded (`<= 500 km`) nearest-point fallback
- `backend/ai_explainer.py` — Modular physical explanation engine (deterministic baseline + optional Gemini 2.5 Flash grounded strictly in computed stats)
- `backend/cases_cache.json` — 6 seeded Detective Case Files + cached live responses
- `frontend/src/App.tsx` — State orchestration, 3-step workflow guide, Partner Telemetry Hub & Giovanni/KNMI CSV Importer
- `frontend/src/SplitMap.tsx` — Interactive dual-region Leaflet/Mapbox map & regional comparison view
- `frontend/src/TrendLab.tsx` — Raw Monthly Data / Deseasonalized Trend Lab / Regional Anomaly Comparison switcher, Dataset Provenance & Data-Quality panel & Scorecard
- `frontend/src/DossierModal.tsx` — AI / physical synthesis brief, provenance/limitations & 1-page printable PDF Field Dossier + self-contained JSON export

## 2. Deterministic Statistical & API Rules
1. **Seasonal Decomposition First**: All trend significance evaluations MUST run on the deseasonalized anomaly series (`raw - seasonal_cycle`, centered at 0), never on raw seasonal data.
2. **Required Series Arrays**: Every analysis response MUST include `timestamps`, `raw_values`, `seasonal_cycle`, `deseasonalized_anomalies`, `trend_line`, `ci_upper`, and `ci_lower`.
3. **Required Statistical Metrics**: Every response MUST return `mann_kendall_tau`, `z_score`, `p_value`, `t_test_p_value`, `is_significant` (`p_value < 0.05` two-sided), `sens_slope_per_year`, `sens_slope_per_decade`, `years_to_significance`, `raw_p_value`, and `variance_reduction_pct`.
4. **Snake Case JSON Contract**: All backend-to-frontend JSON keys follow snake_case matching PRD Section 6 (`metadata`, `primary_series`, `primary_stats`, `teleconnection`, `detective_brief`).
5. **Hybrid Cache & Offline Resilience**: Every successful live NASA POWER API response MUST be persisted atomically to `backend/cases_cache.json` under `live_cache`. If NASA POWER is unreachable, `nasa_service.py` falls back to the nearest cached coordinate for that parameter.
6. **File Hygiene**: Only modify files explicitly scoped to the current sprint/task.
