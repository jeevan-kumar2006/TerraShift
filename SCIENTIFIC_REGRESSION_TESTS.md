# Scientific Regression Tests

## Test inventory

| Category | Tests/evidence |
|---|---|
| Provenance | Cached POWER header preservation; API serialization of source name, access endpoint, status, coordinates, and grid-cell note |
| Ingestion | Timestamp parsing, fill values, duplicate timestamps, short gaps, long-gap rejection |
| Regression | Known noisy trend, OLS/Sen slope outputs, confidence-band fields |
| Mann–Kendall | Standard and Hamed–Rao comparison with `pymannkendall` |
| Seasonality | Pure seasonal null case and strongly seasonal trend case |
| Missing data | Interpolation count, missing percentage, valid-month count |
| Autocorrelation | Hamed–Rao reference comparison and returned lag-1 diagnostic |
| Interpretation | Non-causal hypothesis wording and explicit limitations |
| Spatial/QC | Polygon masking, area weighting, QC sentinel/flag filtering, corrupt-file rejection |
| API | Health, investigation, import, acquisition, CORS, validation, provenance contracts |

## Reproducibility

Tests use deterministic arrays or fixed random seeds. Core mathematical tests do not require live NASA services. Live-provider checks are separate and document upstream availability.

## Current evidence

- `python -m pytest -q backend/tests`: **39 passed**
- `npm run build` in `frontend`: **passed**
- Live NASA POWER sample: **HTTP 200**

## CI

The repository does not currently expose a single top-level CI command. The reproducible commands above should be wired into CI before production deployment. Until then, a green local run is evidence of correctness for this revision, not a permanent enforcement mechanism.

