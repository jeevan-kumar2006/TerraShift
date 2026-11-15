# Scientific Validation

## Data provenance observed

A live API investigation for Delhi (28.6139, 77.2090), T2M, 2000–2024, Hamed-Rao completed on 2026-11-15 in 3.685 s. Response provenance identified **NASA POWER API v2.10.0 / MERRA-2 M2TMNXSLV**, `data_status: cache`, `dataset_tag: cached`, and `is_synthetic: false`; 300 monthly values were analyzed. It produced Sen slope -0.0364/year, p=0.024242. This confirms one working cached NASA-derived path, not that every UI/data-source path is live.

The code supports NASA POWER monthly data, CMR discovery, AppEEARS catalog lookup/import, NASA Giovanni/GES DISC formatted imports, NOAA, KNMI and CSA references. CMR/partner integrations were not independently exercised against upstream services in this audit. Cached fixture origin/age is not exposed with a retrieval timestamp sufficient for independent reproducibility.

## Pipeline reviewed

`source -> parser/cache -> complete monthly index -> <=3 month linear interpolation -> STL(period=12, robust) -> deseasonalized series -> Mann-Kendall/Sen/OLS -> chart/brief`.

## Mathematical assessment

- Monthly indexing, duplicate merging, invalid/sentinel rejection, short-gap handling and long-gap rejection are implemented in `stats_engine.py` and are covered by existing tests.
- Standard MK includes tie correction; Sen computes pairwise slopes and a rank-variance confidence interval. Existing tests compare MK/Hamed-Rao outputs with `pymannkendall`.
- STL is valid only when the input is monthly and seasonality is appropriate. The app should disclose that seasonal adjustment can be inappropriate for already seasonally adjusted or irregularly aggregated imports.
- Pearson teleconnection p-values assume independent paired observations. The code does not adjust correlation significance for serial dependence; do not describe these as causal teleconnections.
- OLS confidence bands explicitly assume independent, homoscedastic normal residuals. The app provides a lag-1 diagnostic and an optional Hamed-Rao MK variant, but OLS p-values and the “additional years” estimate do not use an effective sample size/autocorrelation-robust uncertainty estimate.
- Interpolation of up to three missing months can affect estimates; output flags it, but it should be visually prominent and configurable/disableable for scientific exports.

## Scientific limitations / required wording

Do not call cached/model-reanalysis values “satellite observations.” MERRA-2 is a reanalysis. Do not infer mechanism or causality from Pearson correlation or optional AI narrative. Label fallback/cached/imported/synthetic data at chart/export level, including source URL/product version, retrieval time, spatial aggregation and applied quality filters.

## Result

The core trend computations are **partially validated**, not fully scientifically validated for every claimed source/product or spatial workflow. Add independent golden-data tests (known slopes/CIs, AR(1) false-positive behavior, imported pre-adjusted series) and source-to-chart provenance tests.
