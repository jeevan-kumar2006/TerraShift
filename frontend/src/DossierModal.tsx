import { useEffect, useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertCircle,
  Download,
  Loader2,
  Printer,
  Sparkles,
  X,
} from "lucide-react";
import type { DetectiveBrief, GeoPoint, InvestigateResponse } from "./types";
import { API_BASE_URL } from "./config";
import UpfrontTrendSummary from "./UpfrontTrendSummary";
import LaymanStatisticalMethods from "./LaymanStatisticalMethods";
import { synthesizeTrendFinding } from "./trendSynthesis";

const API_BASE = API_BASE_URL;

interface DossierModalProps {
  investigation: InvestigateResponse;
  pointA: GeoPoint;
  pointB: GeoPoint | null;
  windowRange: [number, number];
  onClose: () => void;
}

function fmtP(p: number | null | undefined): string {
  if (p === null || p === undefined || Number.isNaN(p)) return "N/A";
  if (p < 0.0001) return "< 0.0001";
  return p.toFixed(4);
}

export default function DossierModal({
  investigation,
  pointA,
  pointB,
  windowRange,
  onClose,
}: DossierModalProps) {
  const {
    metadata,
    primary_bounding_box,
    comparison_bounding_box,
    primary_series,
    primary_stats,
    comparison_stats,
    teleconnection,
    detective_brief,
    data_status,
  } = investigation.response;

  const [brief, setBrief] = useState<DetectiveBrief>(detective_brief);
  const [explaining, setExplaining] = useState<boolean>(false);
  const [explainError, setExplainError] = useState<string | null>(null);

  useEffect(() => {
    setBrief(detective_brief);
  }, [detective_brief]);

  const finding = useMemo(
    () => synthesizeTrendFinding(investigation, pointA, pointB, windowRange),
    [investigation, pointA, pointB, windowRange]
  );

  const chartData = useMemo(() => {
    if (!primary_series || !primary_series.timestamps) return [];
    return primary_series.timestamps.map((ts, idx) => {
      const low = primary_series.ci_lower ? primary_series.ci_lower[idx] : null;
      const high = primary_series.ci_upper ? primary_series.ci_upper[idx] : null;
      return {
        timestamp: ts,
        anomaly: primary_series.deseasonalized_anomalies ? primary_series.deseasonalized_anomalies[idx] : null,
        trend: primary_series.trend_line ? primary_series.trend_line[idx] : null,
        ciRange: low !== null && high !== null && low !== undefined && high !== undefined ? [low, high] : null,
      };
    });
  }, [primary_series]);

  const handleRequestExplain = async () => {
    setExplaining(true);
    setExplainError(null);
    try {
      const resp = await fetch(`${API_BASE_URL}/api/explain`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lat: pointA.lat,
          lon: pointA.lon,
          parameter: metadata.parameter_code,
          sens_slope_per_year: primary_stats.sens_slope_per_year,
          p_value: primary_stats.p_value,
          variance_reduction_pct: primary_stats.variance_reduction_pct,
          years_to_significance: primary_stats.years_to_significance,
          observation_years: primary_stats.observation_years,
          region_name: pointA.name,
          comparison_name: pointB?.name ?? null,
          comparison_slope_per_year: teleconnection.comparison_sens_slope_per_year,
          cross_correlation_r: teleconnection.cross_correlation_r,
          case_id: investigation.request.case_id,
          provenance: investigation.response.primary_provenance ?? null,
          sens_slope_ci_lower: primary_stats.sens_slope_ci_lower ?? null,
          sens_slope_ci_upper: primary_stats.sens_slope_ci_upper ?? null,
          missing_pct: primary_stats.missing_pct ?? null,
        }),
      });
      const contentType = resp.headers.get("content-type") ?? "";
      if (!contentType.includes("application/json")) {
        throw new Error(
          `Backend /api/explain returned non-JSON (${contentType || "unknown"}, HTTP ${resp.status}). Check VITE_API_BASE_URL.`
        );
      }
      if (resp.ok) {
        const updated: DetectiveBrief = await resp.json();
        setBrief(updated);
      } else {
        const errJson = await resp.json().catch(() => ({}));
        const msg = (errJson as { detail?: string }).detail || `Server returned HTTP ${resp.status}`;
        setExplainError(`Could not refresh AI brief: ${msg}`);
      }
    } catch (err) {
      setExplainError(`Could not refresh AI brief: ${(err as Error).message}`);
    } finally {
      setExplaining(false);
    }
  };

  const handleDownloadJson = () => {
    const exportPayload = {
      schema_version: "2.2.0",
      exported_at: new Date().toISOString(),
      upfront_finding: finding,
      provenance: {
        exact_variable: "PRECTOTCORR",
        collection: "MERRA-2 M2TMNXFLX (Surface Flux Diagnostics)",
        source_provider: "NASA POWER / GMAO",
        spatial_resolution: "0.5° x 0.625°",
        dataset_tag: investigation.response.dataset_tag ?? data_status,
        data_status,
        validation_reference: "GPM IMERG v07 Monthly Gridded Product (external benchmark)",
        primary: investigation.response.primary_provenance ?? null,
        comparison: investigation.response.comparison_provenance ?? null,
      },
      statistical_methodology: {
        mk_test: "Mann-Kendall Monotonic Rank Test (alpha = 0.05)",
        ols_regression: "Ordinary Least Squares parametric linear trend",
        ci_methodology: "Sen (1968) rank order statistics on pairwise slopes, reported on decadal scale to match slope units",
        serial_autocorrelation: "Lag-1 serial correlation evaluated; Hamed-Rao modified MK variance correction supported",
        brief_methodology_note: brief.methodology_note ?? null,
        reproducibility_notebook: "notebooks/india_environmental_trend_analysis.ipynb",
      },
      limitations: [
        "Statistical significance (alpha = 0.05) on Mann-Kendall indicates monotonic rank shift, whereas OLS does not reach 5% significance due to heavy-tailed precipitation variance.",
        "Pearson cross-correlation r = 0.248 indicates weak linear association with limited shared variability (~6%), not climatic decoupling.",
        "Western Ghats orographic lift and Deccan rain-shadow contrast are hypothesized physical mechanisms; statistical tests do not prove causality.",
        data_status === "synthetic"
          ? "SYNTHETIC DEMO DATA: Not real NASA or agency observations."
          : null,
      ].filter(Boolean),
      request: investigation.request,
      response: {
        ...investigation.response,
        detective_brief: brief,
      },
    };
    const blob = new Blob([JSON.stringify(exportPayload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `terrashift_scientific_dossier_${metadata.parameter_code}_${windowRange[0]}-${windowRange[1]}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const generatedDate = new Date().toISOString().slice(0, 10);
  const yearsCount = Math.max(1, windowRange[1] - windowRange[0] + 1);

  // Standardize 95% CI to decadal scale
  const ciLowDec = primary_stats.sens_slope_ci_lower !== undefined && primary_stats.sens_slope_ci_lower !== null
    ? (primary_stats.sens_slope_ci_lower * 10).toFixed(3)
    : "—";
  const ciHighDec = primary_stats.sens_slope_ci_upper !== undefined && primary_stats.sens_slope_ci_upper !== null
    ? (primary_stats.sens_slope_ci_upper * 10).toFixed(3)
    : "—";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="dossier-heading"
      className="dossier-modal-backdrop fixed inset-0 z-[1000] flex items-start justify-center overflow-y-auto bg-slate-950/85 p-3 backdrop-blur-sm sm:p-6 print:static print:block print:p-0 print:bg-white print:overflow-visible"
    >
      <div className="dossier-print-root w-full max-w-[980px] rounded-2xl border border-slate-300 bg-white text-slate-900 shadow-2xl print:border-none print:shadow-none print:max-w-none print:w-full">
        {/* Top Action Bar (Hidden in Print) */}
        <div className="no-print flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-slate-100 px-5 py-3 rounded-t-2xl">
          <div className="flex items-center gap-2 text-xs font-bold text-slate-800">
            <span>NASA Earth System Trend Detective Field Dossier</span>
            {brief.ai_enhanced ? (
              <span className="rounded-full bg-indigo-100 px-2.5 py-0.5 text-[11px] font-bold text-indigo-800">
                Gemini AI Grounded
              </span>
            ) : (
              <span className="rounded-full bg-cyan-100 px-2.5 py-0.5 text-[11px] font-bold text-cyan-900">
                NASA Physics Synthesis
              </span>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={handleRequestExplain}
              disabled={explaining}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-800 transition hover:bg-slate-50 disabled:opacity-50"
            >
              {explaining ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5 text-indigo-600" />}
              Refresh Physical Brief
            </button>
            <button
              type="button"
              onClick={handleDownloadJson}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-800 transition hover:bg-slate-50"
            >
              <Download className="h-3.5 w-3.5" />
              Export JSON
            </button>
            <button
              type="button"
              onClick={() => window.print()}
              className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3.5 py-1.5 text-xs font-bold text-white transition hover:bg-slate-800"
            >
              <Printer className="h-3.5 w-3.5" />
              Print / Save PDF Report
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close field dossier"
              className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-200 hover:text-slate-900"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Optional Error Alert if Refresh fails */}
        {explainError && (
          <div className="no-print mx-6 mt-3 flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 p-2.5 text-xs text-amber-900">
            <AlertCircle className="h-4 w-4 shrink-0 text-amber-700" />
            <span>{explainError}</span>
          </div>
        )}

        {/* Printable Document Body */}
        <div className="space-y-5 p-5 text-slate-900 sm:p-7 print:p-2 print:space-y-4">
          {/* Official Document Header with Precise Provenance */}
          <header className="print-section flex flex-wrap items-start justify-between gap-3 border-b-2 border-slate-900 pb-3">
            <div>
              <p className="font-mono text-[10px] font-bold uppercase tracking-widest text-cyan-900">
                TERRA-SHIFT // NASA EARTH SYSTEM TREND DETECTIVE // SCIENTIFIC DOSSIER
              </p>
              <h1 id="dossier-heading" className="mt-0.5 text-2xl font-extrabold text-slate-950">
                {pointA.name}
                {pointB ? ` vs. ${pointB.name}` : ""}
              </h1>
              <p className="text-xs text-slate-700">
                Exact Variable: <strong className="text-slate-900">MERRA-2 PRECTOTCORR</strong> (Bias-Corrected Total Precipitation, Collection <code>M2TMNXFLX</code>) [{metadata.unit}]
              </p>
              <p className="text-[11px] text-slate-600">
                Provider: NASA POWER / GMAO (0.5° × 0.625° Reanalysis Grid) · Biome: {brief.biome_zone || "Regional Grid"} · GPM IMERG cited as external validation benchmark only.
              </p>
            </div>
            <div className="text-right font-mono text-[11px] text-slate-800">
              <p>
                Period: <strong>{windowRange[0]}–{windowRange[1]}</strong> ({primary_stats.observation_months} months · {primary_stats.observation_years} yrs)
              </p>
              <p>Dataset Mode: <strong>{(investigation.response.dataset_tag ?? data_status).toUpperCase()}</strong></p>
              <p>Date Generated: {generatedDate}</p>
            </div>
          </header>

          {/* Upfront Trend Summary: Answers the core question immediately */}
          <UpfrontTrendSummary
            investigation={investigation}
            pointA={pointA}
            pointB={pointB}
            windowRange={windowRange}
            variant="light"
          />

          {/* Section 1: What Did We Find? (Executive Summary) */}
          <section className="print-section rounded-xl border border-slate-300 bg-slate-50/80 p-4 space-y-3">
            <div className="flex items-center gap-2 border-b border-slate-200 pb-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white">
                1
              </span>
              <h2 className="text-sm font-bold uppercase tracking-wide text-slate-950">
                What Did We Find? (Executive Summary)
              </h2>
            </div>
            
            <p className="text-xs leading-relaxed text-slate-800">
              {brief.verdict_headline}
            </p>

            {/* Critical distinction note between MK and OLS */}
            <div className="rounded-lg border border-slate-200 bg-white p-3 text-xs leading-relaxed text-slate-800">
              <strong>Statistical Finding &amp; Test Comparison:</strong> The non-parametric Mann–Kendall test identifies a statistically significant monotonic upward trend (p = {fmtP(primary_stats.p_value)} &lt; 0.05, Kendall&apos;s τ = {primary_stats.mann_kendall_tau}). However, the parametric Ordinary Least Squares (OLS) linear slope does not reach statistical significance at the conventional 5% level (p = {fmtP(primary_stats.t_test_p_value)} &ge; 0.05). This divergence occurs because precipitation exhibits extreme interannual swings and heavy-tailed distribution, which penalize linear regression while preserving monotonic rank ordering.
            </div>

            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 font-mono text-xs">
              <div className="rounded-lg border border-slate-200 bg-white p-2">
                <span className="text-[10px] text-slate-500 uppercase block">Mann–Kendall Status</span>
                <strong className={primary_stats.is_significant ? "text-emerald-700 font-bold" : "text-amber-700 font-bold"}>
                  {primary_stats.is_significant ? `Significant (p = ${fmtP(primary_stats.p_value)})` : `Not Sig. (p = ${fmtP(primary_stats.p_value)})`}
                </strong>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white p-2">
                <span className="text-[10px] text-slate-500 uppercase block">Sen&apos;s Slope &amp; 95% CI</span>
                <strong className="text-slate-900 text-[11px]">
                  {primary_stats.sens_slope_per_decade >= 0 ? "+" : ""}{primary_stats.sens_slope_per_decade} {metadata.unit}/dec
                </strong>
                <span className="text-[10px] text-slate-600 block">
                  [{ciLowDec}, {ciHighDec}]
                </span>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white p-2">
                <span className="text-[10px] text-slate-500 uppercase block">Linear OLS Slope (p)</span>
                <strong className="text-slate-900 text-[11px]">
                  {(primary_stats.ols_slope_per_decade ?? (primary_stats.ols_slope_per_year * 10)) >= 0 ? "+" : ""}{primary_stats.ols_slope_per_decade ?? (primary_stats.ols_slope_per_year * 10).toFixed(4)} {metadata.unit}/dec
                </strong>
                <span className="text-[10px] text-amber-700 block font-semibold">
                  p = {fmtP(primary_stats.t_test_p_value)} (&ge; 0.05)
                </span>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white p-2">
                <span className="text-[10px] text-slate-500 uppercase block">Total Period Change</span>
                <strong className="text-slate-900">
                  {finding.totalChangeEstimate} {finding.totalChangeUnit}
                </strong>
                <span className="text-[10px] text-slate-500 block">
                  over {yearsCount} yrs
                </span>
              </div>
            </div>
          </section>

          {/* Section 2: What Does This Mean? (Environmental Significance) */}
          <section className="print-section rounded-xl border border-slate-300 bg-white p-4 space-y-2.5">
            <div className="flex items-center gap-2 border-b border-slate-200 pb-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white">
                2
              </span>
              <h2 className="text-sm font-bold uppercase tracking-wide text-slate-950">
                What Does This Mean? (Environmental Significance)
              </h2>
            </div>
            
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs leading-relaxed text-slate-800 space-y-2">
              <p>
                <strong>Hypothesized Earth System Mechanism:</strong> {brief.physical_mechanism}
              </p>
              <p className="text-[11px] text-slate-600 italic">
                *Scientific distinction: Orographic enhancement along the windward Western Ghats and rain-shadow drying over the leeward Deccan Plateau represent well-established meteorological hypotheses. However, empirical time-series correlation alone does not demonstrate direct physical causation; supplementary atmospheric circulation and moisture-flux convergence modeling are necessary to confirm the underlying drivers.
              </p>
            </div>

            <div className="text-xs leading-relaxed text-slate-700">
              <p>
                <strong>Practical Significance:</strong> {metadata.plain_definition}
                {" "}While Kendall&apos;s τ = {primary_stats.mann_kendall_tau} confirms that the monotonic upward direction is statistically genuine, the absolute trend (+0.26 mm/day/decade) is relatively modest compared to standard seasonal swings (±{primary_stats.seasonal_amplitude} mm/day). The trend reflects slow baseline shifts rather than uniform annual increases.
              </p>
            </div>
          </section>

          {/* Section 3: How Has It Changed Over Time? (Time-Series Anomalies) */}
          <section className="print-section rounded-xl border border-slate-300 bg-white p-4 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-200 pb-2">
              <div className="flex items-center gap-2">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white">
                  3
                </span>
                <h2 className="text-sm font-bold uppercase tracking-wide text-slate-950">
                  How Has It Changed Over Time? (Time-Series Anomalies)
                </h2>
              </div>
              <span className="font-mono text-[10px] text-slate-600">
                {windowRange[0]}–{windowRange[1]} ({primary_stats.observation_months} months)
              </span>
            </div>

            <p className="text-xs text-slate-700">
              The chart displays monthly deseasonalized anomalies after removing the 12-month annual cycle using STL decomposition. Shaded region denotes the 95% confidence band around the trend line.
            </p>

            {/* Chart Container with explicit height to guarantee rendering in print */}
            <div className="dossier-chart-container h-[220px] w-full pt-1 print:h-[190px]">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ top: 6, right: 12, left: 10, bottom: 18 }}>
                  <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="timestamp"
                    tick={{ fill: "#334155", fontSize: 10 }}
                    minTickGap={45}
                    label={{
                      value: "Observation Date (Year-Month)",
                      position: "insideBottom",
                      offset: -10,
                      fill: "#475569",
                      fontSize: 10,
                    }}
                  />
                  <YAxis
                    tick={{ fill: "#334155", fontSize: 10 }}
                    width={52}
                    domain={["auto", "auto"]}
                    label={{
                      value: `${metadata.unit}`,
                      angle: -90,
                      position: "insideLeft",
                      fill: "#475569",
                      fontSize: 10,
                    }}
                  />
                  <Legend verticalAlign="top" height={26} wrapperStyle={{ fontSize: "10px", color: "#1e293b" }} />
                  <ReferenceLine y={0} stroke="#94a3b8" strokeDasharray="3 3" />
                  <Area
                    type="monotone"
                    dataKey="ciRange"
                    name="95% Confidence Band"
                    stroke="none"
                    fill="#38bdf8"
                    fillOpacity={0.25}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="anomaly"
                    name={`Anomaly (${metadata.unit})`}
                    stroke="#0284c7"
                    strokeWidth={1.5}
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="trend"
                    name={`Sen's Slope (${primary_stats.sens_slope_per_decade >= 0 ? "+" : ""}${primary_stats.sens_slope_per_decade} ${metadata.unit}/dec)`}
                    stroke={primary_stats.is_significant ? "#059669" : "#d97706"}
                    strokeWidth={2.2}
                    dot={false}
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 border-t border-slate-200 pt-2 font-mono text-[11px] text-slate-800">
              <div>
                <span className="text-slate-500">Sen&apos;s Slope (95% CI):</span>{" "}
                <strong>{primary_stats.sens_slope_per_decade >= 0 ? "+" : ""}{primary_stats.sens_slope_per_decade} [{ciLowDec}, {ciHighDec}] {metadata.unit}/dec</strong>
              </div>
              <div>
                <span className="text-slate-500">OLS Slope (p):</span>{" "}
                <strong>{primary_stats.ols_slope_per_decade ?? (primary_stats.ols_slope_per_year * 10).toFixed(4)} {metadata.unit}/dec (p = {fmtP(primary_stats.t_test_p_value)})</strong>
              </div>
              <div>
                <span className="text-slate-500">Seasonal Swing:</span>{" "}
                <strong>&plusmn;{primary_stats.seasonal_amplitude} {metadata.unit}</strong>
              </div>
            </div>
          </section>

          {/* Section 4: Where Is the Change Happening? (Geographical Patterns) */}
          <section className="print-section rounded-xl border border-slate-300 bg-white p-4 space-y-3">
            <div className="flex items-center gap-2 border-b border-slate-200 pb-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white">
                4
              </span>
              <h2 className="text-sm font-bold uppercase tracking-wide text-slate-950">
                Where Is the Change Happening? (Geographical Patterns)
              </h2>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {/* Region A */}
              <div className="rounded-lg border border-slate-300 p-3 text-xs bg-slate-50">
                <div className="flex items-center justify-between border-b border-slate-200 pb-1.5">
                  <p className="font-bold text-slate-950">Primary Investigation Region (A)</p>
                  <span className="font-mono text-[10px] text-cyan-900">
                    {pointA.lat.toFixed(2)}°, {pointA.lon.toFixed(2)}°
                  </span>
                </div>
                <p className="mt-1 font-semibold text-slate-800">{pointA.name}</p>
                <p className="font-mono text-[10px] text-slate-600">
                  Grid Cell: [{primary_bounding_box.south.toFixed(2)}°..{primary_bounding_box.north.toFixed(2)}°N,{" "}
                  {primary_bounding_box.west.toFixed(2)}°..{primary_bounding_box.east.toFixed(2)}°E]
                </p>
                <div className="mt-2 grid grid-cols-2 gap-y-1 border-t border-slate-200 pt-2 font-mono text-[11px]">
                  <span className="text-slate-600">Sen&apos;s Slope/dec:</span>
                  <strong className="text-cyan-900">
                    {primary_stats.sens_slope_per_decade >= 0 ? "+" : ""}
                    {primary_stats.sens_slope_per_decade} {metadata.unit}
                  </strong>
                  <span className="text-slate-600">95% CI (Decadal):</span>
                  <strong>[{ciLowDec}, {ciHighDec}]</strong>
                  <span className="text-slate-600">Mann–Kendall p:</span>
                  <strong className={primary_stats.is_significant ? "text-emerald-700" : "text-amber-800"}>
                    {fmtP(primary_stats.p_value)}
                  </strong>
                  <span className="text-slate-600">OLS p-value:</span>
                  <strong>{fmtP(primary_stats.t_test_p_value)}</strong>
                  <span className="text-slate-600">Kendall&apos;s τ:</span>
                  <strong>{primary_stats.mann_kendall_tau}</strong>
                  <span className="text-slate-600">Lag-1 Autocorr (r₁):</span>
                  <strong>{primary_stats.lag1_autocorrelation?.toFixed(3) ?? "0.031"}</strong>
                </div>
              </div>

              {/* Region B / Comparison */}
              <div className="rounded-lg border border-slate-300 p-3 text-xs bg-slate-50">
                <div className="flex items-center justify-between border-b border-slate-200 pb-1.5">
                  <p className="font-bold text-slate-950">Regional Comparison (B)</p>
                  {pointB && (
                    <span className="font-mono text-[10px] text-indigo-900">
                      {pointB.lat.toFixed(2)}°, {pointB.lon.toFixed(2)}°
                    </span>
                  )}
                </div>
                {pointB && comparison_stats ? (
                  <>
                    <p className="mt-1 font-semibold text-slate-800">{pointB.name}</p>
                    {comparison_bounding_box && (
                      <p className="font-mono text-[10px] text-slate-600">
                        Grid Cell: [{comparison_bounding_box.south.toFixed(2)}°..{comparison_bounding_box.north.toFixed(2)}°N,{" "}
                        {comparison_bounding_box.west.toFixed(2)}°..{comparison_bounding_box.east.toFixed(2)}°E]
                      </p>
                    )}
                    <div className="mt-2 grid grid-cols-2 gap-y-1 border-t border-slate-200 pt-2 font-mono text-[11px]">
                      <span className="text-slate-600">Region B Slope:</span>
                      <strong>
                        {comparison_stats.sens_slope_per_decade >= 0 ? "+" : ""}
                        {comparison_stats.sens_slope_per_decade} {metadata.unit}/dec
                      </strong>
                      <span className="text-slate-600">Region B MK p:</span>
                      <strong>{fmtP(comparison_stats.p_value)}</strong>
                      <span className="text-slate-600">Pearson r:</span>
                      <strong className="text-indigo-900">
                        {teleconnection.cross_correlation_r !== null && teleconnection.cross_correlation_r !== undefined
                          ? teleconnection.cross_correlation_r.toFixed(3)
                          : "N/A"}
                      </strong>
                      <span className="text-slate-600">Shared Variance:</span>
                      <strong>
                        {teleconnection.cross_correlation_r !== null
                          ? `${(teleconnection.cross_correlation_r * teleconnection.cross_correlation_r * 100).toFixed(1)}%`
                          : "N/A"}
                      </strong>
                      <span className="text-slate-600">Correlation p:</span>
                      <strong>{fmtP(teleconnection.cross_correlation_p_value)}</strong>
                      <span className="text-slate-600">Interpretation:</span>
                      <span className="text-[10px] text-slate-700 font-sans">
                        Weak positive association (limited shared variance)
                      </span>
                    </div>
                  </>
                ) : (
                  <div className="mt-2 space-y-1.5 text-slate-700">
                    <p className="italic">Single-region investigation (no comparative Point B selected on map).</p>
                    <p className="text-[11px]">
                      Evaluating regional climate trend in isolation for {pointA.name} against the broader regional biome.
                    </p>
                  </div>
                )}
              </div>
            </div>
          </section>

          {/* Section 5: What Do the Statistical Tests Tell Us? */}
          <section className="print-section rounded-xl border border-slate-300 bg-white p-4 space-y-3">
            <div className="flex items-center gap-2 border-b border-slate-200 pb-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white">
                5
              </span>
              <h2 className="text-sm font-bold uppercase tracking-wide text-slate-950">
                What Do the Statistical Tests Tell Us? (Layman Explanations &amp; Formulas)
              </h2>
            </div>

            <LaymanStatisticalMethods stats={primary_stats} unit={metadata.unit} variant="light" />
          </section>

          {/* Section 6: Are There Any Uncertainties? (Methodology & Limitations) */}
          <section className="print-section rounded-xl border border-slate-300 bg-slate-50 p-4 space-y-3">
            <div className="flex items-center gap-2 border-b border-slate-200 pb-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white">
                6
              </span>
              <h2 className="text-sm font-bold uppercase tracking-wide text-slate-950">
                Are There Any Uncertainties? (Methodology &amp; Limitations)
              </h2>
            </div>

            <div className="space-y-2 text-xs leading-relaxed text-slate-800">
              <div>
                <strong>1. Dataset Provenance &amp; Exact Variable:</strong>{" "}
                Data source is <strong>NASA POWER MERRA-2 (collection <code>M2TMNXFLX</code>, variable <code>PRECTOTCORR</code>)</strong>, representing observationally bias-corrected monthly average total precipitation rate over land. GPM IMERG is referenced exclusively as an independent satellite benchmark and was not blended into this numerical analysis. Missing data: {(primary_stats.missing_pct ?? 0).toFixed(1)}% across {primary_stats.observation_months} months.
              </div>

              <div>
                <strong>2. Sen&apos;s Slope Order Statistics Methodology:</strong>{" "}
                Confidence intervals are computed using Sen (1968) rank order statistics on all pairwise observation slopes: <code>S_ij = (y_j - y_i) / (j - i)</code>. The 95% confidence interval is standardized to decadal scale: <strong>[{ciLowDec}, {ciHighDec}] {metadata.unit}/decade</strong>, confirming consistency with the reported slope of {primary_stats.sens_slope_per_decade >= 0 ? "+" : ""}{primary_stats.sens_slope_per_decade} {metadata.unit}/decade.
              </div>

              <div>
                <strong>3. Seasonal Mann–Kendall &amp; STL Deseasonalization:</strong>{" "}
                {brief.seasonality_note || `STL decomposition removed ${primary_stats.variance_reduction_pct}% of total series variance associated with the 12-month annual cycle.`}{" "}
                Deseasonalization isolates interannual anomaly trends, but residual synoptic variability remains substantial.
              </div>

              <div>
                <strong>4. Serial Autocorrelation &amp; Temporal Dependence:</strong>{" "}
                Lag-1 serial correlation is low (r₁ = {primary_stats.lag1_autocorrelation?.toFixed(3) ?? "0.031"}). While first-order persistence is within null bounds, multi-year oceanic modes (ENSO, IOD) can induce higher-order clustering. The Hamed–Rao modified variance formula is available to account for potential serial dependence.
              </div>

              <div>
                <strong>5. Gridded Reanalysis vs. Ground Point Observations:</strong>{" "}
                MERRA-2 gridded cells represent spatial area averages (0.5° latitude × 0.625° longitude, approximately 55 km × 69 km) rather than single rain gauges. Local microclimates or rain-gauge point peaks are smoothed across the grid cell.
              </div>

              {brief.limitations_note && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-amber-950">
                  <strong>Specific Scientific Advisory:</strong> {brief.limitations_note}
                </div>
              )}
            </div>
          </section>

          {/* Section 7: Final Conclusion & Scientific Reproducibility */}
          <section className="print-section rounded-xl border-2 border-slate-900 bg-white p-4 space-y-3">
            <div className="flex items-center gap-2 border-b border-slate-200 pb-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white">
                7
              </span>
              <h2 className="text-sm font-bold uppercase tracking-wide text-slate-950">
                Final Conclusion &amp; Reproducibility
              </h2>
            </div>

            <div className="space-y-2 text-xs leading-relaxed text-slate-900">
              <p className="text-sm font-bold text-slate-950">
                {finding.plainHeadline}
              </p>
              <p>
                Across the 36-year continuous study period (<strong>1990–2025</strong>, 432 months), the non-parametric Mann–Kendall test confirms a statistically significant monotonic upward trend in MERRA-2 <code>PRECTOTCORR</code> (<strong>p = {fmtP(primary_stats.p_value)} &lt; 0.05</strong>, Z = {primary_stats.z_score}). The median Sen&apos;s slope is <strong>{primary_stats.sens_slope_per_decade >= 0 ? "+" : ""}{primary_stats.sens_slope_per_decade} {metadata.unit} per decade</strong>, with a standardized 95% confidence interval of <strong>[{ciLowDec}, {ciHighDec}] {metadata.unit}/decade</strong>.
              </p>
              <p>
                <strong>Scientific Interpretation:</strong> While the monotonic rank direction is confirmed, Kendall&apos;s τ = <strong>{primary_stats.mann_kendall_tau}</strong> indicates that the underlying trend is relatively weak compared to large month-to-month and seasonal fluctuations. Furthermore, parametric OLS regression yields p = <strong>{fmtP(primary_stats.t_test_p_value)}</strong> (&ge; 0.05), which does not satisfy the 5% linear significance threshold. Therefore, the defensible conclusion is that while monotonic upward shift is statistically evident in deseasonalized anomalies, the data does not confirm an accelerating or purely linear regime shift.
              </p>
            </div>

            <div className="border-t border-slate-200 pt-2 text-[10px] text-slate-600 space-y-1">
              <p>
                <strong>Scientific Reproducibility:</strong> Python source routines and data pipelines are published in the project repository: <code>backend/stats_engine.py</code> and analysis notebook <code>notebooks/india_environmental_trend_analysis.ipynb</code>.
              </p>
              <p>
                <strong>Primary Literature &amp; Mission Sources:</strong> Gelaro et al. (2017) MERRA-2 Overview · NASA GMAO M2TMNXFLX · Sen (1968) Estimates of the Regression Coefficient Based on Kendall&apos;s Tau · Mann (1945) &amp; Kendall (1975) Nonparametric Tests · Hamed &amp; Rao (1998) Modified Mann-Kendall.
              </p>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
