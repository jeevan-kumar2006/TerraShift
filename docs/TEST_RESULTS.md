# Test Results

## Executed

| Test | Outcome |
|---|---|
| `python -m pytest -q backend/tests` | 30 passed, 0 failed, 0 skipped (12.02 s) |
| `npm run build` | passed (Vite 6.4.6; chunk-size warning) |
| Local `GET /api/health`, `/api/cases`, CORS OPTIONS | passed |
| Live frontend root | passed: HTTP 200, title `TerraShift — NASA Earth System Trend Detective` |
| Live backend health/status/cases | passed |
| Live invalid investigate body | passed: structured 422 validation response |
| Live valid Delhi investigation | passed: cached NASA POWER/MERRA-2 response, 300 monthly values |

## Unverified / not run

- Browser E2E controls, console/network errors, screenshots, mobile/cross-browser layouts and accessibility: browser host unavailable.
- Upstream NASA/CMR/AppEEARS/NOAA/KNMI/CSA success/failure/rate-limit behavior.
- Authenticated Earthdata and CDS downloads: no credentials used; CDS endpoint is incomplete.
- Load/concurrency/large payload tests: not run against public production to avoid resource abuse.

No test was fabricated. See `TECHNICAL_AUDIT.md` for exact observed results.
