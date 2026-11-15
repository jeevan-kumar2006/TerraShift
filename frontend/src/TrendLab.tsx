import { useEffect, useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CalendarRange,
  CheckCircle2,
  Clock,
  Compass,
  HelpCircle,
  Layers,
  Radio,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import type { GeoPoint, InvestigateResponse } from "./types";
import UpfrontTrendSummary from "./UpfrontTrendSummary";

type ChartMode = "raw" | "deseasonalized" | "teleconnection";

interface TrendLabProps {
  investigation: InvestigateResponse;
  pointA: GeoPoint;
  pointB: GeoPoint | null;
  windowRange: [number, number];
  onChangeWindow: (next: [number, number]) => void;
  loading: boolean;
  onOpenDossier?: () => void;
}

function formatPValue(p: number | null | undefined): string {
  if (p === null || p === undefined || Number.isNaN(p)) return "N/A";
  if (p < 0.0001) return "< 0.0001";
  return p.toFixed(4);
}

function getSlopeDirectionLabel(
  parameter: string,
  slope: number
): { label: string; positiveIsAlert: boolean; description: string } {
  const code = parameter.toUpperCase();
  if (code === "T2M") {
    return {
      label: slope >= 0 ? "Warming Trend" : "Cooling Trend",
      positiveIsAlert: true,
      description: slope >= 0 ? "Temperatures are increasing over time" : "Temperatures are decreasing over time",
    };
  }
  if (code === "PS") {
    return {
      label: slope >= 0 ? "Rising Surface Pressure" : "Falling Surface Pressure",
      positiveIsAlert: false,
      description:
        slope >= 0
          ? "Barometric pressure is trending upward over time"
          : "Barometric pressure is trending downward over time",
    };
  }
  return {
    label: slope >= 0 ? "Wetting Trend (Moisture Increasing)" : "Drying Trend (Moisture Decreasing)",
    positiveIsAlert: false,
    description:
      slope >= 0
        ? "Soil moisture / precipitation is increasing over time"
        : "Soil moisture / precipitation is decreasing over time",
  };
}

// Plain-language definitions for key metrics
const METRIC_EXPLANATIONS: Record<
  string,
  { title: string; summary: string; formulaOrRule: string; interpretation: string }
> = {
  sens_slope: {
    title: "Sen's Slope Estimator",
    summary:
      "The median rate of change per year across all pairwise combinations of months. Unlike standard linear regression, it is non-parametric and immune to distortion from extreme single-month anomalies (e.g. volcanic eruptions, severe El Niño events).",
    formulaOrRule: "Median of slopes between all point pairs (yj - yi) / (j - i) for j > i",
    interpretation:
      "A positive slope means an upward trend over time; a negative slope means a downward trend. Combined with the p-value, it reveals whether the trend is physically meaningful.",
  },
  p_value: {
    title: "Mann-Kendall p-value (Statistical Significance)",
    summary:
      "The probability that the observed multi-decade trend occurred purely by random weather noise rather than an underlying physical change.",
    formulaOrRule: "Threshold: α = 0.05 (95% confidence level)",
    interpretation:
      "p < 0.05: Statistically significant trend. There is less than a 5% chance this is natural noise.\np ≥ 0.05: Not statistically significant over this window. Natural variability masks the trend, or the slope is zero.",
  },
  mk_tau: {
    title: "Mann-Kendall Tau (τ)",
    summary:
      "A rank correlation coefficient measuring monotonic direction over time (-1 = strictly decreasing, 0 = no trend, +1 = strictly increasing).",
    formulaOrRule: "τ = S / [0.5 * n * (n - 1)], where S is the sum of directional signs",
    interpretation:
      "Values near +1 or -1 indicate consistent year-over-year directional shifts regardless of curve shape.",
  },
  z_score: {
    title: "Standardized Test Statistic (Z-Score)",
    summary:
      "Measures how many standard deviations the Mann-Kendall score S deviates from zero expected under the null hypothesis.",
    formulaOrRule: "Z > +1.96 or Z < -1.96 corresponds to p < 0.05 (two-tailed test)",
    interpretation:
      "Large positive Z indicates strong upward momentum; large negative Z indicates strong downward momentum.",
  },
  stl_variance: {
    title: "STL Variance Reduction",
    summary:
      "The percentage of total time-series variance stripped away by removing the repeating 12-month seasonal cycle (e.g. summer highs, winter lows).",
    formulaOrRule: "Decomposition: Raw = Trend + Seasonal (period=12) + Remainder",
    interpretation:
      "A high variance reduction (e.g. > 80%) shows that annual seasons heavily masked the long-term climate signal before deseasonalization.",
  },
  raw_vs_deseasonalized: {
    title: "Why Seasonality (STL) Must Be Stripped",
    summary:
      "In Earth data, massive repeating summer-winter swings produce high autocorrelation and noise that confuse standard trend tests. Stripping the repeating 12-month seasonal cycle exposes the true multi-decade anomalies.",
    formulaOrRule: "Raw MK test often yields false confidence or masks subtle slow shifts",
    interpretation:
      "Notice how the raw p-value differs from the deseasonalized p-value. Deseasonalization is what makes the trend scientifically defensible.",
  },
  obs_horizon: {
    title: "Estimated Additional Observation Period",
    summary:
      "Statistical power assessment: how many additional years of monthly data would be needed to statistically confirm the trend at p < 0.05, assuming stationary slope and variance.",
    formulaOrRule: "Derived from signal-to-noise ratio: (variance / slope²) scaling",
    interpretation:
      "When a short 5-year window shows 'Not Significant', this estimator demonstrates why 30+ year observation baselines are mandatory in climate science.",
  },
  cross_correlation: {
    title: "Pearson Cross-Correlation (r)",
    summary:
      "Measures linear co-variation between Region A and Region B deseasonalized anomalies across identical months.",
    formulaOrRule: "r ranges from -1.0 to +1.0 (α = 0.05)",
    interpretation:
      "r ≥ +0.25: Synchronized co-movement.\nr ≤ -0.25: Inverse seesaw (e.g. dipole / NAO / Arctic-subpolar oscillations).\n-0.25 < r < +0.25: Decoupled regional systems.",
  },
};

export default function TrendLab({
  investigation,
  pointA,
  pointB,
  windowRange,
  onChangeWindow,
  loading,
  onOpenDossier,
}: TrendLabProps) {
  const [chartMode, setChartMode] = useState<ChartMode>("raw");
  const [draftStart, setDraftStart] = useState<number>(windowRange[0]);
  const [draftEnd, setDraftEnd] = useState<number>(windowRange[1]);
  const [activeExplainKey, setActiveExplainKey] = useState<string | null>(null);

  useEffect(() => {
    setDraftStart(windowRange[0]);
    setDraftEnd(windowRange[1]);
  }, [windowRange]);

  const {
    metadata,
    primary_series,
    primary_stats,
    comparison_series,
    teleconnection,
  } = investigation.response;

  // If teleconnection mode was active and Marker B is cleared, return smoothly to deseasonalized
  useEffect(() => {
    if (chartMode === "teleconnection" && (!teleconnection.enabled || !comparison_series)) {
      setChartMode("deseasonalized");
    }
  }, [chartMode, teleconnection.enabled, comparison_series]);

  const chartData = useMemo(() => {
    if (!primary_series || !primary_series.timestamps || primary_series.timestamps.length === 0) {
      return [];
    }

    const rawValid = primary_series.raw_values.filter((v): v is number => v !== null);
    const rawMean = rawValid.length ? rawValid.reduce((a, b) => a + b, 0) / rawValid.length : 0;

    return primary_series.timestamps.map((ts, idx) => {
      const ciLow = primary_series.ci_lower ? primary_series.ci_lower[idx] : null;
      const ciHigh = primary_series.ci_upper ? primary_series.ci_upper[idx] : null;
      const seas = primary_series.seasonal_cycle ? primary_series.seasonal_cycle[idx] : null;
      const compAnom =
        comparison_series && comparison_series.deseasonalized_anomalies && idx < comparison_series.deseasonalized_anomalies.length
          ? comparison_series.deseasonalized_anomalies[idx]
          : null;
      const compTrend =
        comparison_series && comparison_series.trend_line && idx < comparison_series.trend_line.length
          ? comparison_series.trend_line[idx]
          : null;

      return {
        timestamp: ts,
        raw: primary_series.raw_values[idx],
        seasonalShifted: seas !== null && seas !== undefined ? Number((seas + rawMean).toFixed(4)) : null,
        anomaly: primary_series.deseasonalized_anomalies[idx],
        trend: primary_series.trend_line[idx],
        ciRange: ciLow !== null && ciHigh !== null && ciLow !== undefined && ciHigh !== undefined ? [ciLow, ciHigh] : null,
        compAnomaly: compAnom,
        compTrend: compTrend,
      };
    });
  }, [primary_series, comparison_series]);

  const applyDraftStart = (val: number) => {
    const clamped = Math.min(val, draftEnd - 3);
    setDraftStart(clamped);
    onChangeWindow([clamped, draftEnd]);
  };

  const applyDraftEnd = (val: number) => {
    const clamped = Math.max(val, draftStart + 3);
    setDraftEnd(clamped);
    onChangeWindow([draftStart, clamped]);
  };

  const dirInfo = getSlopeDirectionLabel(metadata.parameter_code, primary_stats.sens_slope_per_year);
  const obsYears = primary_stats.observation_years;
  const yearsNeeded = primary_stats.years_to_significance;
  const horizonPct = primary_stats.is_significant
    ? 100
    : yearsNeeded >= 90
      ? 12
      : Math.max(8, Math.min(96, Math.round((obsYears / (obsYears + yearsNeeded)) * 100)));

  const rVal = teleconnection.cross_correlation_r;
  const rInterpret =
    rVal === null || rVal === undefined
      ? null
      : rVal <= -0.25
        ? { label: "Inverse Seesaw (Opposite Coupling)", cls: "bg-rose-500/15 text-rose-200 border-rose-500/40" }
        : rVal >= 0.25
          ? { label: "Synchronized Co-Movement (In-Sync)", cls: "bg-emerald-500/15 text-emerald-200 border-emerald-500/40" }
          : { label: "Weak / Decoupled Systems", cls: "bg-slate-800 text-slate-300 border-slate-700" };

  const activeExplain = activeExplainKey ? METRIC_EXPLANATIONS[activeExplainKey] : null;

  return (
    <section className="flex flex-col gap-5">
      {/* Investigation Progress Breadcrumb Flow Header */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4 shadow-xl">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-cyan-500/20 text-cyan-300 ring-1 ring-cyan-500/40">
              <Compass className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-sm font-bold tracking-tight text-white sm:text-base">
                Investigation Flow — STL Decomposition &amp; Trend Detection
              </h2>
              <p className="text-xs text-slate-400">
                Location: <span className="font-semibold text-slate-200">{pointA.name}</span> · Variable:{" "}
                <span className="font-semibold text-cyan-300">
                  {metadata.parameter_name} ({metadata.parameter_code})
                </span>{" "}
                [{metadata.unit}] · Window:{" "}
                <span className="font-mono font-semibold text-slate-200">
                  {draftStart}–{draftEnd}
                </span>{" "}
                ({primary_stats.observation_months} monthly observations)
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-700 bg-slate-950 px-2.5 py-1 text-xs font-medium text-slate-300">
              <span className="h-2 w-2 rounded-full bg-cyan-400" />
              Source: {investigation.response.primary_provenance?.source_name ?? metadata.mission_source}
            </span>
            <span className="rounded-full border border-slate-700 bg-slate-950 px-2.5 py-1 font-mono text-xs text-cyan-300">
              {(investigation.response.dataset_tag ?? investigation.response.data_status).toUpperCase()}
            </span>
            {onOpenDossier && (
              <button
                type="button"
                onClick={onOpenDossier}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1 text-[11px] font-semibold text-slate-200 transition hover:border-cyan-400 hover:text-white"
              >
                <Radio className="h-3 w-3 text-cyan-400" />
                Print / Save PDF Dossier
              </button>
            )}
          </div>
        </div>

        {/* 3 Step Investigation Tabs */}
        <div className="mt-3 grid grid-cols-1 gap-2.5 sm:grid-cols-3">
          <button
            type="button"
            onClick={() => setChartMode("raw")}
            className={`flex flex-col rounded-xl border p-3 text-left transition ${
              chartMode === "raw"
                ? "border-cyan-400 bg-cyan-500/15 shadow-sm shadow-cyan-500/20"
                : "border-slate-800 bg-slate-950/60 hover:border-slate-700 hover:bg-slate-950"
            }`}
          >
            <div className="flex items-center justify-between">
              <span
                className={`text-xs font-bold uppercase tracking-wider ${
                  chartMode === "raw" ? "text-cyan-300" : "text-slate-400"
                }`}
              >
                Phase 1: Raw Monthly Signal
              </span>
              <span className="rounded bg-slate-800 px-1.5 py-0.5 text-xs font-mono text-slate-300">
                ±{primary_stats.seasonal_amplitude} {metadata.unit}
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-300">
              Inspect recurring seasonal cycle vs natural noise across {primary_stats.observation_years} years.
            </p>
          </button>

          <button
            type="button"
            onClick={() => setChartMode("deseasonalized")}
            className={`flex flex-col rounded-xl border p-3 text-left transition ${
              chartMode === "deseasonalized"
                ? "border-cyan-400 bg-cyan-500/15 shadow-sm shadow-cyan-500/20"
                : "border-slate-800 bg-slate-950/60 hover:border-slate-700 hover:bg-slate-950"
            }`}
          >
            <div className="flex items-center justify-between">
              <span
                className={`text-xs font-bold uppercase tracking-wider ${
                  chartMode === "deseasonalized" ? "text-cyan-300" : "text-slate-400"
                }`}
              >
                Phase 2: Strip Seasonality (STL)
              </span>
              <span className="rounded bg-emerald-950/80 px-1.5 py-0.5 text-xs font-mono font-bold text-emerald-300">
                {primary_stats.variance_reduction_pct}% stripped
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-300">
              Isolate deseasonalized anomalies, Sen&apos;s slope, and 95% confidence bounds.
            </p>
          </button>

          <button
            type="button"
            disabled={!teleconnection.enabled || !comparison_series}
            onClick={() => setChartMode("teleconnection")}
            className={`flex flex-col rounded-xl border p-3 text-left transition ${
              !teleconnection.enabled || !comparison_series
                ? "cursor-not-allowed border-slate-800/50 bg-slate-950/30 opacity-60"
                : chartMode === "teleconnection"
                  ? "border-indigo-400 bg-indigo-500/20 shadow-sm shadow-indigo-500/20"
                  : "border-slate-800 bg-slate-950/60 hover:border-slate-700 hover:bg-slate-950"
            }`}
          >
            <div className="flex items-center justify-between">
              <span
                className={`text-xs font-bold uppercase tracking-wider ${
                  chartMode === "teleconnection" ? "text-indigo-300" : "text-slate-400"
                }`}
              >
                Phase 3: Regional Teleconnection
              </span>
              {rVal !== null && rVal !== undefined && (
                <span className="rounded bg-indigo-950/80 px-1.5 py-0.5 text-xs font-mono font-bold text-indigo-300">
                  r = {rVal.toFixed(2)}
                </span>
              )}
            </div>
            <p className="mt-1 text-xs text-slate-300">
              {pointB
                ? `Compare against ${pointB.name} to test inter-regional climate teleconnections.`
                : "Place Marker B on the map to unlock dual-region cross-correlation."}
            </p>
          </button>
        </div>
      </div>

      {/* Upfront Research Finding: Answering the Core Trend Question */}
      <UpfrontTrendSummary
        investigation={investigation}
        pointA={pointA}
        pointB={pointB}
        windowRange={windowRange}
        variant="dark"
      />

      {/* Main Analysis Grid */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        {/* Left 8 cols: Decomposition Chart + Interactive Window Controls */}
        <div className="flex flex-col gap-3 rounded-2xl border border-slate-800 bg-slate-900/70 p-4 shadow-xl lg:col-span-8">
          {/* Chart Header with Explicit Title, Subtitle, Date Range and Units */}
          <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-800 pb-3">
            <div>
              <div className="flex items-center gap-2">
                <Layers className="h-4 w-4 text-cyan-400" />
                <h3 className="text-base font-extrabold text-white">
                  {chartMode === "raw"
                    ? `Raw Observations & 12-Month Seasonal Cycle: ${metadata.parameter_name}`
                    : chartMode === "deseasonalized"
                      ? `Deseasonalized Anomalies & Sen's Slope: ${metadata.parameter_name}`
                      : `Dual-Region Anomaly Comparison: ${pointA.name} vs. ${pointB?.name || "Region B"}`}
                </h3>
              </div>
              <p className="mt-0.5 text-xs text-slate-400">
                {chartMode === "raw" &&
                  `Showing ${primary_stats.observation_months} continuous monthly points (${metadata.unit}) and fitted periodic seasonal swing.`}
                {chartMode === "deseasonalized" &&
                  `STL decomposition stripped ${primary_stats.variance_reduction_pct}% seasonal variance. Shaded band shows 95% Confidence Interval.`}
                {chartMode === "teleconnection" &&
                  `Dual normalized anomalies (${metadata.unit}) across ${draftStart}–${draftEnd} | Pearson cross-correlation r = ${rVal !== null && rVal !== undefined ? rVal.toFixed(3) : "N/A"}.`}
              </p>
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-950 px-2.5 py-1 text-right">
              <span className="block text-xs uppercase tracking-wider text-slate-400">Date Range</span>
              <span className="font-mono text-xs font-bold text-cyan-300">
                {draftStart}–{draftEnd} ({draftEnd - draftStart + 1} yrs)
              </span>
            </div>
          </div>

          {/* Mode-Specific Narrative Banner (Explaining Why Seasonality Matters) */}
          {chartMode === "raw" && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-500/30 bg-amber-950/25 px-3.5 py-2.5 text-xs">
              <div className="space-y-0.5">
                <p className="font-semibold text-amber-200">
                  Notice: Recurring seasonal swings of &plusmn;{primary_stats.seasonal_amplitude} {metadata.unit} mask
                  the long-term physical trend
                </p>
                <p className="text-xs text-amber-100/80">
                  Raw seasonal Mann-Kendall p-value ={" "}
                  <span className="font-mono font-bold">{formatPValue(primary_stats.raw_p_value)}</span> vs.
                  Deseasonalized STL p-value ={" "}
                  <span className="font-mono font-bold text-cyan-300">{formatPValue(primary_stats.p_value)}</span>.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setChartMode("deseasonalized")}
                className="inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-cyan-400 to-emerald-400 px-3.5 py-2 text-xs font-bold text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:brightness-110"
              >
                Proceed to Phase 2: Strip Seasonality
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>
          )}

          {chartMode === "deseasonalized" && (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-cyan-500/30 bg-cyan-950/25 px-3.5 py-2 text-xs">
              <p className="text-cyan-100">
                <span className="font-semibold text-cyan-300">STL Seasonal Cycle Removed:</span> Total variance
                reduced by{" "}
                <span className="font-mono font-bold text-emerald-300">{primary_stats.variance_reduction_pct}%</span>,
                revealing underlying multi-decade slope:{" "}
                <span className="font-mono font-bold text-white">
                  {primary_stats.sens_slope_per_decade >= 0 ? "+" : ""}
                  {primary_stats.sens_slope_per_decade} {metadata.unit}/decade
                </span>{" "}
                ({dirInfo.label}).
              </p>
              <button
                type="button"
                onClick={() => setActiveExplainKey("stl_variance")}
                className="inline-flex items-center gap-1 text-xs font-medium text-cyan-300 underline hover:text-cyan-200"
              >
                <HelpCircle className="h-3 w-3" />
                How STL works
              </button>
            </div>
          )}

          {chartMode === "teleconnection" && pointB && (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-indigo-500/30 bg-indigo-950/30 px-3.5 py-2 text-xs">
              <p className="text-indigo-100">
                <span className="font-semibold text-cyan-300">Primary (A): {pointA.name}</span> (
                {primary_stats.sens_slope_per_decade >= 0 ? "+" : ""}
                {primary_stats.sens_slope_per_decade}/dec) vs.{" "}
                <span className="font-semibold text-rose-300">Comparison (B): {pointB.name}</span> (
                {(teleconnection.comparison_sens_slope_per_decade ?? 0) >= 0 ? "+" : ""}
                {teleconnection.comparison_sens_slope_per_decade}/dec)
              </p>
              {rInterpret && (
                <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${rInterpret.cls}`}>
                  r = {rVal !== null && rVal !== undefined ? rVal.toFixed(2) : "N/A"} · {rInterpret.label}
                </span>
              )}
            </div>
          )}

          {/* Recharts Visualization Area */}
          <div className="relative h-[340px] w-full sm:h-[380px]">
            {loading && (
              <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-2 rounded-xl bg-slate-950/75 backdrop-blur-[2px]">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent" />
                <span className="rounded-lg border border-cyan-500/30 bg-slate-900 px-3 py-1.5 text-xs font-semibold text-cyan-200 shadow-lg">
                  Recomputing STL Decomposition &amp; Mann-Kendall ({draftStart}–{draftEnd})...
                </span>
              </div>
            )}

            {chartData.length === 0 ? (
              <div className="flex h-full w-full flex-col items-center justify-center gap-2 rounded-xl border border-slate-800 bg-slate-950/50 p-6 text-center text-xs text-slate-400">
                <AlertCircle className="h-8 w-8 text-amber-400" />
                <p className="font-bold text-slate-200">No time-series observations available</p>
                <p className="max-w-md">
                  There are no monthly data points for {metadata.parameter_name} over {draftStart}–{draftEnd}. Try
                  widening the observation window slider or selecting a different preset.
                </p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                {chartMode === "raw" ? (
                  <ComposedChart data={chartData} margin={{ top: 12, right: 20, left: 10, bottom: 24 }}>
                    <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                    <XAxis
                      dataKey="timestamp"
                      tick={{ fill: "#94a3b8", fontSize: 11 }}
                      minTickGap={36}
                      label={{
                        value: "Observation Date (Year-Month)",
                        position: "insideBottom",
                        offset: -14,
                        fill: "#94a3b8",
                        fontSize: 11,
                      }}
                    />
                    <YAxis
                      tick={{ fill: "#94a3b8", fontSize: 11 }}
                      width={64}
                      domain={["auto", "auto"]}
                      label={{
                        value: `${metadata.parameter_name} (${metadata.unit})`,
                        angle: -90,
                        position: "insideLeft",
                        fill: "#38bdf8",
                        fontSize: 11,
                        offset: -4,
                      }}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#020617",
                        borderColor: "#334155",
                        borderRadius: "10px",
                        fontSize: "12px",
                      }}
                      formatter={(val: any, name: string) => [
                        `${typeof val === "number" ? val.toFixed(3) : val} ${metadata.unit}`,
                        name,
                      ]}
                    />
                    <Legend
                      verticalAlign="top"
                      height={36}
                      wrapperStyle={{ fontSize: "11px", color: "#94a3b8" }}
                    />
                    <Line
                      type="monotone"
                      dataKey="raw"
                      name={`Raw Monthly Data (${metadata.unit})`}
                      stroke="#38bdf8"
                      strokeWidth={1.8}
                      dot={false}
                      isAnimationActive={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="seasonalShifted"
                      name="Fitted 12-Month Seasonal Cycle (centered on mean)"
                      stroke="#a78bfa"
                      strokeWidth={1.5}
                      strokeDasharray="4 4"
                      dot={false}
                      isAnimationActive={false}
                    />
                  </ComposedChart>
                ) : chartMode === "deseasonalized" ? (
                  <ComposedChart data={chartData} margin={{ top: 12, right: 20, left: 10, bottom: 24 }}>
                    <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                    <XAxis
                      dataKey="timestamp"
                      tick={{ fill: "#94a3b8", fontSize: 11 }}
                      minTickGap={36}
                      label={{
                        value: "Observation Date (Year-Month)",
                        position: "insideBottom",
                        offset: -14,
                        fill: "#94a3b8",
                        fontSize: 11,
                      }}
                    />
                    <YAxis
                      tick={{ fill: "#94a3b8", fontSize: 11 }}
                      width={64}
                      domain={["auto", "auto"]}
                      label={{
                        value: `Anomaly Departure (${metadata.unit})`,
                        angle: -90,
                        position: "insideLeft",
                        fill: "#38bdf8",
                        fontSize: 11,
                        offset: -4,
                      }}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#020617",
                        borderColor: "#334155",
                        borderRadius: "10px",
                        fontSize: "12px",
                      }}
                      formatter={(val: any, name: string) => {
                        if (Array.isArray(val)) {
                          return [`[${val[0].toFixed(3)}, ${val[1].toFixed(3)}] ${metadata.unit}`, name];
                        }
                        return [`${typeof val === "number" ? val.toFixed(3) : val} ${metadata.unit}`, name];
                      }}
                    />
                    <Legend
                      verticalAlign="top"
                      height={36}
                      wrapperStyle={{ fontSize: "11px", color: "#94a3b8" }}
                    />
                    <ReferenceLine y={0} stroke="#475569" strokeDasharray="3 3" />
                    <Area
                      type="monotone"
                      dataKey="ciRange"
                      name="95% Confidence Band (OLS mean-response)"
                      stroke="none"
                      fill="#22d3ee"
                      fillOpacity={0.18}
                      isAnimationActive={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="anomaly"
                      name={`Deseasonalized Anomaly (${metadata.unit})`}
                      stroke="#38bdf8"
                      strokeWidth={1.5}
                      dot={false}
                      isAnimationActive={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="trend"
                      name={`Sen's Slope Trend Fit (${primary_stats.sens_slope_per_decade >= 0 ? "+" : ""}${primary_stats.sens_slope_per_decade} ${metadata.unit}/dec, ${primary_stats.is_significant ? "p < 0.05" : "p ≥ 0.05"})`}
                      stroke={primary_stats.is_significant ? "#34d399" : "#facc15"}
                      strokeWidth={2.5}
                      dot={false}
                      isAnimationActive={false}
                    />
                  </ComposedChart>
                ) : (
                  <ComposedChart data={chartData} margin={{ top: 12, right: 24, left: 10, bottom: 24 }}>
                    <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                    <XAxis
                      dataKey="timestamp"
                      tick={{ fill: "#94a3b8", fontSize: 11 }}
                      minTickGap={36}
                      label={{
                        value: "Observation Date (Year-Month)",
                        position: "insideBottom",
                        offset: -14,
                        fill: "#94a3b8",
                        fontSize: 11,
                      }}
                    />
                    <YAxis
                      yAxisId="left"
                      tick={{ fill: "#38bdf8", fontSize: 11 }}
                      width={60}
                      domain={["auto", "auto"]}
                      label={{
                        value: `${pointA.name} (${metadata.unit})`,
                        angle: -90,
                        position: "insideLeft",
                        fill: "#38bdf8",
                        fontSize: 11,
                        offset: -4,
                      }}
                    />
                    <YAxis
                      yAxisId="right"
                      orientation="right"
                      tick={{ fill: "#fb7185", fontSize: 11 }}
                      width={60}
                      domain={["auto", "auto"]}
                      label={{
                        value: `${pointB?.name || "Region B"} (${metadata.unit})`,
                        angle: 90,
                        position: "insideRight",
                        fill: "#fb7185",
                        fontSize: 11,
                        offset: 4,
                      }}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#020617",
                        borderColor: "#334155",
                        borderRadius: "10px",
                        fontSize: "12px",
                      }}
                      formatter={(val: any, name: string) => [
                        `${typeof val === "number" ? val.toFixed(3) : val} ${metadata.unit}`,
                        name,
                      ]}
                    />
                    <Legend
                      verticalAlign="top"
                      height={36}
                      wrapperStyle={{ fontSize: "11px", color: "#94a3b8" }}
                    />
                    <ReferenceLine yAxisId="left" y={0} stroke="#334155" strokeDasharray="3 3" />
                    <Line
                      yAxisId="left"
                      type="monotone"
                      dataKey="anomaly"
                      name={`Region A: ${pointA.name} Anomaly`}
                      stroke="#38bdf8"
                      strokeWidth={1.4}
                      dot={false}
                      isAnimationActive={false}
                    />
                    <Line
                      yAxisId="left"
                      type="monotone"
                      dataKey="trend"
                      name="Region A Linear Fit"
                      stroke="#22d3ee"
                      strokeWidth={2.4}
                      strokeDasharray="5 3"
                      dot={false}
                      isAnimationActive={false}
                    />
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="compAnomaly"
                      name={`Region B: ${pointB?.name || "Comparison"} Anomaly`}
                      stroke="#fb7185"
                      strokeWidth={1.4}
                      dot={false}
                      isAnimationActive={false}
                    />
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="compTrend"
                      name="Region B Linear Fit"
                      stroke="#f43f5e"
                      strokeWidth={2.4}
                      strokeDasharray="5 3"
                      dot={false}
                      isAnimationActive={false}
                    />
                  </ComposedChart>
                )}
              </ResponsiveContainer>
            )}
          </div>

          {/* Interactive Window Length Slider & Presets */}
          <div className="flex flex-col gap-3 rounded-xl border border-slate-800 bg-slate-950/70 p-3.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-xs font-semibold text-slate-200">
                <CalendarRange className="h-4 w-4 text-cyan-400" />
                <span>Adjust Observation Window:</span>
                <span className="rounded bg-slate-800 px-2.5 py-0.5 font-mono text-cyan-300">
                  {draftStart} – {draftEnd} ({draftEnd - draftStart + 1} yrs · {primary_stats.observation_months} mos)
                </span>
              </div>

              {/* Window Presets for Scientific Comparison */}
              <div className="flex flex-wrap items-center gap-1.5 text-xs">
                {[
                  { label: "5-Yr Test (2018–2022)", range: [2018, 2022] as [number, number] },
                  { label: "Latest 5-Yr (2021–2025)", range: [2021, 2025] as [number, number] },
                  { label: "15-Yr (2010–2025)", range: [2010, 2025] as [number, number] },
                  { label: "35-Yr Baseline (1990–2025)", range: [1990, 2025] as [number, number] },
                  { label: "Full Era (1981–2025)", range: [1981, 2025] as [number, number] },
                ].map((preset) => {
                  const active = draftStart === preset.range[0] && draftEnd === preset.range[1];
                  return (
                    <button
                      key={preset.label}
                      type="button"
                      onClick={() => {
                        setDraftStart(preset.range[0]);
                        setDraftEnd(preset.range[1]);
                        onChangeWindow(preset.range);
                      }}
                      className={`rounded-lg px-2.5 py-1 font-medium transition ${
                        active
                          ? "bg-cyan-500 font-bold text-slate-950"
                          : "bg-slate-800 text-slate-300 hover:bg-slate-700"
                      }`}
                    >
                      {preset.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="flex items-center gap-2.5 text-xs text-slate-300">
                <span className="w-20 shrink-0 font-medium">Start: {draftStart}</span>
                <input
                  type="range"
                  min={1981}
                  max={2022}
                  value={draftStart}
                  onChange={(e) => applyDraftStart(Number(e.target.value))}
                  aria-label="Start year slider"
                  className="w-full cursor-pointer accent-cyan-400"
                />
              </label>
              <label className="flex items-center gap-2.5 text-xs text-slate-300">
                <span className="w-20 shrink-0 font-medium">End: {draftEnd}</span>
                <input
                  type="range"
                  min={1984}
                  max={2025}
                  value={draftEnd}
                  onChange={(e) => applyDraftEnd(Number(e.target.value))}
                  aria-label="End year slider"
                  className="w-full cursor-pointer accent-cyan-400"
                />
              </label>
            </div>
            <p className="text-xs text-slate-400">
              <span className="font-semibold text-cyan-300">Why window length matters:</span> Short 5-year windows are
              frequently dominated by short-term interannual variability (ENSO, NAO) where p &ge; 0.05. Multi-decade
              windows (30+ years) are mandatory in climate and Earth observation science to confirm long-term signals.
            </p>
          </div>
        </div>

        {/* Right 4 cols: Detective Verdict Scorecard */}
        <aside className="flex flex-col gap-3 rounded-2xl border border-slate-800 bg-slate-900/70 p-4 shadow-xl lg:col-span-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-cyan-400" />
              <h3 className="text-sm font-bold text-white">Detective Verdict Scorecard</h3>
            </div>
            <span className="font-mono text-xs text-slate-400">
              Significance threshold: &alpha; = 0.05
            </span>
          </div>

          {/* High-Contrast Significance Verdict Banner */}
          {primary_stats.is_significant ? (
            <div className="flex items-start gap-2.5 rounded-xl border border-emerald-500/40 bg-emerald-950/40 p-3 text-emerald-100">
              <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-400" />
              <div>
                <p className="text-xs font-extrabold tracking-wide text-emerald-300">
                  STATISTICALLY SIGNIFICANT TREND (p &lt; 0.05)
                </p>
                <p className="mt-0.5 text-xs text-emerald-100/90 leading-relaxed">
                  Confirmed on deseasonalized anomalies across {primary_stats.observation_years} years (p ={" "}
                  {formatPValue(primary_stats.p_value)}). The probability that this trend occurred by random chance is
                  less than 5%.
                </p>
              </div>
            </div>
          ) : (
            <div className="flex items-start gap-2.5 rounded-xl border border-amber-500/40 bg-amber-950/40 p-3 text-amber-100">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
              <div>
                <p className="text-xs font-extrabold tracking-wide text-amber-300">
                  {yearsNeeded >= 90
                    ? "NATURAL NOISE / NO DETECTABLE SLOPE (p ≥ 0.05)"
                    : `NOT YET SIGNIFICANT — NEEDS ~${yearsNeeded} MORE YEARS`}
                </p>
                <p className="mt-0.5 text-xs text-amber-100/90 leading-relaxed">
                  Natural variability masks the trend over this {primary_stats.observation_years}-year window (p ={" "}
                  {formatPValue(primary_stats.p_value)}). Statistical evidence is insufficient to reject the null
                  hypothesis.
                </p>
              </div>
            </div>
          )}

          {/* Sen's Slope Rate Cards with Plain-Language Directions */}
          <div className="grid grid-cols-2 gap-2.5">
            <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-400">Sen&apos;s Slope / Year</span>
                <button
                  type="button"
                  onClick={() => setActiveExplainKey("sens_slope")}
                  className="text-slate-400 hover:text-cyan-300"
                  aria-label="Explain Sen's slope"
                >
                  <HelpCircle className="h-3.5 w-3.5" />
                </button>
              </div>
              <div className="mt-1 flex items-center gap-1.5">
                {primary_stats.sens_slope_per_year >= 0 ? (
                  <TrendingUp className="h-4 w-4 text-emerald-400" />
                ) : (
                  <TrendingDown className="h-4 w-4 text-amber-400" />
                )}
                <span className="font-mono text-base font-bold text-white">
                  {primary_stats.sens_slope_per_year >= 0 ? "+" : ""}
                  {primary_stats.sens_slope_per_year}
                </span>
              </div>
              <p className="mt-0.5 text-xs font-medium text-cyan-300">
                {metadata.unit}/yr · {dirInfo.label}
              </p>
              {primary_stats.sens_slope_ci_lower !== undefined && primary_stats.sens_slope_ci_upper !== undefined && (
                <p className="mt-1 font-mono text-xs text-slate-400">
                  95% CI: [{primary_stats.sens_slope_ci_lower >= 0 ? "+" : ""}
                  {primary_stats.sens_slope_ci_lower}, {primary_stats.sens_slope_ci_upper >= 0 ? "+" : ""}
                  {primary_stats.sens_slope_ci_upper}]
                </p>
              )}
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-3">
              <span className="text-xs font-medium text-slate-400">Sen&apos;s Slope / Decade</span>
              <p className="mt-1 font-mono text-base font-bold text-cyan-300">
                {primary_stats.sens_slope_per_decade >= 0 ? "+" : ""}
                {primary_stats.sens_slope_per_decade}
              </p>
              <p className="mt-0.5 text-xs text-slate-400">
                {metadata.unit}/decade
              </p>
              <p className="mt-1 text-xs text-slate-400 line-clamp-1">
                {dirInfo.description}
              </p>
            </div>
          </div>

          {/* Statistical Metrics Grid with Accessible Plain-Language Explanations */}
          <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-xs">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-1.5 text-xs font-semibold text-slate-300">
              <span>Statistical Validation Metrics</span>
              <span className="text-xs text-slate-400">Click &ldquo;?&rdquo; for guide</span>
            </div>
            <div className="mt-2.5 grid grid-cols-2 gap-2.5">
              <div className="rounded-lg bg-slate-900/60 p-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-400">Mann-Kendall &tau;</span>
                  <button
                    type="button"
                    onClick={() => setActiveExplainKey("mk_tau")}
                    className="text-slate-400 hover:text-cyan-300"
                    aria-label="Explain Mann-Kendall Tau"
                  >
                    <HelpCircle className="h-3 w-3" />
                  </button>
                </div>
                <p className="font-mono font-semibold text-slate-100">{primary_stats.mann_kendall_tau}</p>
                <p className="text-xs text-slate-400">Monotonic direction</p>
              </div>

              <div className="rounded-lg bg-slate-900/60 p-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-400">Z-Score</span>
                  <button
                    type="button"
                    onClick={() => setActiveExplainKey("z_score")}
                    className="text-slate-400 hover:text-cyan-300"
                    aria-label="Explain Z-score"
                  >
                    <HelpCircle className="h-3 w-3" />
                  </button>
                </div>
                <p className="font-mono font-semibold text-slate-100">{primary_stats.z_score}</p>
                <p className="text-xs text-slate-400">&gt; &plusmn;1.96 = 95% conf.</p>
              </div>

              <div className="rounded-lg bg-slate-900/60 p-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-400">Deseasonalized p</span>
                  <button
                    type="button"
                    onClick={() => setActiveExplainKey("p_value")}
                    className="text-slate-400 hover:text-cyan-300"
                    aria-label="Explain p-value"
                  >
                    <HelpCircle className="h-3 w-3" />
                  </button>
                </div>
                <p
                  className={`font-mono font-bold ${
                    primary_stats.is_significant ? "text-emerald-400" : "text-amber-300"
                  }`}
                >
                  {formatPValue(primary_stats.p_value)}
                </p>
                <p className="text-xs text-slate-400">
                  {primary_stats.is_significant ? "Significant" : "Inconclusive"}
                </p>
              </div>

              <div className="rounded-lg bg-slate-900/60 p-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-400">Raw Seasonal p</span>
                  <button
                    type="button"
                    onClick={() => setActiveExplainKey("raw_vs_deseasonalized")}
                    className="text-slate-400 hover:text-cyan-300"
                    aria-label="Explain raw vs deseasonalized p"
                  >
                    <HelpCircle className="h-3 w-3" />
                  </button>
                </div>
                <p className="font-mono font-semibold text-slate-300">{formatPValue(primary_stats.raw_p_value)}</p>
                <p className="text-xs text-slate-400">Before seasonal removal</p>
              </div>

              <div className="rounded-lg bg-slate-900/60 p-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-400">Student&apos;s t p</span>
                  <button
                    type="button"
                    onClick={() => setActiveExplainKey("p_value")}
                    className="text-slate-400 hover:text-cyan-300"
                    aria-label="Explain t-test p"
                  >
                    <HelpCircle className="h-3 w-3" />
                  </button>
                </div>
                <p className="font-mono font-semibold text-slate-100">
                  {formatPValue(primary_stats.t_test_p_value)}
                </p>
                <p className="text-xs text-slate-400">Parametric check</p>
              </div>

              <div className="rounded-lg bg-slate-900/60 p-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-400">STL Variance Cut</span>
                  <button
                    type="button"
                    onClick={() => setActiveExplainKey("stl_variance")}
                    className="text-slate-400 hover:text-cyan-300"
                    aria-label="Explain STL variance"
                  >
                    <HelpCircle className="h-3 w-3" />
                  </button>
                </div>
                <p className="font-mono font-semibold text-cyan-300">
                  {primary_stats.variance_reduction_pct}%
                </p>
                <p className="text-xs text-slate-400">Seasonal noise removed</p>
              </div>
            </div>

            {/* Active Metric Explanation Callout */}
            {activeExplain && (
              <div className="mt-3 rounded-lg border border-cyan-500/30 bg-cyan-950/40 p-2.5 text-xs text-cyan-100">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-cyan-300">{activeExplain.title}</span>
                  <button
                    type="button"
                    onClick={() => setActiveExplainKey(null)}
                    className="text-xs text-slate-400 hover:text-white"
                  >
                    Close
                  </button>
                </div>
                <p className="mt-1 text-slate-200">{activeExplain.summary}</p>
                <p className="mt-1 font-mono text-xs text-cyan-200">Rule: {activeExplain.formulaOrRule}</p>
                <p className="mt-1 text-xs text-slate-300">How to interpret: {activeExplain.interpretation}</p>
              </div>
            )}

            {!primary_stats.is_significant && (
              <p className="mt-2.5 border-t border-slate-800/80 pt-2 text-xs leading-relaxed text-amber-200/85">
                Note: p &ge; 0.05 indicates insufficient statistical evidence to reject the null hypothesis over this
                window—it does not prove the absence of physical change.
              </p>
            )}
          </div>

          {/* Observation Window Horizon & Statistical Power Progress Bar */}
          <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
            <div className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-1.5 font-semibold text-slate-200">
                <Clock className="h-3.5 w-3.5 text-cyan-400" />
                Statistical Power Assessment
              </span>
              <button
                type="button"
                onClick={() => setActiveExplainKey("obs_horizon")}
                className="text-slate-400 hover:text-cyan-300"
                aria-label="Explain observation horizon"
              >
                <HelpCircle className="h-3 w-3" />
              </button>
            </div>
            <div className="mt-2 flex items-center justify-between text-xs">
              <span className="text-slate-400">Observation Progress</span>
              <span className="font-mono font-bold text-cyan-300">{horizonPct}%</span>
            </div>
            <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-slate-800">
              <div
                className={`h-full rounded-full transition-all duration-300 ${
                  primary_stats.is_significant ? "bg-emerald-400" : "bg-amber-400"
                }`}
                style={{ width: `${horizonPct}%` }}
              />
            </div>
            <p className="mt-2 text-xs leading-relaxed text-slate-400">
              {primary_stats.is_significant
                ? `95% statistical confidence threshold reached within ${obsYears} years of monthly data.`
                : (primary_stats.estimated_additional_observation_years ?? yearsNeeded) >= 90
                  ? "Slope is near zero; extended observations cannot resolve a monotonic trend."
                  : `Power estimate: ~${primary_stats.estimated_additional_observation_years ?? yearsNeeded} additional years of monthly data required (illustrative statistical power estimate assuming stationary slope and variance, not a forecast).`}
            </p>
          </div>

          {/* Regional Anomaly Comparison Summary */}
          <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-xs font-semibold text-slate-200">
                <Radio className="h-3.5 w-3.5 text-indigo-400" />
                Regional Teleconnection (A vs. B)
              </span>
              <button
                type="button"
                onClick={() => setActiveExplainKey("cross_correlation")}
                className="text-slate-400 hover:text-cyan-300"
                aria-label="Explain cross-correlation"
              >
                <HelpCircle className="h-3 w-3" />
              </button>
            </div>

            {teleconnection.enabled && pointB ? (
              <div className="mt-2 space-y-1.5 text-xs">
                {rInterpret && (
                  <span className={`inline-block rounded-full border px-2.5 py-0.5 font-semibold ${rInterpret.cls}`}>
                    {rInterpret.label}
                  </span>
                )}
                <p className="text-slate-300">
                  <span className="font-semibold text-indigo-300">{pointB.name}:</span>{" "}
                  {(teleconnection.comparison_sens_slope_per_year ?? 0) >= 0 ? "+" : ""}
                  {teleconnection.comparison_sens_slope_per_year} {metadata.unit}/yr (
                  {teleconnection.comparison_is_significant ? "significant" : "not significant"}, p ={" "}
                  {formatPValue(teleconnection.comparison_p_value)})
                </p>
                <p className="text-xs text-slate-400">
                  Cross-correlation r = {rVal !== null && rVal !== undefined ? rVal.toFixed(3) : "N/A"}. Notice:
                  correlation measures statistical co-variation of deseasonalized anomalies and does not by itself
                  establish physical causation.
                </p>
              </div>
            ) : (
              <p className="mt-1.5 text-xs text-slate-400">
                To test global teleconnections, return to the map and click &ldquo;Set Comparison Region (B)&rdquo; on a
                distant Earth system.
              </p>
            )}
          </div>

          {/* Dataset Provenance & Data-Quality Panel */}
          <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-xs">
            <p className="font-semibold text-slate-200">Dataset Provenance &amp; Data Quality</p>
            <dl className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1.5 text-slate-300">
              <div>
                <dt className="text-xs text-slate-400">Source / Mission</dt>
                <dd className="font-medium text-slate-200">
                  {investigation.response.primary_provenance?.source_name ?? metadata.mission_source}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-slate-400">Data Type &amp; Tag</dt>
                <dd className="font-mono text-xs text-cyan-300">
                  {investigation.response.primary_provenance?.data_type ?? metadata.data_type ?? "Reanalysis"} ·{" "}
                  {(investigation.response.dataset_tag ?? investigation.response.data_status).toUpperCase()}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-slate-400">Observation Window</dt>
                <dd className="font-mono text-xs">
                  {investigation.response.primary_provenance
                    ? `${investigation.response.primary_provenance.start_date} → ${investigation.response.primary_provenance.end_date}`
                    : `${primary_stats.observation_months} months`}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-slate-400">Valid / Missing Data</dt>
                <dd className="font-mono text-xs">
                  {primary_stats.valid_months ?? primary_stats.observation_months} valid ·{" "}
                  {(primary_stats.missing_pct ?? 0).toFixed(1)}% missing
                </dd>
              </div>
              <div className="col-span-2">
                <dt className="text-xs text-slate-400">Spatial Resolution &amp; Grid Cell</dt>
                <dd className="text-xs text-slate-300">
                  {metadata.unit} ({investigation.response.primary_provenance?.spatial_resolution ?? metadata.resolution}) ·{" "}
                  {investigation.response.primary_provenance && investigation.response.primary_provenance.fallback_distance_km > 0
                    ? `Fallback source at ${investigation.response.primary_provenance.source_lat.toFixed(2)}°, ${investigation.response.primary_provenance.source_lon.toFixed(2)}° (${investigation.response.primary_provenance.fallback_distance_km} km away)`
                    : `Exact requested coordinates (${investigation.response.primary_provenance?.retrieval_status ?? investigation.response.data_status})`}
                </dd>
              </div>
              <div className="col-span-2">
                <dt className="text-[10px] text-slate-400">Provenance Note</dt>
                <dd className="text-[10px] text-slate-300">
                {investigation.response.primary_provenance?.provenance_note ??
                  "Interpretation is limited to the supplied dataset metadata and processing window."}
                {investigation.response.primary_provenance?.access_url ? (
                  <>
                    {" "}
                    <span className="font-mono text-cyan-300">
                      Access endpoint recorded in export.
                    </span>
                  </>
                ) : null}
                </dd>
              </div>
            </dl>
          </div>

          {/* References */}
          <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-xs text-slate-400">
            <p className="font-semibold text-slate-200">Scientific References</p>
            <p className="mt-1 text-xs leading-relaxed text-slate-400">
              {investigation.response.detective_brief.reference}
            </p>
          </div>
        </aside>
      </div>
    </section>
  );
}
