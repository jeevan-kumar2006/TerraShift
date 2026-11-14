import { useEffect, useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CalendarRange,
  CheckCircle2,
  Clock,
  Layers,
  Radio,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import type { GeoPoint, InvestigateResponse } from "./types";

type ChartMode = "raw" | "deseasonalized" | "teleconnection";

interface TrendLabProps {
  investigation: InvestigateResponse;
  pointA: GeoPoint;
  pointB: GeoPoint | null;
  windowRange: [number, number];
  onChangeWindow: (next: [number, number]) => void;
  loading: boolean;
}

function formatPValue(p: number | null | undefined): string {
  if (p === null || p === undefined) return "N/A";
  if (p < 0.0001) return "< 0.0001";
  return p.toFixed(4);
}

function getSlopeDirectionLabel(parameter: string, slope: number): { label: string; positiveIsAlert: boolean } {
  const code = parameter.toUpperCase();
  if (code === "T2M") {
    return { label: slope >= 0 ? "Warming" : "Cooling", positiveIsAlert: true };
  }
  if (code === "PS") {
    return { label: slope >= 0 ? "Rising Pressure" : "Falling Pressure", positiveIsAlert: false };
  }
  return { label: slope >= 0 ? "Wetting" : "Drying", positiveIsAlert: false };
}

export default function TrendLab({
  investigation,
  pointA,
  pointB,
  windowRange,
  onChangeWindow,
  loading,
}: TrendLabProps) {
  const [chartMode, setChartMode] = useState<ChartMode>("raw");
  const [draftStart, setDraftStart] = useState<number>(windowRange[0]);
  const [draftEnd, setDraftEnd] = useState<number>(windowRange[1]);

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

  // If teleconnection mode was active and Marker B is cleared, drop back cleanly
  useEffect(() => {
    if (chartMode === "teleconnection" && (!teleconnection.enabled || !comparison_series)) {
      setChartMode("deseasonalized");
    }
  }, [chartMode, teleconnection.enabled, comparison_series]);

  const chartData = useMemo(() => {
    const rawValid = primary_series.raw_values.filter((v): v is number => v !== null);
    const rawMean = rawValid.length ? rawValid.reduce((a, b) => a + b, 0) / rawValid.length : 0;

    return primary_series.timestamps.map((ts, idx) => {
      const ciLow = primary_series.ci_lower[idx];
      const ciHigh = primary_series.ci_upper[idx];
      const seas = primary_series.seasonal_cycle[idx];
      const compAnom =
        comparison_series && idx < comparison_series.deseasonalized_anomalies.length
          ? comparison_series.deseasonalized_anomalies[idx]
          : null;
      const compTrend =
        comparison_series && idx < comparison_series.trend_line.length
          ? comparison_series.trend_line[idx]
          : null;

      return {
        timestamp: ts,
        raw: primary_series.raw_values[idx],
        seasonalShifted: seas !== null ? Number((seas + rawMean).toFixed(4)) : null,
        anomaly: primary_series.deseasonalized_anomalies[idx],
        trend: primary_series.trend_line[idx],
        ciRange: ciLow !== null && ciHigh !== null ? [ciLow, ciHigh] : null,
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
    rVal === null
      ? null
      : rVal <= -0.25
        ? { label: "Inverse / Opposite Seesaw", cls: "bg-rose-500/15 text-rose-200 border-rose-500/40" }
        : rVal >= 0.25
          ? { label: "Synchronized Co-Movement", cls: "bg-emerald-500/15 text-emerald-200 border-emerald-500/40" }
          : { label: "Weak / Decoupled Coupling", cls: "bg-slate-800 text-slate-300 border-slate-700" };

  return (
    <section className="grid grid-cols-1 gap-4 lg:grid-cols-12">
      {/* Left 8 cols: Decomposition Chart + Window Length Slider */}
      <div className="flex flex-col gap-3 rounded-2xl border border-slate-800 bg-slate-900/70 p-4 shadow-xl lg:col-span-8">
        {/* Switcher Header */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-cyan-400" />
            <div>
              <h2 className="text-sm font-bold text-white">
                STL Decomposition Lab — {pointA.name}
              </h2>
              <p className="text-[11px] text-slate-400">
                {metadata.parameter_name} ({metadata.unit}) · {primary_stats.observation_months} monthly observations
              </p>
            </div>
          </div>

          <div className="flex flex-wrap rounded-xl border border-slate-800 bg-slate-950 p-1 text-xs">
            <button
              type="button"
              onClick={() => setChartMode("raw")}
              className={`rounded-lg px-3 py-1.5 font-medium transition ${
                chartMode === "raw"
                  ? "bg-cyan-500 text-slate-950 shadow"
                  : "text-slate-400 hover:text-slate-100"
              }`}
            >
              1. Raw Satellite Series
            </button>
            <button
              type="button"
              onClick={() => setChartMode("deseasonalized")}
              className={`rounded-lg px-3 py-1.5 font-medium transition ${
                chartMode === "deseasonalized"
                  ? "bg-cyan-500 text-slate-950 shadow"
                  : "text-slate-400 hover:text-slate-100"
              }`}
            >
              2. Deseasonalized Trend Lab
            </button>
            <button
              type="button"
              disabled={!teleconnection.enabled || !comparison_series}
              onClick={() => setChartMode("teleconnection")}
              className={`rounded-lg px-3 py-1.5 font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${
                chartMode === "teleconnection"
                  ? "bg-indigo-500 text-white shadow"
                  : "text-slate-400 hover:text-slate-100"
              }`}
            >
              3. Teleconnection Overlay
            </button>
          </div>
        </div>

        {/* Mode-Specific Narrative Banner (The "Why Seasonality Matters" Moment) */}
        {chartMode === "raw" && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-500/30 bg-amber-950/25 px-3.5 py-2.5 text-xs">
            <div className="space-y-0.5">
              <p className="font-semibold text-amber-200">
                Seasonal swings of &plusmn;{primary_stats.seasonal_amplitude} {metadata.unit} mask the multi-decade slope
              </p>
              <p className="text-[11px] text-amber-100/80">
                Raw seasonal Mann-Kendall p-value = <span className="font-mono font-bold">{formatPValue(primary_stats.raw_p_value)}</span> vs.
                Deseasonalized p-value = <span className="font-mono font-bold text-cyan-300">{formatPValue(primary_stats.p_value)}</span>
              </p>
            </div>
            <button
              type="button"
              onClick={() => setChartMode("deseasonalized")}
              className="inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-cyan-400 to-emerald-400 px-3.5 py-2 text-xs font-bold text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:brightness-110"
            >
              Strip Seasonal Cycle (STL)
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        {chartMode === "deseasonalized" && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-cyan-500/30 bg-cyan-950/25 px-3.5 py-2 text-xs">
            <p className="text-cyan-100">
              <span className="font-semibold text-cyan-300">STL Seasonal Cycle Removed:</span>{" "}
              Total variance reduced by{" "}
              <span className="font-mono font-bold text-emerald-300">
                {primary_stats.variance_reduction_pct}%
              </span>
              , exposing deseasonalized anomalies, OLS trend line, and shaded 95% confidence interval.
            </p>
            <span className="font-mono text-[11px] text-slate-300">
              Raw p={formatPValue(primary_stats.raw_p_value)} → STL p={formatPValue(primary_stats.p_value)}
            </span>
          </div>
        )}

        {chartMode === "teleconnection" && pointB && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-indigo-500/30 bg-indigo-950/30 px-3.5 py-2 text-xs">
            <p className="text-indigo-100">
              <span className="font-semibold text-cyan-300">Left Axis: {pointA.name}</span>{" "}
              ({primary_stats.sens_slope_per_decade >= 0 ? "+" : ""}
              {primary_stats.sens_slope_per_decade}/dec) vs.{" "}
              <span className="font-semibold text-rose-300">Right Axis: {pointB.name}</span>{" "}
              ({(teleconnection.comparison_sens_slope_per_decade ?? 0) >= 0 ? "+" : ""}
              {teleconnection.comparison_sens_slope_per_decade}/dec)
            </p>
            {rInterpret && (
              <span className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${rInterpret.cls}`}>
                r = {rVal?.toFixed(2)} · {rInterpret.label}
              </span>
            )}
          </div>
        )}

        {/* Recharts Visualization */}
        <div className="relative h-[320px] w-full sm:h-[360px]">
          {loading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center rounded-xl bg-slate-950/50 backdrop-blur-[1px]">
              <span className="rounded-lg border border-cyan-500/30 bg-slate-900 px-3 py-1.5 text-xs font-medium text-cyan-200">
                Recomputing STL &amp; Mann-Kendall...
              </span>
            </div>
          )}

          <ResponsiveContainer width="100%" height="100%">
            {chartMode === "raw" ? (
              <ComposedChart data={chartData} margin={{ top: 10, right: 16, left: 0, bottom: 4 }}>
                <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                <XAxis
                  dataKey="timestamp"
                  tick={{ fill: "#94a3b8", fontSize: 11 }}
                  minTickGap={36}
                />
                <YAxis
                  tick={{ fill: "#94a3b8", fontSize: 11 }}
                  width={56}
                  domain={["auto", "auto"]}
                  label={{
                    value: metadata.unit,
                    angle: -90,
                    position: "insideLeft",
                    fill: "#64748b",
                    fontSize: 11,
                  }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#020617",
                    borderColor: "#334155",
                    borderRadius: "10px",
                    fontSize: "12px",
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="raw"
                  name={`Raw ${metadata.parameter_code} (${metadata.unit})`}
                  stroke="#38bdf8"
                  strokeWidth={1.75}
                  dot={false}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="seasonalShifted"
                  name="STL Seasonal Cycle (centered on mean)"
                  stroke="#a78bfa"
                  strokeWidth={1.4}
                  strokeDasharray="4 4"
                  dot={false}
                  isAnimationActive={false}
                />
              </ComposedChart>
            ) : chartMode === "deseasonalized" ? (
              <ComposedChart data={chartData} margin={{ top: 10, right: 16, left: 0, bottom: 4 }}>
                <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                <XAxis
                  dataKey="timestamp"
                  tick={{ fill: "#94a3b8", fontSize: 11 }}
                  minTickGap={36}
                />
                <YAxis
                  tick={{ fill: "#94a3b8", fontSize: 11 }}
                  width={56}
                  domain={["auto", "auto"]}
                  label={{
                    value: `Anomaly (${metadata.unit})`,
                    angle: -90,
                    position: "insideLeft",
                    fill: "#64748b",
                    fontSize: 11,
                  }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#020617",
                    borderColor: "#334155",
                    borderRadius: "10px",
                    fontSize: "12px",
                  }}
                />
                <ReferenceLine y={0} stroke="#475569" strokeDasharray="3 3" />
                <Area
                  type="monotone"
                  dataKey="ciRange"
                  name="95% Confidence Band"
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
                  name="Linear Trend Fit"
                  stroke={primary_stats.is_significant ? "#34d399" : "#facc15"}
                  strokeWidth={2.5}
                  dot={false}
                  isAnimationActive={false}
                />
              </ComposedChart>
            ) : (
              <ComposedChart data={chartData} margin={{ top: 10, right: 16, left: 0, bottom: 4 }}>
                <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                <XAxis
                  dataKey="timestamp"
                  tick={{ fill: "#94a3b8", fontSize: 11 }}
                  minTickGap={36}
                />
                <YAxis
                  yAxisId="left"
                  tick={{ fill: "#38bdf8", fontSize: 11 }}
                  width={52}
                  domain={["auto", "auto"]}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  tick={{ fill: "#fb7185", fontSize: 11 }}
                  width={52}
                  domain={["auto", "auto"]}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#020617",
                    borderColor: "#334155",
                    borderRadius: "10px",
                    fontSize: "12px",
                  }}
                />
                <ReferenceLine yAxisId="left" y={0} stroke="#334155" strokeDasharray="3 3" />
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey="anomaly"
                  name={`Region A: ${pointA.name}`}
                  stroke="#38bdf8"
                  strokeWidth={1.4}
                  dot={false}
                  isAnimationActive={false}
                />
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey="trend"
                  name="Region A Trend"
                  stroke="#22d3ee"
                  strokeWidth={2.5}
                  strokeDasharray="5 3"
                  dot={false}
                  isAnimationActive={false}
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="compAnomaly"
                  name={`Region B: ${pointB?.name || "Comparison"}`}
                  stroke="#fb7185"
                  strokeWidth={1.4}
                  dot={false}
                  isAnimationActive={false}
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="compTrend"
                  name="Region B Trend"
                  stroke="#f43f5e"
                  strokeWidth={2.5}
                  strokeDasharray="5 3"
                  dot={false}
                  isAnimationActive={false}
                />
              </ComposedChart>
            )}
          </ResponsiveContainer>
        </div>

        {/* Interactive Window-Length Slider & 5yr vs 35yr Demo Presets */}
        <div className="flex flex-col gap-2.5 rounded-xl border border-slate-800 bg-slate-950/70 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-200">
              <CalendarRange className="h-4 w-4 text-cyan-400" />
              Observation Window:
              <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-cyan-300">
                {draftStart} – {draftEnd} ({draftEnd - draftStart + 1} yrs)
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
              {[
                { label: "5-Yr Test (2018–2022)", range: [2018, 2022] as [number, number] },
                { label: "Latest 5-Yr (2021–2025)", range: [2021, 2025] as [number, number] },
                { label: "15-Yr (2010–2025)", range: [2010, 2025] as [number, number] },
                { label: "35-Yr Baseline (1990–2025)", range: [1990, 2025] as [number, number] },
                { label: "Full Era (1981–2025)", range: [1981, 2025] as [number, number] },
              ].map((preset) => {
                const active =
                  draftStart === preset.range[0] && draftEnd === preset.range[1];
                return (
                  <button
                    key={preset.label}
                    type="button"
                    onClick={() => {
                      setDraftStart(preset.range[0]);
                      setDraftEnd(preset.range[1]);
                      onChangeWindow(preset.range);
                    }}
                    className={`rounded-lg px-2 py-1 font-medium transition ${
                      active
                        ? "bg-cyan-500 text-slate-950"
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
            <label className="flex items-center gap-2 text-xs text-slate-400">
              <span className="w-16 shrink-0">Start: {draftStart}</span>
              <input
                type="range"
                min={1981}
                max={2022}
                value={draftStart}
                onChange={(e) => applyDraftStart(Number(e.target.value))}
                className="w-full cursor-pointer"
              />
            </label>
            <label className="flex items-center gap-2 text-xs text-slate-400">
              <span className="w-16 shrink-0">End: {draftEnd}</span>
              <input
                type="range"
                min={1984}
                max={2025}
                value={draftEnd}
                onChange={(e) => applyDraftEnd(Number(e.target.value))}
                className="w-full cursor-pointer"
              />
            </label>
          </div>
        </div>
      </div>

      {/* Right 4 cols: Detective Verdict Scorecard */}
      <aside className="flex flex-col gap-3 rounded-2xl border border-slate-800 bg-slate-900/70 p-4 shadow-xl lg:col-span-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-cyan-400" />
            <h2 className="text-sm font-bold text-white">Detective Verdict Scorecard</h2>
          </div>
          <span className="font-mono text-[11px] text-slate-400">
            &alpha; = 0.05
          </span>
        </div>

        {/* High-Contrast Significance Badge */}
        {primary_stats.is_significant ? (
          <div className="flex items-start gap-2.5 rounded-xl border border-emerald-500/40 bg-emerald-950/40 p-3 text-emerald-100">
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-400" />
            <div>
              <p className="text-xs font-extrabold tracking-wide text-emerald-300">
                STATISTICALLY SIGNIFICANT TREND (p &lt; 0.05)
              </p>
              <p className="mt-0.5 text-[11px] text-emerald-100/85">
                Confirmed on deseasonalized anomalies across {primary_stats.observation_years} years.
              </p>
            </div>
          </div>
        ) : (
          <div className="flex items-start gap-2.5 rounded-xl border border-amber-500/40 bg-amber-950/40 p-3 text-amber-100">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
            <div>
              <p className="text-xs font-extrabold tracking-wide text-amber-300">
                {yearsNeeded >= 90
                  ? "NOISE / NO DETECTABLE SLOPE (p ≥ 0.05)"
                  : `NOT YET SIGNIFICANT — NEEDS ~${yearsNeeded} MORE YEARS`}
              </p>
              <p className="mt-0.5 text-[11px] text-amber-100/85">
                Natural variability masks the signal over this {primary_stats.observation_years}-yr window.
              </p>
            </div>
          </div>
        )}

        {/* Sen's Slope Rate Cards */}
        <div className="grid grid-cols-2 gap-2.5">
          <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-3">
            <p className="text-[11px] font-medium text-slate-400">Sen&apos;s Slope / Year</p>
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
            <p className="mt-0.5 text-[11px] text-slate-400">
              {metadata.unit}/yr · {dirInfo.label}
            </p>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-3">
            <p className="text-[11px] font-medium text-slate-400">Sen&apos;s Slope / Decade</p>
            <p className="mt-1 font-mono text-base font-bold text-cyan-300">
              {primary_stats.sens_slope_per_decade >= 0 ? "+" : ""}
              {primary_stats.sens_slope_per_decade}
            </p>
            <p className="mt-0.5 text-[11px] text-slate-400">
              {metadata.unit}/decade
            </p>
          </div>
        </div>

        {/* Non-Parametric & Parametric Statistical Grid */}
        <div className="grid grid-cols-2 gap-2 rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-xs">
          <div>
            <p className="text-[11px] text-slate-400">Mann-Kendall &tau;</p>
            <p className="font-mono font-semibold text-slate-100">{primary_stats.mann_kendall_tau}</p>
          </div>
          <div>
            <p className="text-[11px] text-slate-400">Z-Score</p>
            <p className="font-mono font-semibold text-slate-100">{primary_stats.z_score}</p>
          </div>
          <div>
            <p className="text-[11px] text-slate-400">Deseasonalized MK p</p>
            <p
              className={`font-mono font-bold ${
                primary_stats.is_significant ? "text-emerald-400" : "text-amber-300"
              }`}
            >
              {formatPValue(primary_stats.p_value)}
            </p>
          </div>
          <div>
            <p className="text-[11px] text-slate-400">Student&apos;s t-test p</p>
            <p className="font-mono font-semibold text-slate-100">
              {formatPValue(primary_stats.t_test_p_value)}
            </p>
          </div>
          <div>
            <p className="text-[11px] text-slate-400">Raw Seasonal MK p</p>
            <p className="font-mono font-semibold text-slate-300">
              {formatPValue(primary_stats.raw_p_value)}
            </p>
          </div>
          <div>
            <p className="text-[11px] text-slate-400">STL Variance Stripped</p>
            <p className="font-mono font-semibold text-cyan-300">
              {primary_stats.variance_reduction_pct}%
            </p>
          </div>
        </div>

        {/* Time-to-Significance Horizon Progress Bar */}
        <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
          <div className="flex items-center justify-between text-xs">
            <span className="flex items-center gap-1.5 font-semibold text-slate-200">
              <Clock className="h-3.5 w-3.5 text-cyan-400" />
              Time-to-Significance Horizon
            </span>
            <span className="font-mono text-[11px] text-cyan-300">{horizonPct}%</span>
          </div>
          <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-slate-800">
            <div
              className={`h-full rounded-full transition-all duration-300 ${
                primary_stats.is_significant ? "bg-emerald-400" : "bg-amber-400"
              }`}
              style={{ width: `${horizonPct}%` }}
            />
          </div>
          <p className="mt-1.5 text-[11px] text-slate-400">
            {primary_stats.is_significant
              ? `95% confidence threshold reached within ${obsYears} years of observation.`
              : yearsNeeded >= 90
                ? "Slope is near zero; extended observations cannot resolve a monotonic trend."
                : `Needs ~${yearsNeeded} additional years of monthly satellite data (assuming constant slope & variance).`}
          </p>
        </div>

        {/* Teleconnection Cross-Correlation Summary */}
        <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-xs font-semibold text-slate-200">
              <Radio className="h-3.5 w-3.5 text-indigo-400" />
              Teleconnection Link (A vs B)
            </span>
            {teleconnection.enabled && rVal !== null && (
              <span className="font-mono text-xs font-bold text-indigo-300">
                r = {rVal.toFixed(2)}
              </span>
            )}
          </div>

          {teleconnection.enabled && pointB ? (
            <div className="mt-2 space-y-1.5 text-[11px]">
              {rInterpret && (
                <span className={`inline-block rounded-full border px-2.5 py-0.5 font-semibold ${rInterpret.cls}`}>
                  {rInterpret.label}
                </span>
              )}
              <p className="text-slate-300">
                <span className="font-semibold text-indigo-300">{pointB.name}:</span>{" "}
                {(teleconnection.comparison_sens_slope_per_year ?? 0) >= 0 ? "+" : ""}
                {teleconnection.comparison_sens_slope_per_year} {metadata.unit}/yr (
                {teleconnection.comparison_is_significant ? "significant" : "insignificant"}, p ={" "}
                {formatPValue(teleconnection.comparison_p_value)})
              </p>
            </div>
          ) : (
            <p className="mt-1.5 text-[11px] text-slate-400">
              Click &ldquo;Region B&rdquo; on the map above to compute Pearson cross-correlation across distant Earth regions.
            </p>
          )}
        </div>

        {/* Space Agency & Statistical Methodology Literature Links */}
        <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-[11px] text-slate-400">
          <p className="font-semibold text-slate-200">Statistical &amp; Space Agency References</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            <a
              href="https://ntrs.nasa.gov/api/citations/20090042747/downloads/20090042747.pdf"
              target="_blank"
              rel="noreferrer"
              className="rounded bg-slate-900 px-2 py-0.5 text-cyan-300 hover:underline"
            >
              NASA SeaWiFS Trend Study (PDF)
            </a>
            <a
              href="https://medium.com/@snp.kriss/statistical-test-methods-to-detect-trends-in-time-series-data-b361a0ec530b"
              target="_blank"
              rel="noreferrer"
              className="rounded bg-slate-900 px-2 py-0.5 text-cyan-300 hover:underline"
            >
              Trend Test Methods (MK/Sen)
            </a>
            <a
              href="https://www.statsig.com/perspectives/a-comprehensive-guide-to-statistical-significance"
              target="_blank"
              rel="noreferrer"
              className="rounded bg-slate-900 px-2 py-0.5 text-cyan-300 hover:underline"
            >
              Statistical Significance Guide
            </a>
            <a
              href="https://www.asc-csa.gc.ca/eng/satellites/swot/"
              target="_blank"
              rel="noreferrer"
              className="rounded bg-slate-900 px-2 py-0.5 text-indigo-300 hover:underline"
            >
              CSA SWOT
            </a>
            <a
              href="https://donnees-data.asc-csa.gc.ca/en/dataset/rcm"
              target="_blank"
              rel="noreferrer"
              className="rounded bg-slate-900 px-2 py-0.5 text-indigo-300 hover:underline"
            >
              CSA RCM Data
            </a>
            <a
              href="https://github.com/asc-csa/Synthetic_Aperture_Radar_Tutorial"
              target="_blank"
              rel="noreferrer"
              className="rounded bg-slate-900 px-2 py-0.5 text-indigo-300 hover:underline"
            >
              CSA SAR Tutorial
            </a>
          </div>
        </div>
      </aside>
    </section>
  );
}
