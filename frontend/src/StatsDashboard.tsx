import { useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Download,
  FileText,
  Info,
  Minus,
  ShieldCheck,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import type { GeoPoint, InvestigateResponse } from "./types";

interface StatsDashboardProps {
  investigation: InvestigateResponse;
  pointA: GeoPoint;
  pointB: GeoPoint | null;
  mkVariant: "standard" | "hamed_rao";
  onToggleMkVariant: (variant: "standard" | "hamed_rao") => void;
  onOpenDossier: () => void;
  onGoToCharts: () => void;
}

function fmtP(p: number | null | undefined): string {
  if (p === null || p === undefined || Number.isNaN(p)) return "N/A";
  if (p < 0.0001) return "< 0.0001";
  return p.toFixed(4);
}

interface ExpandableExplainProps {
  title: string;
  whatItDoes: string;
  whyUsed: string;
  outputMeaning: string;
  howToInterpret: string;
  example: string;
}

function ExpandableMethodGuide({
  title,
  whatItDoes,
  whyUsed,
  outputMeaning,
  howToInterpret,
  example,
}: ExpandableExplainProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-3 border-t border-slate-800/80 pt-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between rounded-lg bg-slate-950/70 px-3 py-2 text-left text-xs font-semibold text-cyan-300 transition hover:bg-slate-950"
        aria-expanded={open}
      >
        <span className="flex items-center gap-1.5">
          <Info className="h-3.5 w-3.5" />
          {open ? `Hide beginner guide: ${title}` : `Learn how ${title} works`}
        </span>
        {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
      </button>

      {open && (
        <div className="mt-2.5 space-y-2 rounded-xl border border-slate-800 bg-slate-950/80 p-3.5 text-xs leading-relaxed text-slate-300">
          <p>
            <strong className="text-white">What it does:</strong> {whatItDoes}
          </p>
          <p>
            <strong className="text-white">Why it is used:</strong> {whyUsed}
          </p>
          <p>
            <strong className="text-white">What the output means:</strong> {outputMeaning}
          </p>
          <p>
            <strong className="text-white">How to interpret:</strong> {howToInterpret}
          </p>
          <p className="rounded-lg border border-cyan-500/20 bg-cyan-950/20 p-2 text-cyan-100">
            <strong>Simple example:</strong> {example}
          </p>
        </div>
      )}
    </div>
  );
}

export default function StatsDashboard({
  investigation,
  pointA,
  pointB,
  mkVariant,
  onToggleMkVariant,
  onOpenDossier,
  onGoToCharts,
}: StatsDashboardProps) {
  const {
    metadata,
    primary_stats: ps,
    comparison_stats: cs,
    teleconnection,
    detective_brief: brief,
    primary_provenance: prov,
    data_status,
    primary_series: pSeries,
    source_badge,
    region_coverage,
    quality_flags,
  } = investigation.response;

  const [showScience, setShowScience] = useState<boolean>(false);
  const [selectedSeason, setSelectedSeason] = useState<"Annual" | "DJF" | "MAM" | "JJAS" | "ON">("Annual");

  const SEASON_MONTHS: Record<"Annual" | "DJF" | "MAM" | "JJAS" | "ON", number[]> = {
    Annual: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    DJF: [12, 1, 2],
    MAM: [3, 4, 5],
    JJAS: [6, 7, 8, 9],
    ON: [10, 11],
  };

  const seasonalMetrics = (() => {
    const allowed = new Set(SEASON_MONTHS[selectedSeason]);
    const pts: number[] = [];
    pSeries.timestamps.forEach((ts, idx) => {
      const m = Number(ts.slice(5, 7));
      const v = pSeries.raw_values[idx];
      if (allowed.has(m) && v !== null && !Number.isNaN(v)) {
        pts.push(v);
      }
    });
    if (pts.length === 0) return null;
    const mean = pts.reduce((a, b) => a + b, 0) / pts.length;
    const min = Math.min(...pts);
    const max = Math.max(...pts);
    return { count: pts.length, mean, min, max };
  })();

  const handleDownloadCsv = () => {
    const header = [
      "timestamp",
      "raw_value",
      "seasonal_cycle",
      "deseasonalized_anomaly",
      "trend_line",
      "ci_lower",
      "ci_upper",
    ];
    const rows = pSeries.timestamps.map((ts, i) => [
      ts,
      pSeries.raw_values[i] ?? "",
      pSeries.seasonal_cycle[i] ?? "",
      pSeries.deseasonalized_anomalies[i] ?? "",
      pSeries.trend_line[i] ?? "",
      pSeries.ci_lower[i] ?? "",
      pSeries.ci_upper[i] ?? "",
    ]);
    const csvContent = [
      `# TerraShift Export | Region: ${pointA.name} | Variable: ${metadata.parameter_code} (${metadata.unit})`,
      `# Sens Slope: ${ps.sens_slope_per_year}/yr | MK p-value: ${ps.p_value} | Significant: ${ps.is_significant}`,
      header.join(","),
      ...rows.map((r) => r.join(",")),
    ].join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `terrashift-${pointA.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${metadata.parameter_code}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const sigBadge = ps.is_significant
    ? {
        cls: "border-emerald-500/40 bg-emerald-500/15 text-emerald-200",
        text: "Statistically significant (p < 0.05)",
      }
    : ps.p_value < 0.1
      ? {
          cls: "border-amber-500/40 bg-amber-500/15 text-amber-200",
          text: `Borderline (p = ${fmtP(ps.p_value)}, 0.05 ≤ p < 0.10)`,
        }
      : {
          cls: "border-slate-600 bg-slate-800/80 text-slate-300",
          text: `Too noisy / not enough data yet — about ${ps.years_to_significance} more years needed`,
        };

  const isSig = ps.is_significant;
  const isPositive = ps.sens_slope_per_year >= 0;

  // Important: Never classify a trend as significant based only on direction or slope.
  const verdict = !isSig
    ? {
        label: "No Statistically Significant Trend",
        badgeClass: "border-amber-500/40 bg-amber-500/15 text-amber-200",
        cardClass: "border-amber-500/35 bg-gradient-to-br from-amber-950/30 via-slate-900 to-slate-950",
        Icon: Minus,
        summary: `Although the estimated slope is ${ps.sens_slope_per_year >= 0 ? "+" : ""}${ps.sens_slope_per_year} ${metadata.unit}/yr, the Mann-Kendall p-value (${fmtP(ps.p_value)}) is >= 0.05. We do not have enough statistical evidence to rule out natural year-to-year variability over this window.`,
      }
    : isPositive
      ? {
          label: "Statistically Significant Increasing Trend",
          badgeClass: "border-emerald-500/40 bg-emerald-500/15 text-emerald-200",
          cardClass: "border-emerald-500/35 bg-gradient-to-br from-emerald-950/30 via-slate-900 to-slate-950",
          Icon: TrendingUp,
          summary: `The deseasonalized series shows a statistically significant upward trend (p = ${fmtP(ps.p_value)} < 0.05) at ${ps.sens_slope_per_decade >= 0 ? "+" : ""}${ps.sens_slope_per_decade} ${metadata.unit} per decade.`,
        }
      : {
          label: "Statistically Significant Decreasing Trend",
          badgeClass: "border-cyan-500/40 bg-cyan-500/15 text-cyan-200",
          cardClass: "border-cyan-500/35 bg-gradient-to-br from-cyan-950/30 via-slate-900 to-slate-950",
          Icon: TrendingDown,
          summary: `The deseasonalized series shows a statistically significant downward trend (p = ${fmtP(ps.p_value)} < 0.05) at ${ps.sens_slope_per_decade} ${metadata.unit} per decade.`,
        };

  const VerdictIcon = verdict.Icon;
  const olsDecade = ps.ols_slope_per_decade ?? Number((ps.ols_slope_per_year * 10).toFixed(4));
  const olsIntercept = ps.ols_intercept ?? 0;
  const tStat = ps.t_statistic ?? 0;
  const df = ps.degrees_of_freedom ?? Math.max(1, ps.observation_months - 2);
  const mkS = ps.mann_kendall_s ?? 0;
  const acf1 = ps.lag1_autocorrelation ?? 0;
  const acfSig = Boolean(ps.autocorrelation_significant);
  const outlierCount = ps.outlier_count ?? 0;

  return (
    <div className="space-y-6">
      {/* Top Verdict Summary Card */}
      <section className={`rounded-2xl border p-5 shadow-xl sm:p-6 ${verdict.cardClass}`}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-bold ${verdict.badgeClass}`}
              >
                <VerdictIcon className="h-3.5 w-3.5" />
                {verdict.label}
              </span>
              <span className="rounded-full border border-slate-700 bg-slate-900/80 px-2.5 py-0.5 text-xs font-medium text-slate-300">
                {pointA.name} · {metadata.parameter_name} ({metadata.unit})
              </span>
              {source_badge && (
                <span className="rounded-full border border-cyan-500/40 bg-cyan-950/50 px-2.5 py-0.5 text-xs font-semibold text-cyan-200">
                  {source_badge}
                </span>
              )}
              <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${sigBadge.cls}`}>
                {sigBadge.text}
              </span>
              <span className="rounded-full border border-slate-700 bg-slate-900/80 px-2.5 py-0.5 font-mono text-xs text-slate-300">
                n = {ps.observation_months} months ({ps.observation_years} yrs)
              </span>
            </div>

            {region_coverage && (
              <p className="text-xs text-slate-300">
                Region averaging: <strong>{region_coverage.grid_cells_used}</strong> grid cell(s) ·{" "}
                <strong>{region_coverage.area_covered_pct.toFixed(1)}%</strong> area covered ({region_coverage.weighting})
              </p>
            )}
            {quality_flags && quality_flags.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {quality_flags.map((flag, idx) => (
                  <span
                    key={idx}
                    className="rounded-lg border border-amber-500/40 bg-amber-950/40 px-2.5 py-1 text-xs text-amber-200"
                  >
                    {flag}
                  </span>
                ))}
              </div>
            )}

            <h2 className="text-xl font-extrabold text-white sm:text-2xl">{brief.verdict_headline}</h2>
            <p className="max-w-3xl text-sm leading-relaxed text-slate-200">{verdict.summary}</p>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onGoToCharts}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-900 px-3.5 py-2 text-xs font-semibold text-slate-200 transition hover:border-cyan-400"
            >
              View Time-Series Chart
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={handleDownloadCsv}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-900 px-3.5 py-2 text-xs font-semibold text-slate-200 transition hover:border-cyan-400"
            >
              <Download className="h-3.5 w-3.5" />
              Export CSV
            </button>
            <button
              type="button"
              onClick={onOpenDossier}
              className="inline-flex items-center gap-1.5 rounded-xl bg-slate-100 px-3.5 py-2 text-xs font-bold text-slate-950 transition hover:bg-cyan-200"
            >
              <FileText className="h-3.5 w-3.5" />
              Field Dossier (PDF / JSON)
            </button>
          </div>
        </div>

        {/* Main-flow Indian Seasonal Breakdown + Show the Science Toggle */}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-800/80 pt-4">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-xs font-semibold text-slate-400">Season:</span>
            {(["Annual", "DJF", "MAM", "JJAS", "ON"] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setSelectedSeason(s)}
                className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition ${
                  selectedSeason === s
                    ? "bg-cyan-500 text-slate-950"
                    : "border border-slate-700 bg-slate-900 text-slate-300 hover:bg-slate-800"
                }`}
              >
                {s}
              </button>
            ))}
            {seasonalMetrics && (
              <span className="ml-2 text-xs text-slate-300">
                Mean: <strong className="font-mono text-white">{seasonalMetrics.mean.toFixed(2)} {metadata.unit}</strong>{" "}
                ({seasonalMetrics.count} mo)
              </span>
            )}
            {ps.seasonal_mann_kendall && (
              <span className="ml-2 rounded-full border border-indigo-500/40 bg-indigo-950/40 px-2.5 py-0.5 text-xs text-indigo-200">
                Seasonal MK (Hirsch 1982): p = {fmtP(ps.seasonal_mann_kendall.p_value)}
              </span>
            )}
          </div>

          <button
            type="button"
            onClick={() => setShowScience((prev) => !prev)}
            className="inline-flex items-center gap-1.5 rounded-xl border border-cyan-500/40 bg-cyan-950/40 px-3 py-1.5 text-xs font-bold text-cyan-200 transition hover:bg-cyan-900/50"
          >
            {showScience ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            {showScience ? "Hide the science" : "Show the science"}
          </button>
        </div>

        {/* At-a-glance KPI Strip (shown when Show the science is toggled on) */}
        {showScience && (
          <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-3">
            <p className="text-xs text-slate-400">Sen&apos;s Slope / Decade</p>
            <p className="mt-1 font-mono text-base font-bold text-cyan-300">
              {ps.sens_slope_per_decade >= 0 ? "+" : ""}
              {ps.sens_slope_per_decade}
            </p>
            <p className="text-xs text-slate-500">{metadata.unit}/decade</p>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-3">
            <p className="text-xs text-slate-400">OLS Slope / Decade</p>
            <p className="mt-1 font-mono text-base font-bold text-slate-100">
              {olsDecade >= 0 ? "+" : ""}
              {olsDecade}
            </p>
            <p className="text-xs text-slate-500">{metadata.unit}/decade</p>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-3">
            <p className="text-xs text-slate-400">Mann-Kendall p</p>
            <p className={`mt-1 font-mono text-base font-bold ${isSig ? "text-emerald-400" : "text-amber-300"}`}>
              {fmtP(ps.p_value)}
            </p>
            <p className="text-xs text-slate-500">{isSig ? "p < 0.05 (Significant)" : "p >= 0.05 (Not Sig.)"}</p>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-3">
            <p className="text-xs text-slate-400">Student&apos;s t-test p</p>
            <p className="mt-1 font-mono text-base font-bold text-slate-100">{fmtP(ps.t_test_p_value)}</p>
            <p className="text-xs text-slate-500">df = {df}</p>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-3">
            <p className="text-xs text-slate-400">95% Slope CI</p>
            <p className="mt-1 font-mono text-xs font-bold text-slate-100">
              [{ps.sens_slope_ci_lower ?? "—"}, {ps.sens_slope_ci_upper ?? "—"}]
            </p>
            <p className="text-xs text-slate-500">{metadata.unit}/year</p>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-3">
            <p className="text-xs text-slate-400">Seasonality Removed</p>
            <p className="mt-1 font-mono text-base font-bold text-emerald-300">{ps.variance_reduction_pct}%</p>
            <p className="text-xs text-slate-400">via STL (period=12)</p>
          </div>
        </div>
        )}
      </section>

      {/* Autocorrelation Advisory Banner (if serial correlation is detected) */}
      {acfSig && mkVariant === "standard" && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-500/40 bg-amber-950/35 px-4 py-3 text-xs text-amber-100">
          <div className="flex items-start gap-2.5">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
            <div>
              <p className="font-bold text-amber-200">
                Serial Autocorrelation Detected (Lag-1 r = {acf1.toFixed(3)})
              </p>
              <p className="mt-0.5 text-amber-100/90">
                Adjacent months are correlated, which can make standard p-values appear overly confident. Switching to the{" "}
                <strong>Hamed-Rao Modified Mann-Kendall</strong> test adjusts the variance for serial correlation.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => onToggleMkVariant("hamed_rao")}
            className="rounded-lg bg-amber-400 px-3 py-1.5 text-xs font-bold text-slate-950 transition hover:bg-amber-300"
          >
            Apply Hamed-Rao Modified MK
          </button>
        </div>
      )}

      {/* 5 Core Statistical Method Cards (expanded with Show the science) */}
      {showScience && (
      <section className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* A. Linear Regression & Rate of Change */}
        <article className="rounded-2xl border border-slate-800 bg-slate-900/75 p-5 shadow-lg">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-bold text-white">A. Linear Regression &amp; Rate of Change</h3>
            <span className="rounded-full bg-cyan-500/15 px-2.5 py-0.5 text-xs font-semibold text-cyan-300">
              Parametric OLS
            </span>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3 rounded-xl border border-slate-800 bg-slate-950/60 p-3.5 text-xs sm:grid-cols-3">
            <div>
              <p className="text-slate-400">Slope (per year)</p>
              <p className="mt-0.5 font-mono text-sm font-bold text-white">
                {ps.ols_slope_per_year >= 0 ? "+" : ""}
                {ps.ols_slope_per_year} {metadata.unit}/yr
              </p>
            </div>
            <div>
              <p className="text-slate-400">Slope (per decade)</p>
              <p className="mt-0.5 font-mono text-sm font-bold text-cyan-300">
                {olsDecade >= 0 ? "+" : ""}
                {olsDecade} {metadata.unit}/dec
              </p>
            </div>
            <div>
              <p className="text-slate-400">Intercept (at t = 0)</p>
              <p className="mt-0.5 font-mono text-sm font-bold text-slate-200">
                {olsIntercept >= 0 ? "+" : ""}
                {olsIntercept} {metadata.unit}
              </p>
            </div>
          </div>

          <p className="mt-3 text-xs leading-relaxed text-slate-300">
            The best-fit straight line through the deseasonalized anomalies slopes{" "}
            <strong className="text-white">
              {ps.ols_slope_per_year > 0 ? "upward" : ps.ols_slope_per_year < 0 ? "downward" : "flat"}
            </strong>{" "}
            at{" "}
            <span className="font-mono text-cyan-300">
              {olsDecade >= 0 ? "+" : ""}
              {olsDecade} {metadata.unit}/decade
            </span>
            . This regression line is plotted directly on the Deseasonalized Trend Lab chart.
          </p>

          <ExpandableMethodGuide
            title="Linear Regression"
            whatItDoes="Fits the straight line (y = intercept + slope × time) that minimizes the squared vertical distances to the deseasonalized monthly anomalies."
            whyUsed="Gives an easy-to-read average rate of change in real physical units (such as °C per decade or mm per year)."
            outputMeaning="A positive slope means the average value is rising over time; a negative slope means it is falling; the intercept is the baseline value at the start of the window."
            howToInterpret="Check the slope together with a significance test (t-test or Mann-Kendall). A non-zero slope alone does not prove a lasting trend if year-to-year noise is large."
            example="If temperature anomalies have an OLS slope of +0.03 °C/year, the linear trend corresponds to +0.30 °C over 10 years."
          />
        </article>

        {/* B. Student's t-test */}
        <article className="rounded-2xl border border-slate-800 bg-slate-900/75 p-5 shadow-lg">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-bold text-white">B. Student&apos;s t-test for Trend</h3>
            <span
              className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                ps.t_test_p_value < 0.05
                  ? "bg-emerald-500/15 text-emerald-300"
                  : "bg-amber-500/15 text-amber-300"
              }`}
            >
              {ps.t_test_p_value < 0.05 ? "Significant (p < 0.05)" : "Not Significant (p >= 0.05)"}
            </span>
          </div>

          <div className="mt-4 grid grid-cols-3 gap-3 rounded-xl border border-slate-800 bg-slate-950/60 p-3.5 text-xs">
            <div>
              <p className="text-slate-400">t-statistic</p>
              <p className="mt-0.5 font-mono text-sm font-bold text-white">{tStat}</p>
            </div>
            <div>
              <p className="text-slate-400">Degrees of Freedom</p>
              <p className="mt-0.5 font-mono text-sm font-bold text-slate-200">{df}</p>
            </div>
            <div>
              <p className="text-slate-400">Two-sided p-value</p>
              <p
                className={`mt-0.5 font-mono text-sm font-bold ${
                  ps.t_test_p_value < 0.05 ? "text-emerald-400" : "text-amber-300"
                }`}
              >
                {fmtP(ps.t_test_p_value)}
              </p>
            </div>
          </div>

          <p className="mt-3 text-xs leading-relaxed text-slate-300">
            With <span className="font-mono">t = {tStat}</span> and <span className="font-mono">df = {df}</span>, the
            probability of seeing a linear slope this steep by random chance alone is{" "}
            <strong className="text-white">{fmtP(ps.t_test_p_value)}</strong>.{" "}
            {ps.t_test_p_value < 0.05
              ? "Because p < 0.05, the linear slope is unlikely to be pure random noise (assuming independent residuals)."
              : "Because p >= 0.05, we cannot reject the null hypothesis of zero linear trend."}
          </p>

          <ExpandableMethodGuide
            title="Student's t-test"
            whatItDoes="Divides the estimated linear regression slope by its standard error to test whether the true slope is different from zero."
            whyUsed="Evaluates how large the trend signal is compared to the scatter (noise) around the regression line."
            outputMeaning="Larger |t| values mean stronger evidence against a flat trend; df = n - 2 reflects sample size minus two fitted parameters; p < 0.05 is the standard 95% significance threshold."
            howToInterpret="Because climate data can have outliers or serial correlation, compare the t-test p-value with the non-parametric Mann-Kendall test."
            example="If t = 4.2 with p = 0.0001, there is only a 0.01% chance of observing such a steep line if no real linear trend existed."
          />
        </article>

        {/* C. Mann-Kendall Trend Test */}
        <article className="rounded-2xl border border-slate-800 bg-slate-900/75 p-5 shadow-lg">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-base font-bold text-white">C. Mann-Kendall Trend Test</h3>
            <div className="flex items-center gap-1 rounded-lg border border-slate-800 bg-slate-950 p-0.5 text-xs">
              <button
                type="button"
                onClick={() => onToggleMkVariant("standard")}
                className={`rounded-md px-2 py-1 font-medium transition ${
                  mkVariant === "standard" ? "bg-cyan-500 text-slate-950 font-bold" : "text-slate-400 hover:text-white"
                }`}
              >
                Standard MK
              </button>
              <button
                type="button"
                onClick={() => onToggleMkVariant("hamed_rao")}
                className={`rounded-md px-2 py-1 font-medium transition ${
                  mkVariant === "hamed_rao" ? "bg-cyan-500 text-slate-950 font-bold" : "text-slate-400 hover:text-white"
                }`}
              >
                Hamed-Rao Modified
              </button>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3 rounded-xl border border-slate-800 bg-slate-950/60 p-3.5 text-xs sm:grid-cols-4">
            <div>
              <p className="text-slate-400">Kendall&apos;s S</p>
              <p className="mt-0.5 font-mono text-sm font-bold text-white">{mkS}</p>
            </div>
            <div>
              <p className="text-slate-400">Kendall&apos;s &tau;</p>
              <p className="mt-0.5 font-mono text-sm font-bold text-cyan-300">{ps.mann_kendall_tau}</p>
            </div>
            <div>
              <p className="text-slate-400">Z-statistic</p>
              <p className="mt-0.5 font-mono text-sm font-bold text-slate-100">{ps.z_score}</p>
            </div>
            <div>
              <p className="text-slate-400">p-value</p>
              <p className={`mt-0.5 font-mono text-sm font-bold ${isSig ? "text-emerald-400" : "text-amber-300"}`}>
                {fmtP(ps.p_value)}
              </p>
            </div>
          </div>

          <p className="mt-3 text-xs leading-relaxed text-slate-300">
            Active variant: <strong className="text-white">{mkVariant === "hamed_rao" ? "Hamed-Rao Modified MK" : "Standard MK"}</strong>.{" "}
            Direction is <strong className="text-white">{ps.z_score >= 0 ? "upward" : "downward"}</strong> and is{" "}
            <strong className={isSig ? "text-emerald-300" : "text-amber-300"}>
              {isSig ? "statistically significant (p < 0.05)" : "not statistically significant (p >= 0.05)"}
            </strong>
            . Raw seasonal MK p-value before STL deseasonalizing was <span className="font-mono">{fmtP(ps.raw_p_value)}</span>.
          </p>

          <ExpandableMethodGuide
            title="Mann-Kendall Test"
            whatItDoes="Compares every earlier observation with every later observation to count whether values consistently go up (S > 0) or down (S < 0), without assuming a straight line or bell-curve noise."
            whyUsed="Environmental data often has extreme weather spikes and skewed values. Mann-Kendall is resistant to outliers and works for any monotonic (consistently rising or falling) pattern."
            outputMeaning="S is the net count of upward vs. downward pairs; tau (-1 to +1) scales S by total pairs; Z measures how many standard deviations S is from zero; p < 0.05 indicates a statistically significant monotonic trend."
            howToInterpret="If lag-1 autocorrelation is significant, use Hamed-Rao Modified MK so persistent weather regimes (like multi-year El Niño cycles) do not inflate significance."
            example="If tau = +0.42 and p = 0.0002, later years consistently rank higher than earlier years much more often than expected by chance."
          />
        </article>

        {/* D. Sen's Slope Estimator */}
        <article className="rounded-2xl border border-slate-800 bg-slate-900/75 p-5 shadow-lg">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-bold text-white">D. Sen&apos;s Slope Estimator</h3>
            <span className="rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-xs font-semibold text-emerald-300">
              Robust Non-Parametric
            </span>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3 rounded-xl border border-slate-800 bg-slate-950/60 p-3.5 text-xs">
            <div>
              <p className="text-slate-400">Sen&apos;s Slope (Median Rate)</p>
              <p className="mt-0.5 font-mono text-sm font-bold text-emerald-300">
                {ps.sens_slope_per_year >= 0 ? "+" : ""}
                {ps.sens_slope_per_year} {metadata.unit}/yr
              </p>
              <p className="font-mono text-xs text-slate-400">
                ({ps.sens_slope_per_decade >= 0 ? "+" : ""}
                {ps.sens_slope_per_decade} {metadata.unit}/dec)
              </p>
            </div>
            <div>
              <p className="text-slate-400">Comparison vs. OLS Slope</p>
              <p className="mt-0.5 font-mono text-sm font-bold text-slate-100">
                {ps.ols_slope_per_year >= 0 ? "+" : ""}
                {ps.ols_slope_per_year} {metadata.unit}/yr
              </p>
              <p className="text-xs text-slate-400">
                Difference:{" "}
                <span className="font-mono">
                  {Math.abs(ps.sens_slope_per_year - ps.ols_slope_per_year).toFixed(4)}
                </span>{" "}
                {metadata.unit}/yr
              </p>
            </div>
          </div>

          <p className="mt-3 text-xs leading-relaxed text-slate-300">
            Sen&apos;s slope takes the <strong>median</strong> of all pairwise slopes between points, so an extreme heatwave
            or flood year does not pull the trend rate off course the way it can in ordinary linear regression.
          </p>

          <ExpandableMethodGuide
            title="Sen's Slope Estimator"
            whatItDoes="Calculates the slope between every pair of months in the dataset and selects the exact middle (median) slope."
            whyUsed="Ordinary linear regression squares errors, meaning one extreme El Niño or hurricane month can tilt the line. Sen's median slope stays anchored to the typical long-term change."
            outputMeaning="Expressed directly in physical units per year and per decade. Comparing Sen's slope with OLS reveals whether outliers are pulling the linear regression line."
            howToInterpret="When Sen's slope and OLS slope are close, the trend is steady across the whole record; when they differ noticeably, extreme events are influencing the OLS mean."
            example="If 1998 had an extreme rainfall spike, OLS might exaggerate or flatten the slope, while Sen's median slope reflects the underlying multi-decade shift."
          />
        </article>

        {/* E. Confidence Intervals & Uncertainty */}
        <article className="rounded-2xl border border-slate-800 bg-slate-900/75 p-5 shadow-lg lg:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-base font-bold text-white">E. 95% Confidence Intervals &amp; Uncertainty</h3>
            <span className="rounded-full bg-indigo-500/15 px-2.5 py-0.5 text-xs font-semibold text-indigo-300">
              95% Confidence Level (&alpha; = 0.05)
            </span>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-3">
            <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3.5 text-xs">
              <p className="text-slate-400">Sen&apos;s Slope 95% Confidence Interval</p>
              <p className="mt-1 font-mono text-base font-bold text-cyan-300">
                [{ps.sens_slope_ci_lower ?? "—"}, {ps.sens_slope_ci_upper ?? "—"}] {metadata.unit}/yr
              </p>
              <p className="mt-1 text-xs text-slate-400">
                {ps.sens_slope_ci_lower !== undefined &&
                ps.sens_slope_ci_upper !== undefined &&
                ((ps.sens_slope_ci_lower > 0 && ps.sens_slope_ci_upper > 0) ||
                  (ps.sens_slope_ci_lower < 0 && ps.sens_slope_ci_upper < 0))
                  ? "The entire 95% interval lies on one side of zero, reinforcing a consistent trend direction."
                  : "The 95% interval includes zero, meaning both slight increases and slight decreases remain plausible."}
              </p>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3.5 text-xs">
              <p className="text-slate-400">Chart Uncertainty Band</p>
              <p className="mt-1 font-semibold text-white">95% OLS Mean-Response Band</p>
              <p className="mt-1 text-xs text-slate-400">
                The shaded ribbon around the regression line in Trend Analysis visualizes how precisely the mean trend is
                pinned down at each point in time.
              </p>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3.5 text-xs">
              <p className="text-slate-400">Estimated Additional Observation Period</p>
              <p className="mt-1 font-mono text-base font-bold text-emerald-300">
                {isSig
                  ? "0 yrs (Threshold Reached)"
                  : (ps.estimated_additional_observation_years ?? ps.years_to_significance) >= 90
                    ? "Near-zero slope"
                    : `~${ps.estimated_additional_observation_years ?? ps.years_to_significance} yrs`}
              </p>
              <p className="mt-1 text-xs text-slate-400">
                Illustrative statistical power estimate assuming stationary slope and noise — not a future forecast.
              </p>
            </div>
          </div>

          <ExpandableMethodGuide
            title="95% Confidence Intervals"
            whatItDoes="Calculates a plausible lower and upper bound around the estimated slope (Sen 1968 order statistics for Sen's slope; Student's t distribution for the OLS chart band)."
            whyUsed="A single slope number hides measurement uncertainty. A confidence interval shows how wide the range of plausible rates is given the length and noisiness of the data."
            outputMeaning="A narrower interval means a more precisely measured trend; a wider interval means higher natural variability or a shorter observation window."
            howToInterpret="If the 95% CI spans from negative to positive (crossing 0), we cannot be 95% sure of the true direction yet."
            example="A slope of +0.20 °C/decade with a 95% CI of [+0.14, +0.26] means the true underlying rate is likely between +0.14 and +0.26 °C/decade."
          />
        </article>
      </section>
      )}

      {/* Scientific Reliability, Data Diagnostics & AI Grounding */}
      <section className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <div className="rounded-2xl border border-slate-800 bg-slate-900/75 p-5 lg:col-span-6">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-emerald-400" />
            <h3 className="text-base font-bold text-white">Scientific Reliability &amp; Data Quality Checks</h3>
          </div>

          <dl className="mt-4 grid grid-cols-2 gap-3 text-xs">
            <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
              <dt className="text-slate-400">Missing Observations</dt>
              <dd className="mt-0.5 font-mono font-bold text-white">
                {ps.missing_months ?? 0} months ({(ps.missing_pct ?? 0).toFixed(1)}%)
              </dd>
              <dd className="mt-0.5 text-xs text-slate-500">Gaps &gt; 3 months are rejected rather than fabricated.</dd>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
              <dt className="text-slate-400">Outliers Detected (|z| &gt; 3)</dt>
              <dd className="mt-0.5 font-mono font-bold text-white">{outlierCount} points</dd>
              <dd className="mt-0.5 text-xs text-slate-500">Flagged for transparency; never automatically deleted.</dd>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
              <dt className="text-slate-400">Lag-1 Autocorrelation</dt>
              <dd className="mt-0.5 font-mono font-bold text-white">
                r = {acf1.toFixed(3)} ({acfSig ? "Present" : "Low"})
              </dd>
              <dd className="mt-0.5 text-xs text-slate-500">Checked on detrended anomalies.</dd>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
              <dt className="text-slate-400">Data Source &amp; Status</dt>
              <dd className="mt-0.5 font-semibold text-cyan-300">
                {(prov?.source_name ?? metadata.mission_source).split("(")[0].trim()} ({data_status})
              </dd>
              <dd className="mt-0.5 text-xs text-slate-500">{prov?.data_type ?? metadata.data_type ?? "Reanalysis"}</dd>
            </div>
          </dl>

          <ul className="mt-4 space-y-1.5 text-xs leading-relaxed text-slate-400">
            <li className="flex items-start gap-1.5">
              <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" />
              <span>
                <strong className="text-slate-200">Statistical vs. Practical Significance:</strong> A tiny trend can be
                statistically significant in a long record yet have minor local impact, while a real environmental shift
                may not yet reach p &lt; 0.05 in a short record.
              </span>
            </li>
            <li className="flex items-start gap-1.5">
              <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" />
              <span>
                <strong className="text-slate-200">No Causal Claims from Trends Alone:</strong> Statistical tests measure
                change over time and co-variation; physical causes require domain evidence.
              </span>
            </li>
          </ul>
        </div>

        {/* AI / Physical Interpretation & Comparison Summary */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900/75 p-5 lg:col-span-6">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-cyan-400" />
              <h3 className="text-base font-bold text-white">Plain-Language Physical Context</h3>
            </div>
            <span className="rounded-full border border-slate-700 bg-slate-950 px-2.5 py-0.5 text-xs font-semibold text-slate-300">
              {brief.ai_enhanced ? "Gemini-Enhanced · Stats-Grounded" : "Deterministic Brief"}
            </span>
          </div>

          <div className="mt-4 space-y-3 text-xs leading-relaxed text-slate-300">
            <p>{brief.physical_mechanism}</p>
            <p className="text-slate-400">{brief.seasonality_note}</p>
            <p className="text-slate-400">{brief.horizon_note}</p>

            {teleconnection.enabled && pointB && cs && (
              <div className="rounded-xl border border-indigo-500/30 bg-indigo-950/25 p-3">
                <p className="flex items-center gap-1.5 font-semibold text-indigo-200">
                  <Activity className="h-3.5 w-3.5" />
                  Regional Comparison: {pointA.name} vs. {pointB.name}
                </p>
                <p className="mt-1 text-xs text-slate-300">
                  {pointB.name} slope:{" "}
                  <span className="font-mono font-bold">
                    {cs.sens_slope_per_year >= 0 ? "+" : ""}
                    {cs.sens_slope_per_year} {metadata.unit}/yr
                  </span>{" "}
                  (p = {fmtP(cs.p_value)}) · Cross-correlation{" "}
                  <span className="font-mono font-bold">r = {teleconnection.cross_correlation_r?.toFixed(2) ?? "N/A"}</span>.
                  Correlation measures statistical co-variation, not direct causation.
                </p>
              </div>
            )}

            {brief.limitations_note && (
              <p className="rounded-lg border border-slate-800 bg-slate-950/60 p-2.5 text-xs text-slate-400">
                <strong className="text-slate-200">Limitations:</strong> {brief.limitations_note}
              </p>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
