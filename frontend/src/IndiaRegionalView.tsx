import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Calendar,
  Compass,
  Globe2,
  Loader2,
  MapPin,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import type {
  IndiaPhysiographicRegion,
  IndiaRegionalComparisonResponse,
  IndiaRegionsResponse,
  IndiaSeasonalAnalysisResponse,
  PresetCaseMeta,
} from "./types";

interface IndiaRegionalViewProps {
  apiBase: string;
  cases: PresetCaseMeta[];
  onSelectRegionForMap?: (lat: number, lon: number, name: string, parameter: string) => void;
}

const SEASON_ORDER = ["JF", "MAM", "JJAS", "OND"] as const;

const INDIA_PARAMETERS = [
  { code: "T2M", label: "2m Air Temperature (°C)" },
  { code: "PRECTOTCORR", label: "Corrected Precipitation (mm/day)" },
  { code: "GWETROOT", label: "Root-Zone Soil Wetness (0–1)" },
  { code: "GWETPROF", label: "Profile Soil Wetness (0–1)" },
  { code: "QV2M", label: "2m Specific Humidity (g/kg)" },
];

export default function IndiaRegionalView({
  apiBase,
  cases,
  onSelectRegionForMap,
}: IndiaRegionalViewProps) {
  const [regionsData, setRegionsData] = useState<IndiaRegionsResponse | null>(null);
  const [comparison, setComparison] = useState<IndiaRegionalComparisonResponse | null>(null);
  const [selectedCaseId, setSelectedCaseId] = useState<string>(cases[0]?.case_id || "case_1_monsoon");
  const [selectedRegion, setSelectedRegion] = useState<IndiaPhysiographicRegion | null>(null);
  const [parameter, setParameter] = useState<string>("T2M");
  const [seasonalReport, setSeasonalReport] = useState<IndiaSeasonalAnalysisResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [compLoading, setCompLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${apiBase}/api/india/regions`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d: IndiaRegionsResponse | null) => {
        if (d) setRegionsData(d);
      })
      .catch(() => {});

    setCompLoading(true);
    fetch(`${apiBase}/api/india/regional-comparison?start_year=1990&end_year=2025`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d: IndiaRegionalComparisonResponse | null) => {
        if (d) setComparison(d);
      })
      .catch(() => {})
      .finally(() => setCompLoading(false));
  }, [apiBase]);

  const runCaseAnalysis = async (caseId: string) => {
    setSelectedRegion(null);
    setSelectedCaseId(caseId);
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${apiBase}/api/india/seasonal-analysis`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          case_id: caseId,
          start_year: 1981,
          end_year: 2025,
          baseline_start: 1991,
          baseline_end: 2020,
        }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err?.detail || `HTTP ${resp.status}`);
      }
      const data: IndiaSeasonalAnalysisResponse = await resp.json();
      setSeasonalReport(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to run seasonal analysis.");
    } finally {
      setLoading(false);
    }
  };

  const runRegionAnalysis = async (region: IndiaPhysiographicRegion, paramCode: string) => {
    setSelectedRegion(region);
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${apiBase}/api/india/seasonal-analysis`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lat: region.lat,
          lon: region.lon,
          parameter: paramCode,
          start_year: 1990,
          end_year: 2025,
          baseline_start: 1991,
          baseline_end: 2020,
        }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err?.detail || `HTTP ${resp.status}`);
      }
      const data: IndiaSeasonalAnalysisResponse = await resp.json();
      setSeasonalReport(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to retrieve regional seasonal analysis.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (cases.length > 0 && !seasonalReport) {
      void runCaseAnalysis(cases[0].case_id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cases]);

  const eda = seasonalReport?.analysis?.eda;
  const seasons = seasonalReport?.analysis?.seasons;

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-6 px-4 py-6 sm:px-6">
      {/* Header Banner */}
      <section className="surface-panel rounded-2xl border border-slate-800 bg-slate-900/75 p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-1.5">
            <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-semibold text-cyan-300">
              <Globe2 className="h-3.5 w-3.5" />
              India-Exclusive Climatology · 6.0°N–37.5°N, 68.0°E–97.5°E
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
              India Seasonal &amp; Physiographic Trend Observatory
            </h1>
            <p className="max-w-3xl text-sm text-slate-300">
              Evaluates India&apos;s four IMD climatological seasons (Winter JF, Pre-Monsoon MAM,
              Southwest Monsoon JJAS, Post-Monsoon OND) using Mann-Kendall, Sen&apos;s slope, OLS,
              and Holm-Bonferroni multiple-hypothesis correction against a 1991–2020 baseline.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-xs font-semibold text-slate-400" htmlFor="india-param-select">
              Region Variable:
            </label>
            <select
              id="india-param-select"
              value={parameter}
              onChange={(e) => {
                const nextParam = e.target.value;
                setParameter(nextParam);
                if (selectedRegion) {
                  void runRegionAnalysis(selectedRegion, nextParam);
                }
              }}
              className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs font-medium text-slate-100 outline-none focus:border-cyan-400"
            >
              {INDIA_PARAMETERS.map((p) => (
                <option key={p.code} value={p.code}>
                  {p.code} — {p.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </section>

      {/* 10 Indian Physiographic Regions Selector */}
      <section className="surface-panel rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Compass className="h-4 w-4 text-cyan-400" />
            <h2 className="text-base font-bold text-white">
              10 Indian Physiographic &amp; Climatic Regions
            </h2>
          </div>
          <span className="text-xs text-slate-400">
            Click any region to compute live 4-season NASA POWER trends ({parameter})
          </span>
        </div>

        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-5">
          {(regionsData?.physiographic_regions ?? []).map((reg) => {
            const isActive = selectedRegion?.id === reg.id;
            return (
              <button
                key={reg.id}
                type="button"
                onClick={() => void runRegionAnalysis(reg, parameter)}
                className={`flex flex-col items-start gap-1 rounded-xl border p-3 text-left transition ${
                  isActive
                    ? "border-cyan-400/70 bg-cyan-500/15 text-white"
                    : "border-slate-800 bg-slate-950/60 text-slate-200 hover:border-slate-600 hover:bg-slate-900"
                }`}
              >
                <div className="flex w-full items-center justify-between gap-1">
                  <span className="text-xs font-bold text-cyan-300">{reg.name}</span>
                  <MapPin className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                </div>
                <span className="font-mono text-xs text-slate-400">
                  {reg.lat.toFixed(2)}°N, {reg.lon.toFixed(2)}°E
                </span>
                <span className="line-clamp-2 text-xs text-slate-300">{reg.focus}</span>
              </button>
            );
          })}
        </div>

        {/* Preset India Case Pills */}
        {cases.length > 0 && (
          <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-800/80 pt-3">
            <span className="text-xs font-semibold text-slate-400">Cached 1981–2025 Case Files:</span>
            {cases.map((c) => (
              <button
                key={c.case_id}
                type="button"
                onClick={() => void runCaseAnalysis(c.case_id)}
                className={`rounded-lg border px-2.5 py-1 text-xs font-medium transition ${
                  !selectedRegion && selectedCaseId === c.case_id
                    ? "border-cyan-400/60 bg-cyan-500/20 text-cyan-200"
                    : "border-slate-700 bg-slate-950 text-slate-300 hover:border-slate-500"
                }`}
              >
                {c.title}
              </button>
            ))}
          </div>
        )}
      </section>

      {/* Active Seasonal Analysis Results */}
      <section className="surface-panel rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-bold text-white">
              <Calendar className="h-4 w-4 text-cyan-400" />
              IMD 4-Season Breakdown:{" "}
              <span className="text-cyan-300">
                {selectedRegion
                  ? `${selectedRegion.name} (${parameter})`
                  : seasonalReport?.meta?.location || "Loading..."}
              </span>
            </h2>
            {seasonalReport?.meta && (
              <p className="mt-0.5 text-xs text-slate-400">
                Variable: <strong className="text-slate-200">{seasonalReport.meta.parameter}</strong>{" "}
                ({seasonalReport.meta.units || "native units"}) · Source:{" "}
                <strong className="text-slate-200">{seasonalReport.meta.source_mode}</strong> ·
                Baseline: <strong className="text-slate-200">{seasonalReport.analysis.baseline_period}</strong>
              </p>
            )}
          </div>
          {selectedRegion && onSelectRegionForMap && (
            <button
              type="button"
              onClick={() =>
                onSelectRegionForMap(
                  selectedRegion.lat,
                  selectedRegion.lon,
                  selectedRegion.name,
                  parameter
                )
              }
              className="rounded-xl border border-cyan-500/40 bg-cyan-500/15 px-3 py-1.5 text-xs font-semibold text-cyan-200 hover:bg-cyan-500/25"
            >
              Open in Trend Lab
            </button>
          )}
        </div>

        {loading && (
          <div className="flex items-center gap-2 py-8 text-sm text-cyan-300">
            <Loader2 className="h-4 w-4 animate-spin" />
            Computing seasonal Mann-Kendall, Sen&apos;s slope, and Holm-Bonferroni statistics...
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 rounded-xl border border-rose-500/40 bg-rose-950/30 p-3 text-xs text-rose-200">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {error}
          </div>
        )}

        {!loading && seasonalReport && seasons && (
          <>
            {/* EDA Summary Strip */}
            {eda && (
              <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
                <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
                  <div className="text-xs text-slate-400">Valid Months</div>
                  <div className="font-mono text-base font-bold text-white">
                    {eda.n_valid} / {eda.n_total}
                  </div>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
                  <div className="text-xs text-slate-400">Mean</div>
                  <div className="font-mono text-base font-bold text-cyan-300">
                    {eda.mean !== null ? eda.mean.toFixed(3) : "—"}
                  </div>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
                  <div className="text-xs text-slate-400">Std Dev</div>
                  <div className="font-mono text-base font-bold text-slate-200">
                    {eda.std !== null ? eda.std.toFixed(3) : "—"}
                  </div>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
                  <div className="text-xs text-slate-400">Min / Max</div>
                  <div className="font-mono text-sm font-bold text-slate-200">
                    {eda.min !== null && eda.max !== null
                      ? `${eda.min.toFixed(2)} / ${eda.max.toFixed(2)}`
                      : "—"}
                  </div>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
                  <div className="text-xs text-slate-400">Coverage</div>
                  <div className="font-mono text-base font-bold text-slate-200">
                    {eda.start_year ?? "—"}–{eda.end_year ?? "—"}
                  </div>
                </div>
              </div>
            )}

            {/* 4 Season Cards */}
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
              {SEASON_ORDER.map((code) => {
                const s = seasons[code];
                if (!s) return null;
                const slope = s.sen_slope_per_decade ?? 0;
                const isUp = slope > 0;
                return (
                  <div
                    key={code}
                    className="flex flex-col justify-between gap-2 rounded-xl border border-slate-800 bg-slate-950/75 p-4"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <span className="font-mono text-xs font-bold text-cyan-400">{code}</span>
                        <h3 className="text-sm font-bold text-white">{s.name}</h3>
                      </div>
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-bold ${
                          s.significant_holm
                            ? "border border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
                            : "border border-slate-700 bg-slate-800 text-slate-300"
                        }`}
                      >
                        {s.significant_holm ? "Holm p < 0.05" : "Not sig (Holm)"}
                      </span>
                    </div>

                    <div className="flex items-center gap-1.5 font-mono text-lg font-bold text-white">
                      {isUp ? (
                        <TrendingUp className="h-4 w-4 text-amber-400" />
                      ) : (
                        <TrendingDown className="h-4 w-4 text-cyan-400" />
                      )}
                      <span>
                        {slope >= 0 ? "+" : ""}
                        {s.sen_slope_per_decade !== null ? s.sen_slope_per_decade.toFixed(4) : "—"}/dec
                      </span>
                    </div>

                    <div className="space-y-1 text-xs text-slate-400">
                      <div className="flex justify-between">
                        <span>OLS Slope:</span>
                        <span className="font-mono text-slate-200">
                          {s.ols_slope_per_decade !== null
                            ? `${s.ols_slope_per_decade >= 0 ? "+" : ""}${s.ols_slope_per_decade.toFixed(4)}/dec`
                            : "—"}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span>MK p / Holm p:</span>
                        <span className="font-mono text-slate-200">
                          {s.mk_p_value !== null ? s.mk_p_value.toFixed(4) : "—"} /{" "}
                          {s.holm_adjusted_p !== null ? s.holm_adjusted_p.toFixed(4) : "—"}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span>Lag-1 Autocorr (r₁):</span>
                        <span className="font-mono text-slate-200">
                          {s.lag1_autocorr !== null ? s.lag1_autocorr.toFixed(3) : "—"}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Annual Anomaly Extremes */}
            <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3.5">
                <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-amber-300">
                  Top Positive Annual Anomalies (vs {seasonalReport.analysis.baseline_period})
                </h4>
                <div className="flex flex-wrap gap-2">
                  {(seasonalReport.analysis.top_positive_years ?? []).map((yr) => (
                    <span
                      key={yr.year}
                      className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 font-mono text-xs text-amber-200"
                    >
                      {yr.year}: {yr.anomaly >= 0 ? "+" : ""}
                      {yr.anomaly.toFixed(3)}
                    </span>
                  ))}
                </div>
              </div>
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3.5">
                <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-cyan-300">
                  Top Negative Annual Anomalies (vs {seasonalReport.analysis.baseline_period})
                </h4>
                <div className="flex flex-wrap gap-2">
                  {(seasonalReport.analysis.top_negative_years ?? []).map((yr) => (
                    <span
                      key={yr.year}
                      className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-1 font-mono text-xs text-cyan-200"
                    >
                      {yr.year}: {yr.anomaly >= 0 ? "+" : ""}
                      {yr.anomaly.toFixed(3)}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </>
        )}
      </section>

      {/* Cross-Region Comparison Table */}
      <section className="surface-panel rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-cyan-400" />
            <h2 className="text-base font-bold text-white">
              India Regional Trend Matrix (1990–2025, NASA POWER)
            </h2>
          </div>
          {compLoading && <Loader2 className="h-4 w-4 animate-spin text-cyan-300" />}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-xs">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400">
                <th className="py-2 pr-3 font-semibold">Location</th>
                <th className="py-2 pr-3 font-semibold">Param</th>
                <th className="py-2 pr-3 font-semibold">Overall Sen&apos;s Slope</th>
                <th className="py-2 pr-3 font-semibold">JF (Winter)</th>
                <th className="py-2 pr-3 font-semibold">MAM (Pre-Monsoon)</th>
                <th className="py-2 pr-3 font-semibold">JJAS (Monsoon)</th>
                <th className="py-2 font-semibold">OND (Post-Monsoon)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70">
              {(comparison?.rows ?? []).map((row) => (
                <tr key={`${row.case_id}-${row.role}`} className="text-slate-200 hover:bg-slate-800/30">
                  <td className="py-2.5 pr-3">
                    <div className="font-semibold text-white">{row.location}</div>
                    <div className="font-mono text-xs text-slate-400">
                      {row.lat.toFixed(2)}°N, {row.lon.toFixed(2)}°E
                    </div>
                  </td>
                  <td className="py-2.5 pr-3 font-mono text-cyan-300">{row.parameter}</td>
                  <td className="py-2.5 pr-3 font-mono">
                    {row.sen_slope_per_decade !== null
                      ? `${row.sen_slope_per_decade >= 0 ? "+" : ""}${row.sen_slope_per_decade.toFixed(4)}/dec`
                      : "—"}
                    {row.mk_significant ? (
                      <span className="ml-1.5 text-xs text-emerald-300">*</span>
                    ) : null}
                  </td>
                  {SEASON_ORDER.map((sCode) => {
                    const sd = row.seasons?.[sCode];
                    const val = sd?.sen_slope_per_decade;
                    return (
                      <td key={sCode} className="py-2.5 pr-3 font-mono">
                        {val !== null && val !== undefined
                          ? `${val >= 0 ? "+" : ""}${val.toFixed(4)}`
                          : "—"}
                        {sd?.significant_holm ? (
                          <span className="ml-1 text-xs font-bold text-emerald-300">*</span>
                        ) : null}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          * Indicates statistical significance at α = 0.05 after Holm-Bonferroni correction across
          the 4 IMD seasons (or Hamed-Rao variance-corrected Mann-Kendall for overall monthly series).
        </p>
      </section>
    </div>
  );
}
