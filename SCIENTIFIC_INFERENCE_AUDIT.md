# Scientific Inference Audit

## Corrections made

Earlier deterministic briefs used phrases such as “drives,” “accelerate,” and “yields” for observational trend outputs. These were changed to language such as “is consistent with,” “may contribute,” and “contextual hypothesis.”

Every brief now states:

- a detected trend is limited to the selected variable, region, period, and dataset;
- a mechanism sentence is not causal attribution;
- correlation does not establish causation or a teleconnection;
- p >= 0.05 does not prove no physical change;
- grid-cell/reanalysis values are not point-gauge observations.

## Interpretation boundaries

| Concept | Permitted claim |
|---|---|
| Observed change | The selected series changed over the selected period |
| Estimated trend | Sen or OLS slope with explicit units |
| Statistical significance | Evidence against the declared null at alpha 0.05 |
| Practical significance | Not automatically established by p-value |
| Causal explanation | Not established by TerraShift trend/correlation analysis |
| Uncertainty | Statistical interval plus explicit data/model/spatial limitations |

## AI interpretation

The optional Gemini path receives validated statistics and provenance after the deterministic brief is built. It cannot calculate or replace numerical values. The deterministic brief remains the fallback when no key is configured or AI enhancement fails.

Remaining risk: an external model can still produce wording that requires review. The UI labels AI-enhanced output, exports the deterministic numerical response, and includes the deterministic limitations. Production scientific claims should use the deterministic result object as the authority.

## Remaining limitations

- No threshold for “rapid,” “severe,” or “meaningful” change is asserted.
- No global false-discovery correction is applied across independent user analyses.
- Mechanism context is not a formal attribution study.
- Statistical confidence intervals do not represent all measurement/model uncertainty.

