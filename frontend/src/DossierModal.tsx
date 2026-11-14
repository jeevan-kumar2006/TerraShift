import { useEffect, useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";
import { Download, Loader2, Printer, Sparkles, X } from "lucide-react";
import type { DetectiveBrief, GeoPoint, InvestigateResponse } from "./types";

interface DossierModalProps {
  investigation: InvestigateResponse;
  pointA: GeoPoint;
  pointB: GeoPoint | null;
  windowRange: [number, number];
  onClose: () => void;
}

function fmtP(p: number | null | undefined): string {
  if (p === null || p === undefined) return "N/A";
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

  useEffect(() => {
    setBrief(detective_brief);
  }, [detective_brief]);

  const chartData = useMemo(() => {
    return primary_series.timestamps.map((ts, idx) => {
      const low = primary_series.ci_lower[idx];
      const high = primary_series.ci_upper[idx];
      return {
        timestamp: ts,
        anomaly: primary_series.deseasonalized_anomalies[idx],
        trend: primary_series.trend_line[idx],
        ciRange: low !== null && high !== null ? [low, high] : null,
      };
    });
  }, [primary_series]);

  const handleRequestExplain = async () => {
    setExplaining(true);
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
        }),
      });
      if (resp.ok) {
        const updated: DetectiveBrief = await resp.json();
        setBrief(updated);
      }
    } finally {
      setExplaining(false);
    }
  };

  const handleDownloadJson = () => {
    const blob = new Blob([JSON.stringify({ ...investigation, detective_brief: brief }, null, 2)], {
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
    <div className="dossier-modal-backdrop fixed inset-0 z-[1000] flex items-start justify-center overflow-y-auto bg-slate-950/85 p-3 backdrop-blur-sm sm:p-6">
      <div className="dossier-print-root w-full max-w-[900px] rounded-2xl border border-slate-300 bg-white text-slate-900 shadow-2xl">
        {/* Top Action Bar (Hidden in PDF Print) */}
        <div className="no-print flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-slate-100 px-5 py-3 rounded-t-2xl">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-700">
            <span>1-Page Printable NASA Field Dossier</span>
            {brief.ai_enhanced ? (
              <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-[11px] font-bold text-indigo-700">
                Gemini AI Grounded
              </span>
            ) : (
              <span className="rounded-full bg-cyan-100 px-2 py-0.5 text-[11px] font-bold text-cyan-800">
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
              aria-label="Close dossier"
              className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-200 hover:text-slate-900"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Printable Document Body */}
        <div className="space-y-3.5 p-6 text-slate-900">
          {/* Official Header */}
          <div className="print-avoid-break flex flex-wrap items-start justify-between gap-2 border-b-2 border-slate-900 pb-3">
            <div>
              <p className="font-mono text-[10px] font-bold uppercase tracking-widest text-cyan-800">
                TERRA-SHIFT // NASA EARTH SYSTEM TREND DETECTIVE FIELD DOSSIER
              </p>
              <h2 className="mt-0.5 text-xl font-extrabold text-slate-950">
                {pointA.name}
                {pointB ? ` vs. ${pointB.name}` : ""}
              </h2>
              <p className="text-xs text-slate-600">
                {metadata.parameter_name} ({metadata.parameter_code}) · {metadata.mission_source} ·{" "}
                {brief.biome_zone}
              </p>
            </div>
            <div className="text-right font-mono text-[11px] text-slate-700">
              <p>
                Window: <strong>{windowRange[0]}–{windowRange[1]}</strong> ({primary_stats.observation_months} mos)
              </p>
              <p>Source Mode: {data_status.toUpperCase()}</p>
              <p>Generated: {generatedDate}</p>
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
            <p className="text-[11px] font-bold uppercase tracking-wider">
              Statistical Verdict (&alpha; = 0.05 on Deseasonalized STL Anomalies)
            </p>
            <p className="text-sm font-extrabold">{brief.verdict_headline}</p>
          </div>

          {/* Coordinates & Statistical Scorecard Table */}
          <div className="print-avoid-break grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-slate-300 p-3 text-xs">
              <p className="font-bold text-slate-900">Primary Investigation Region (A)</p>
              <p className="text-slate-700">
                {pointA.name} ({pointA.lat.toFixed(2)}°, {pointA.lon.toFixed(2)}°)
              </p>
              <p className="font-mono text-[10px] text-slate-500">
                MERRA-2 Cell: [{primary_bounding_box.south}..{primary_bounding_box.north}°N,{" "}
                {primary_bounding_box.west}..{primary_bounding_box.east}°E]
              </p>
              <div className="mt-2 grid grid-cols-2 gap-y-1 border-t border-slate-200 pt-2 font-mono text-[11px]">
                <span>Sen&apos;s Slope/yr:</span>
                <strong>
                  {primary_stats.sens_slope_per_year >= 0 ? "+" : ""}
                  {primary_stats.sens_slope_per_year} {metadata.unit}
                </strong>
                <span>Sen&apos;s Slope/dec:</span>
                <strong>
                  {primary_stats.sens_slope_per_decade >= 0 ? "+" : ""}
                  {primary_stats.sens_slope_per_decade} {metadata.unit}
                </strong>
                <span>MK &tau; / Z:</span>
                <strong>
                  {primary_stats.mann_kendall_tau} / {primary_stats.z_score}
                </strong>
                <span>Deseasonalized p:</span>
                <strong>{fmtP(primary_stats.p_value)}</strong>
                <span>Student&apos;s t-test p:</span>
                <strong>{fmtP(primary_stats.t_test_p_value)}</strong>
                <span>Raw Seasonal p:</span>
                <strong>{fmtP(primary_stats.raw_p_value)}</strong>
              </div>
            </div>

            <div className="rounded-lg border border-slate-300 p-3 text-xs">
              <p className="font-bold text-slate-900">Teleconnection Comparison (B)</p>
              {pointB && comparison_stats ? (
                <>
                  <p className="text-slate-700">
                    {pointB.name} ({pointB.lat.toFixed(2)}°, {pointB.lon.toFixed(2)}°)
                  </p>
                  {comparison_bounding_box && (
                    <p className="font-mono text-[10px] text-slate-500">
                      MERRA-2 Cell: [{comparison_bounding_box.south}..{comparison_bounding_box.north}°N,{" "}
                      {comparison_bounding_box.west}..{comparison_bounding_box.east}°E]
                    </p>
                  )}
                  <div className="mt-2 grid grid-cols-2 gap-y-1 border-t border-slate-200 pt-2 font-mono text-[11px]">
                    <span>Region B Slope/yr:</span>
                    <strong>
                      {comparison_stats.sens_slope_per_year >= 0 ? "+" : ""}
                      {comparison_stats.sens_slope_per_year} {metadata.unit}
                    </strong>
                    <span>Region B MK p:</span>
                    <strong>{fmtP(comparison_stats.p_value)}</strong>
                    <span>Pearson Link (r):</span>
                    <strong>{teleconnection.cross_correlation_r?.toFixed(3) ?? "N/A"}</strong>
                    <span>Correlation p:</span>
                    <strong>{fmtP(teleconnection.cross_correlation_p_value)}</strong>
                    <span>STL Var Removed:</span>
                    <strong>{primary_stats.variance_reduction_pct}%</strong>
                    <span>Horizon Needed:</span>
                    <strong>
                      {primary_stats.is_significant ? "0 yrs (Confirmed)" : `~${primary_stats.years_to_significance} yrs`}
                    </strong>
                  </div>
                </>
              ) : (
                <div className="mt-2 space-y-1.5 text-slate-600">
                  <p>Single-region mode (no Comparison Region B selected).</p>
                  <div className="grid grid-cols-2 gap-y-1 border-t border-slate-200 pt-2 font-mono text-[11px] text-slate-800">
                    <span>STL Var Removed:</span>
                    <strong>{primary_stats.variance_reduction_pct}%</strong>
                    <span>Seasonal Swing:</span>
                    <strong>&plusmn;{primary_stats.seasonal_amplitude} {metadata.unit}</strong>
                    <span>Horizon Needed:</span>
                    <strong>
                      {primary_stats.is_significant ? "0 yrs (Confirmed)" : `~${primary_stats.years_to_significance} yrs`}
                    </strong>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Static Deseasonalized Chart Snapshot */}
          <div className="print-avoid-break rounded-lg border border-slate-300 p-3">
            <p className="mb-1 text-[11px] font-bold uppercase tracking-wide text-slate-700">
              Deseasonalized Anomaly Series, Linear Trend &amp; 95% Confidence Band ({metadata.unit})
            </p>
            <div className="h-[175px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ top: 6, right: 12, left: 0, bottom: 2 }}>
                  <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
                  <XAxis dataKey="timestamp" tick={{ fill: "#475569", fontSize: 10 }} minTickGap={40} />
                  <YAxis tick={{ fill: "#475569", fontSize: 10 }} width={48} domain={["auto", "auto"]} />
                  <ReferenceLine y={0} stroke="#94a3b8" strokeDasharray="3 3" />
                  <Area
                    type="monotone"
                    dataKey="ciRange"
                    stroke="none"
                    fill="#0ea5e9"
                    fillOpacity={0.18}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="anomaly"
                    stroke="#0284c7"
                    strokeWidth={1.3}
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="trend"
                    stroke={primary_stats.is_significant ? "#059669" : "#d97706"}
                    strokeWidth={2.2}
                    dot={false}
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Structured Physical Brief */}
          <div className="print-avoid-break space-y-2 rounded-lg border border-slate-300 bg-slate-50 p-3.5 text-xs leading-relaxed">
            <div>
              <h3 className="font-bold uppercase tracking-wide text-slate-800">
                1. Earth System Physical Mechanism
              </h3>
              <p className="mt-0.5 text-slate-700">{brief.physical_mechanism}</p>
            </div>
            <div>
              <h3 className="font-bold uppercase tracking-wide text-slate-800">
                2. Why Stripping Seasonality (STL) Was Necessary
              </h3>
              <p className="mt-0.5 text-slate-700">{brief.seasonality_note}</p>
            </div>
            <div>
              <h3 className="font-bold uppercase tracking-wide text-slate-800">
                3. Observation Window &amp; Statistical Power Assessment
              </h3>
              <p className="mt-0.5 text-slate-700">{brief.horizon_note}</p>
            </div>
            <div className="border-t border-slate-200 pt-2 text-[11px] text-slate-600">
              <p>
                <strong>Primary Literature &amp; Mission Reference:</strong> {brief.reference} ·{" "}
                <em>{metadata.plain_definition}</em>
              </p>
              <p className="mt-1 text-[10px] text-slate-500">
                <strong>Multi-Agency &amp; Statistical Methodology Sources:</strong> NASA Giovanni · GES DISC
                Hydrology Time Series · NASA AppEEARS · NOAA NCEI CDO · NASA NTRS 20090042747 (SeaWiFS Coastal
                Time-Series) · KNMI Climate Explorer · CSA RADARSAT Constellation Mission (RCM) · Geo.ca ·
                NASA/CNES/CSA SWOT Mission · CSA SAR Python Tutorial · Mann-Kendall &amp; Sen&apos;s Slope
                Significance Guides (&alpha; = 0.05).
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
