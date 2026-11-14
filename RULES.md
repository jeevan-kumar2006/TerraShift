# TerraShift — Global Project Rules & Contracts

## 1. Architecture (8 Core Files)
- `RULES.md` — Global rules, API schema contract, and statistical guardrails
- `backend/main.py` — FastAPI API router (`/api/health`, `/api/cases`, `/api/parameters`, `/api/analyze`, `/api/investigate`, `/api/explain`)
- `backend/stats_engine.py` — STL seasonal decomposition, Mann-Kendall, Sen's slope, OLS Student's t-test, time-to-significance horizon, Pearson cross-correlation
- `backend/nasa_service.py` — NASA POWER monthly API client, parameter metadata registry, local JSON cache & nearest-point offline fallback
- `backend/cases_cache.json` — 4 seeded multi-mission Detective Case Files + cached live responses
- `frontend/src/App.tsx` — State orchestration & Earth Detective Control Bar
- `frontend/src/SplitMap.tsx` — Interactive dual-region Leaflet map & teleconnection view
- `frontend/src/TrendLab.tsx` — Raw / Deseasonalized / Teleconnection chart switcher & Verdict Scorecard
- `frontend/src/DossierModal.tsx` — AI / physical synthesis brief & 1-page printable PDF Field Dossier

## 2. Deterministic Statistical & API Rules
1. **Seasonal Decomposition First**: All trend significance evaluations MUST run on the deseasonalized anomaly series (`raw - seasonal_cycle`, centered at 0), never on raw seasonal data.
2. **Required Series Arrays**: Every analysis response MUST include `timestamps`, `raw_values`, `seasonal_cycle`, `deseasonalized_anomalies`, `trend_line`, `ci_upper`, and `ci_lower`.
3. **Required Statistical Metrics**: Every response MUST return `mann_kendall_tau`, `z_score`, `p_value`, `t_test_p_value`, `is_significant` (`p_value < 0.05` two-sided), `sens_slope_per_year`, `sens_slope_per_decade`, `years_to_significance`, `raw_p_value`, and `variance_reduction_pct`.
4. **Snake Case JSON Contract**: All backend-to-frontend JSON keys follow snake_case matching PRD Section 6 (`metadata`, `primary_series`, `primary_stats`, `teleconnection`, `detective_brief`).
5. **Hybrid Cache & Offline Resilience**: Every successful live NASA POWER API response MUST be persisted atomically to `backend/cases_cache.json` under `live_cache`. If NASA POWER is unreachable, `nasa_service.py` falls back to the nearest cached coordinate for that parameter.
6. **File Hygiene**: Only modify files explicitly scoped to the current sprint/task.
