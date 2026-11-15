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
import { AlertCircle, Download, Loader2, Printer, Sparkles, X } from "lucide-react";
import type { DetectiveBrief, GeoPoint, InvestigateResponse } from "./types";

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
      const resp = await fetch("/api/explain", {
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
      schema_version: "2.0.0",
      exported_at: new Date().toISOString(),
      provenance: {
        dataset_tag: investigation.response.dataset_tag ?? data_status,
        data_status,
        primary: investigation.response.primary_provenance ?? null,
        comparison: investigation.response.comparison_provenance ?? null,
      },
      methodology_and_assumptions: {
        mk_variant: primary_stats.mk_variant,
        ci_methodology:
          primary_stats.ci_methodology ??
          "Sen's slope 95% CI uses Sen (1968) order statistics; chart band shows 95% OLS mean-response CI.",
        horizon_assumptions:
          primary_stats.horizon_assumptions ??
          "Estimated Additional Observation Period is an illustrative statistical power estimate assuming stationary slope and variance, not a forecast.",
        brief_methodology_note: brief.methodology_note ?? null,
      },
      limitations: [
        brief.limitations_note ??
          "Statistical significance (alpha = 0.05) depends on window length and autocorrelation; p >= 0.05 does not prove absence of physical change, and cross-correlation r does not prove causation.",
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
    a.download = `terrashift_dossier_${metadata.parameter_code}_${windowRange[0]}-${windowRange[1]}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const generatedDate = new Date().toISOString().slice(0, 10);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="dossier-heading"
      className="dossier-modal-backdrop fixed inset-0 z-[1000] flex items-start justify-center overflow-y-auto bg-slate-950/85 p-3 backdrop-blur-sm sm:p-6"
    >
      <div className="dossier-print-root w-full max-w-[940px] rounded-2xl border border-slate-300 bg-white text-slate-900 shadow-2xl">
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
              Print / Save 1-Page PDF
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
        <div className="space-y-3.5 p-6 text-slate-900 sm:p-7">
          {/* Official Header */}
          <div className="print-avoid-break flex flex-wrap items-start justify-between gap-3 border-b-2 border-slate-900 pb-3">
            <div>
              <p className="font-mono text-[10px] font-bold uppercase tracking-widest text-cyan-900">
                TERRA-SHIFT // NASA EARTH SYSTEM TREND DETECTIVE // SCIENTIFIC DOSSIER
              </p>
              <h2 id="dossier-heading" className="mt-0.5 text-xl font-extrabold text-slate-950">
                {pointA.name}
                {pointB ? ` vs. ${pointB.name}` : ""}
              </h2>
              <p className="text-xs text-slate-700">
                Variable: <strong className="text-slate-900">{metadata.parameter_name} ({metadata.parameter_code})</strong> [{metadata.unit}] · Source:{" "}
                {investigation.response.primary_provenance?.source_name ?? metadata.mission_source} · Biome: {brief.biome_zone}
              </p>
            </div>
            <div className="text-right font-mono text-[11px] text-slate-800">
              <p>
                Window: <strong>{windowRange[0]}–{windowRange[1]}</strong> ({primary_stats.observation_months} months · {primary_stats.observation_years} yrs)
              </p>
              <p>Dataset Mode: <strong>{(investigation.response.dataset_tag ?? data_status).toUpperCase()}</strong></p>
              <p>Date Generated: {generatedDate}</p>
            </div>
          </div>

          {/* Executive Verdict Strip */}
          <div
            className={`print-avoid-break rounded-lg border-l-4 px-4 py-2.5 ${
              primary_stats.is_significant
                ? "border-emerald-600 bg-emerald-50 text-emerald-950"
                : "border-amber-600 bg-amber-50 text-amber-950"
            }`}
          >
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-bold uppercase tracking-wider">
                Statistical Verdict (&alpha; = 0.05 on Deseasonalized STL Anomalies)
              </p>
              <span className="font-mono text-[11px] font-bold">
                MK p = {fmtP(primary_stats.p_value)} ({primary_stats.is_significant ? "Significant" : "Not Significant"})
              </span>
            </div>
            <p className="mt-0.5 text-sm font-extrabold">{brief.verdict_headline}</p>
          </div>

          {/* Geographic & Statistical Scorecard Table */}
          <div className="print-avoid-break grid grid-cols-1 gap-3 sm:grid-cols-2">
            {/* Region A */}
            <div className="rounded-lg border border-slate-300 p-3 text-xs">
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
                <span className="text-slate-600">Sen&apos;s Slope/yr:</span>
                <strong>
                  {primary_stats.sens_slope_per_year >= 0 ? "+" : ""}
                  {primary_stats.sens_slope_per_year} {metadata.unit}
                </strong>
                <span className="text-slate-600">Sen&apos;s Slope/dec:</span>
                <strong className="text-cyan-900">
                  {primary_stats.sens_slope_per_decade >= 0 ? "+" : ""}
                  {primary_stats.sens_slope_per_decade} {metadata.unit}
                </strong>
                <span className="text-slate-600">MK &tau; / Z-Score:</span>
                <strong>
                  {primary_stats.mann_kendall_tau} / {primary_stats.z_score}
                </strong>
                <span className="text-slate-600">Deseasonalized p:</span>
                <strong className={primary_stats.is_significant ? "text-emerald-700" : "text-amber-800"}>
                  {fmtP(primary_stats.p_value)}
                </strong>
                <span className="text-slate-600">Student&apos;s t-test p:</span>
                <strong>{fmtP(primary_stats.t_test_p_value)}</strong>
                <span className="text-slate-600">Raw Seasonal p:</span>
                <strong>{fmtP(primary_stats.raw_p_value)}</strong>
              </div>
            </div>

            {/* Region B / Comparison */}
            <div className="rounded-lg border border-slate-300 p-3 text-xs">
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
                    <span className="text-slate-600">Region B Slope/yr:</span>
                    <strong>
                      {comparison_stats.sens_slope_per_year >= 0 ? "+" : ""}
                      {comparison_stats.sens_slope_per_year} {metadata.unit}
                    </strong>
                    <span className="text-slate-600">Region B MK p:</span>
                    <strong>{fmtP(comparison_stats.p_value)}</strong>
                    <span className="text-slate-600">Pearson Link (r):</span>
                    <strong className="text-indigo-900">
                      {teleconnection.cross_correlation_r !== null && teleconnection.cross_correlation_r !== undefined
                        ? teleconnection.cross_correlation_r.toFixed(3)
                        : "N/A"}
                    </strong>
                    <span className="text-slate-600">Correlation p:</span>
                    <strong>{fmtP(teleconnection.cross_correlation_p_value)}</strong>
                    <span className="text-slate-600">STL Var Removed:</span>
                    <strong>{primary_stats.variance_reduction_pct}%</strong>
                    <span className="text-slate-600">Est. Add&apos;l Obs:</span>
                    <strong>
                      {primary_stats.is_significant
                        ? "0 yrs (Confirmed)"
                        : `~${primary_stats.estimated_additional_observation_years ?? primary_stats.years_to_significance} yrs`}
                    </strong>
                  </div>
                </>
              ) : (
                <div className="mt-2 space-y-1.5 text-slate-700">
                  <p className="italic">Single-region mode (no comparison point selected).</p>
                  <div className="grid grid-cols-2 gap-y-1 border-t border-slate-200 pt-2 font-mono text-[11px] text-slate-900">
                    <span className="text-slate-600">STL Var Stripped:</span>
                    <strong>{primary_stats.variance_reduction_pct}%</strong>
                    <span className="text-slate-600">Seasonal Amplitude:</span>
                    <strong>&plusmn;{primary_stats.seasonal_amplitude} {metadata.unit}</strong>
                    <span className="text-slate-600">Valid Observations:</span>
                    <strong>{primary_stats.valid_months ?? primary_stats.observation_months} months</strong>
                    <span className="text-slate-600">Est. Add&apos;l Obs:</span>
                    <strong>
                      {primary_stats.is_significant
                        ? "0 yrs (Confirmed)"
                        : `~${primary_stats.estimated_additional_observation_years ?? primary_stats.years_to_significance} yrs`}
                    </strong>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Static Deseasonalized Chart Snapshot */}
          <div className="print-avoid-break rounded-lg border border-slate-300 p-3">
            <div className="flex items-center justify-between border-b border-slate-200 pb-1">
              <p className="text-[11px] font-bold uppercase tracking-wide text-slate-800">
                Deseasonalized Anomaly Series &amp; 95% Confidence Band ({metadata.unit})
              </p>
              <span className="font-mono text-[10px] text-slate-600">
                {windowRange[0]}–{windowRange[1]} ({primary_stats.observation_months} mos)
              </span>
            </div>
            <div className="h-[175px] w-full pt-1.5">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ top: 6, right: 12, left: 10, bottom: 18 }}>
                  <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="timestamp"
                    tick={{ fill: "#475569", fontSize: 10 }}
                    minTickGap={40}
                    label={{
                      value: "Observation Date (Year-Month)",
                      position: "insideBottom",
                      offset: -10,
                      fill: "#475569",
                      fontSize: 10,
                    }}
                  />
                  <YAxis
                    tick={{ fill: "#475569", fontSize: 10 }}
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
                  <Legend verticalAlign="top" height={24} wrapperStyle={{ fontSize: "10px", color: "#334155" }} />
                  <ReferenceLine y={0} stroke="#94a3b8" strokeDasharray="3 3" />
                  <Area
                    type="monotone"
                    dataKey="ciRange"
                    name="95% Confidence Band"
                    stroke="none"
                    fill="#0ea5e9"
                    fillOpacity={0.2}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="anomaly"
                    name={`Anomaly (${metadata.unit})`}
                    stroke="#0284c7"
                    strokeWidth={1.4}
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
          </div>

          {/* Structured Physical Brief (4 Core Sections) */}
          <div className="print-avoid-break space-y-2 rounded-lg border border-slate-300 bg-slate-50 p-3.5 text-xs leading-relaxed">
            <div>
              <h3 className="font-bold uppercase tracking-wide text-slate-900">
                1. Earth System Physical Mechanism
              </h3>
              <p className="mt-0.5 text-slate-800">{brief.physical_mechanism}</p>
            </div>
            <div>
              <h3 className="font-bold uppercase tracking-wide text-slate-900">
                2. Why Stripping Seasonality (STL) Was Necessary
              </h3>
              <p className="mt-0.5 text-slate-800">{brief.seasonality_note}</p>
            </div>
            <div>
              <h3 className="font-bold uppercase tracking-wide text-slate-900">
                3. Observation Window &amp; Statistical Power Assessment
              </h3>
              <p className="mt-0.5 text-slate-800">{brief.horizon_note}</p>
            </div>
            <div>
              <h3 className="font-bold uppercase tracking-wide text-slate-900">
                4. Dataset Provenance, Methodology &amp; Limitations
              </h3>
              <p className="mt-0.5 text-slate-800">
                <strong>Source &amp; Status:</strong>{" "}
                {investigation.response.primary_provenance?.source_name ?? metadata.mission_source} (
                {(investigation.response.dataset_tag ?? data_status).toUpperCase()}) ·{" "}
                {primary_stats.valid_months ?? primary_stats.observation_months} valid months ·{" "}
                {(primary_stats.missing_pct ?? 0).toFixed(1)}% missing data.{" "}
                {investigation.response.primary_provenance &&
                investigation.response.primary_provenance.fallback_distance_km > 0
                  ? `Fallback source coordinates (${investigation.response.primary_provenance.source_lat.toFixed(2)}°, ${investigation.response.primary_provenance.source_lon.toFixed(2)}°; ${investigation.response.primary_provenance.fallback_distance_km} km from requested target).`
                  : `Exact target grid resolution (${investigation.response.primary_provenance?.spatial_resolution ?? metadata.resolution}).`}
              </p>
              {brief.limitations_note && (
                <p className="mt-1 text-slate-700">
                  <strong>Limitations:</strong> {brief.limitations_note}
                </p>
              )}
            </div>
            <div className="border-t border-slate-200 pt-2 text-[11px] text-slate-700">
              <p>
                <strong>Primary Literature &amp; Mission Reference:</strong> {brief.reference} ·{" "}
                <em>{metadata.plain_definition}</em>
              </p>
              <p className="mt-1 text-[10px] text-slate-500">
                <strong>Multi-Agency &amp; Statistical Methodology Sources:</strong> NASA Giovanni · GES DISC
                Hydrology Time Series · NASA AppEEARS · NOAA NCEI CDO · NASA NTRS 20090042747 · KNMI Climate Explorer ·
                CSA SWOT &amp; RCM · Sen (1968) &amp; Mann-Kendall Significance Testing (&alpha; = 0.05).
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
