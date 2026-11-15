# Statistical Validation Report

## Production methods

`backend/stats_engine.py` performs:

1. monthly index completion and short-gap interpolation;
2. robust STL decomposition with period 12;
3. Mann–Kendall with tie correction;
4. optional Hamed–Rao rank-autocorrelation variance adjustment;
5. Theil–Sen pairwise median slope and Kendall-order confidence interval;
6. OLS slope and two-sided Student t confidence band;
7. Pearson correlation on aligned deseasonalized anomalies.

Rates are converted from monthly index units to per-year and per-decade units after the monthly contract is enforced.

## Independent checks

The regression suite compares production values to `pymannkendall` rather than calling the production implementation twice:

- standard Mann–Kendall: S/tau/z/p match within `1e-6`;
- Hamed–Rao modification: tau/z/p match within `1e-6`;
- pure seasonal series: variance reduction exceeds 95%, no significant trend, near-zero Sen slope;
- noisy known trend: slope and significance remain within controlled tolerances;
- constant, missing, duplicate, long-gap, and insufficient-length cases are covered.

## Reference cases

| Case | Expected | Result |
|---|---|---|
| Strong seasonal trend | Seasonal variance removed; positive trend retained | PASS |
| Five-year weak trend | Insufficient evidence is retained | PASS |
| Pure noise | No significant trend | PASS |
| Pure annual seasonality | No false monotonic trend | PASS |
| Increasing noisy reference | Matches independent MK implementation | PASS |
| Hamed–Rao autocorrelated reference | Matches independent implementation | PASS |
| Constant series with fill value | Flat result; fill value interpolated and documented | PASS |
| Long missing gap | Analysis rejected | PASS |

## Assumptions and limitations

- The regular monthly index is deliberate. Irregular input timestamps are expanded to monthly periods; missing interior months are interpolated only up to three consecutive months.
- OLS confidence bands describe statistical uncertainty of the fitted mean response under independent, homoscedastic residual assumptions. They do not include measurement, model, spatial-representativeness, or structural uncertainty.
- Hamed–Rao is available as an explicit method choice; the default remains standard Mann–Kendall for backward compatibility. Autocorrelation diagnostics are returned so users can choose the modified method.
- Pearson correlation is descriptive co-variation of aligned anomalies. It is not a teleconnection proof or causal test.
- Multiple comparisons across repeated user-selected analyses are not globally corrected. India seasonal analysis applies Holm correction across its four seasons only.

## Verdict

The tested mathematical components are independently reproducible for the covered cases. The result is statistically defensible when users preserve the declared monthly window, method, and assumptions; it is not a causal attribution system.

