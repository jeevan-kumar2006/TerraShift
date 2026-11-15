# Priority Fixes

1. **P1 — Bound and protect compute/download endpoints.** Add FastAPI body/sample limits, rate limiting and authenticated acquisition/Gemini access. Replace in-process heavy work with bounded jobs. Regression: oversized payload -> 413/422; unauthenticated acquisition -> 401/403; queue concurrency test.
2. **P1 — Complete or hide CDS download.** The current endpoint returns a readiness message rather than acquiring data. Wire the existing client into the validation/QC/subset pipeline and test it with a mock.
3. **P1 — Replace ephemeral CSV persistence.** Object storage plus a transactional metadata service, or clearly label acquisition as single-instance demo-only. Test parallel writes and restart persistence.
4. **P2 — Release hardening.** Set production environment, define API URL at build/deploy, add error tracking and a revision endpoint.
5. **P2 — Scientific provenance.** Persist source URL/product/version/retrieval timestamp/spatial operation and make it exportable; add independent golden data and serial-correlation tests.
6. **P2 — Browser regression suite.** Add Playwright workflow, back/forward/modal test, map selection, import, error states and mobile layouts.

Fix status: none changed by this read-only audit. Regression status: existing backend suite passes; new regressions are not yet implemented.
