import { useCallback, useEffect, useRef, useState } from "react";
import {
  Compass,
  Database,
  FileText,
  HelpCircle,
  Loader2,
  MapPin,
  Play,
  Satellite,
  Sparkles,
  Wifi,
  WifiOff,
} from "lucide-react";
import SplitMap from "./SplitMap";
import type {
  GeoPoint,
  InvestigateResponse,
  ParameterMeta,
  PresetCaseMeta,
} from "./types";

const DETECTIVE_QUESTIONS: { question: string; parameter: string; hint: string }[] = [
  {
    question: "Where is warming fastest?",
    parameter: "T2M",
    hint: "MERRA-2 / AIRS 2m Air Temperature (°C)",
  },
  {
    question: "Where is drought worsening?",
    parameter: "GWETROOT",
    hint: "GLDAS / SMAP Root-Zone Soil Moisture",
  },
  {
    question: "Where is rainfall accelerating?",
    parameter: "PRECTOTCORR",
    hint: "GPM / MERRA-2 Corrected Precipitation",
  },
  {
    question: "Where are forest canopies drying?",
    parameter: "GWETPROF",
    hint: "MODIS NDVI / GLDAS Deep Soil Wetness",
  },
  {
    question: "Where is atmospheric humidity rising?",
    parameter: "QV2M",
    hint: "MERRA-2 2m Specific Humidity (g/kg)",
  },
];

export default function App() {
  const [cases, setCases] = useState<PresetCaseMeta[]>([]);
  const [parameters, setParameters] = useState<Record<string, ParameterMeta>>({});
  const [mode, setMode] = useState<"case" | "custom">("case");
  const [caseId, setCaseId] = useState<string | null>("case_3_arctic");
  const [parameter, setParameter] = useState<string>("T2M");
  const [pointA, setPointA] = useState<GeoPoint | null>({
    name: "Svalbard Archipelago",
    lat: 78.22,
    lon: 15.63,
  });
  const [pointB, setPointB] = useState<GeoPoint | null>({
    name: "Subpolar North Atlantic",
    lat: 54.0,
    lon: -32.0,
  });
  const [activeTarget, setActiveTarget] = useState<"A" | "B">("A");
  const [windowRange, setWindowRange] = useState<[number, number]>([1990, 2025]);
  const [mkVariant, setMkVariant] = useState<"standard" | "hamed_rao">("standard");
  const [result, setResult] = useState<InvestigateResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [showTooltip, setShowTooltip] = useState<boolean>(false);
  const [dossierOpen, setDossierOpen] = useState<boolean>(false);
  const [fitVersion, setFitVersion] = useState<number>(1);

  const abortRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<number | null>(null);

  const runInvestigation = useCallback(
    async (opts?: {
      nextCaseId?: string | null;
      nextParam?: string;
      nextA?: GeoPoint | null;
      nextB?: GeoPoint | null;
      nextWindow?: [number, number];
      nextMk?: "standard" | "hamed_rao";
    }) => {
      const targetA = opts?.nextA !== undefined ? opts.nextA : pointA;
      if (!targetA) return;
      const targetB = opts?.nextB !== undefined ? opts.nextB : pointB;
      const targetParam = opts?.nextParam ?? parameter;
      const targetCaseId = opts?.nextCaseId !== undefined ? opts.nextCaseId : caseId;
      const targetWin = opts?.nextWindow ?? windowRange;
      const targetMk = opts?.nextMk ?? mkVariant;

      if (abortRef.current) {
        abortRef.current.abort();
      }
      const controller = new AbortController();
      abortRef.current = controller;

      setLoading(true);
      setError(null);

      try {
        const resp = await fetch("/api/investigate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: controller.signal,
          body: JSON.stringify({
            case_id: targetCaseId,
            parameter: targetParam,
            primary_point: targetA,
            comparison_point: targetB,
            start_year: targetWin[0],
            end_year: targetWin[1],
            mk_variant: targetMk,
          }),
        });
        if (!resp.ok) {
          const errJson = await resp.json().catch(() => ({}));
          throw new Error(errJson.detail || `Backend returned HTTP ${resp.status}`);
        }
        const data: InvestigateResponse = await resp.json();
        setResult(data);
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        setError((err as Error).message || "Unable to connect to TerraShift backend.");
      } finally {
        setLoading(false);
      }
    },
    [caseId, mkVariant, parameter, pointA, pointB, windowRange]
  );

  // Load case catalog + run initial Case 3 (or Case 1) on mount
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const resp = await fetch("/api/cases");
        if (resp.ok) {
          const data = await resp.json();
          if (!mounted) return;
          setCases(data.cases || []);
          setParameters(data.parameters || {});
          const initial = (data.cases || []).find((c: PresetCaseMeta) => c.case_id === "case_3_arctic") || data.cases?.[0];
          if (initial) {
            setCaseId(initial.case_id);
            setParameter(initial.parameter);
            setPointA(initial.primary_point);
            setPointB(initial.comparison_point);
            setWindowRange(initial.default_window);
            setFitVersion((v) => v + 1);
            await runInvestigation({
              nextCaseId: initial.case_id,
              nextParam: initial.parameter,
              nextA: initial.primary_point,
              nextB: initial.comparison_point,
              nextWindow: initial.default_window,
            });
            return;
          }
        }
      } catch {
        // fallback initial run
      }
      if (mounted) {
        await runInvestigation();
      }
    })();
    return () => {
      mounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSelectCase = (c: PresetCaseMeta) => {
    setMode("case");
    setCaseId(c.case_id);
    setParameter(c.parameter);
    setPointA(c.primary_point);
    setPointB(c.comparison_point);
    setWindowRange(c.default_window);
    setFitVersion((v) => v + 1);
    runInvestigation({
      nextCaseId: c.case_id,
      nextParam: c.parameter,
      nextA: c.primary_point,
      nextB: c.comparison_point,
      nextWindow: c.default_window,
    });
  };

  const handleSelectQuestion = (paramCode: string) => {
    setMode("custom");
    setCaseId(null);
    setParameter(paramCode);
    if (pointA) {
      runInvestigation({ nextCaseId: null, nextParam: paramCode });
    }
  };

  const handleSelectPoint = (target: "A" | "B", lat: number, lon: number) => {
    setMode("custom");
    setCaseId(null);
    const label = `${lat >= 0 ? `${lat.toFixed(2)}°N` : `${Math.abs(lat).toFixed(2)}°S`}, ${
      lon >= 0 ? `${lon.toFixed(2)}°E` : `${Math.abs(lon).toFixed(2)}°W`
    }`;
    const newPt: GeoPoint = {
      name: target === "A" ? `Custom A (${label})` : `Custom B (${label})`,
      lat,
      lon,
    };

    if (target === "A") {
      setPointA(newPt);
      if (!pointB) {
        setActiveTarget("B");
      }
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
      debounceRef.current = window.setTimeout(() => {
        runInvestigation({ nextCaseId: null, nextA: newPt, nextB: pointB });
      }, 180);
    } else {
      setPointB(newPt);
      if (pointA) {
        if (debounceRef.current) window.clearTimeout(debounceRef.current);
        debounceRef.current = window.setTimeout(() => {
          runInvestigation({ nextCaseId: null, nextA: pointA, nextB: newPt });
        }, 180);
      }
    }
  };

  const handleClearPointB = () => {
    setMode("custom");
    setCaseId(null);
    setPointB(null);
    setActiveTarget("B");
    if (pointA) {
      runInvestigation({ nextCaseId: null, nextA: pointA, nextB: null });
    }
  };

  const handleSwapPoints = () => {
    if (!pointA || !pointB) return;
    setMode("custom");
    setCaseId(null);
    const nextA = { ...pointB };
    const nextB = { ...pointA };
    setPointA(nextA);
    setPointB(nextB);
    runInvestigation({ nextCaseId: null, nextA, nextB });
  };

  const activeMeta = parameters[parameter] ?? result?.response.metadata;
  const activeStep = !pointA ? 2 : result ? 3 : 2;
  const dataStatus = result?.response.data_status;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="app-shell-hide-on-print mx-auto flex max-w-[1440px] flex-col gap-4 px-4 py-4 sm:px-6">
        {/* Brand & 3-Step Detective Wizard Header */}
        <header className="flex flex-col gap-4 rounded-2xl border border-slate-800 bg-gradient-to-br from-slate-900 via-slate-900/95 to-slate-950 p-4 shadow-xl">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/15 ring-1 ring-cyan-400/40">
                <Satellite className="h-5 w-5 text-cyan-300" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-lg font-bold tracking-tight text-white sm:text-xl">
                    TerraShift
                  </h1>
                  <span className="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-cyan-300">
                    NASA Earth System Trend Detective
                  </span>
                </div>
                <p className="text-xs text-slate-400">
                  Strip seasonal cycles via STL decomposition, validate trends with Mann-Kendall &amp; Sen&apos;s slope, and inspect global teleconnections.
                </p>
              </div>
            </div>

            {/* Status & Dossier Trigger */}
            <div className="flex flex-wrap items-center gap-2">
              {dataStatus === "cache" && (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-300">
                  <Database className="h-3.5 w-3.5" /> Cached Case / Instant
                </span>
              )}
              {dataStatus === "live" && (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-medium text-cyan-300">
                  <Wifi className="h-3.5 w-3.5" /> Live NASA POWER API
                </span>
              )}
              {dataStatus === "offline_fallback" && (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs font-medium text-amber-300">
                  <WifiOff className="h-3.5 w-3.5" /> Offline Cache Fallback
                </span>
              )}

              <button
                type="button"
                disabled={!result}
                onClick={() => setDossierOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-xl bg-slate-100 px-3.5 py-2 text-xs font-bold text-slate-950 shadow transition hover:bg-cyan-200 disabled:opacity-40"
              >
                <FileText className="h-3.5 w-3.5" />
                Field Dossier (PDF)
              </button>
            </div>
          </div>

          {/* 3-Step Detective Progress Strip */}
          <div className="grid grid-cols-1 gap-2 border-t border-slate-800/80 pt-3 sm:grid-cols-3">
            {[
              { step: 1, title: "1. Pick a Mystery", desc: "Load a Case File or choose a Plain-English Question" },
              { step: 2, title: "2. Place Region Markers", desc: "Click Marker A (primary) & optional Marker B (teleconnection)" },
              { step: 3, title: "3. Uncover & Verify", desc: "Strip STL seasonality, test window length, export Dossier" },
            ].map((item) => {
              const active = activeStep === item.step;
              return (
                <div
                  key={item.step}
                  className={`flex items-center gap-2.5 rounded-xl border px-3 py-2 text-xs transition ${
                    active
                      ? "border-cyan-500/40 bg-cyan-500/10 text-cyan-100"
                      : "border-slate-800/80 bg-slate-900/50 text-slate-400"
                  }`}
                >
                  <Compass className={`h-4 w-4 shrink-0 ${active ? "text-cyan-300" : "text-slate-500"}`} />
                  <div>
                    <p className="font-semibold">{item.title}</p>
                    <p className="text-[11px] opacity-80">{item.desc}</p>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Earth Detective Control Bar: Case Files + Plain-English Question Picker */}
          <div className="flex flex-col gap-3 rounded-xl border border-slate-800 bg-slate-950/60 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="mr-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  Case Files:
                </span>
                {cases.map((c) => {
                  const selected = mode === "case" && caseId === c.case_id;
                  return (
                    <button
                      key={c.case_id}
                      type="button"
                      onClick={() => handleSelectCase(c)}
                      className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${
                        selected
                          ? "bg-cyan-500 text-slate-950 shadow-sm shadow-cyan-500/30"
                          : "bg-slate-800/90 text-slate-300 hover:bg-slate-700"
                      }`}
                    >
                      {c.short_title}
                    </button>
                  );
                })}
                <button
                  type="button"
                  onClick={() => {
                    setMode("custom");
                    setCaseId(null);
                  }}
                  className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${
                    mode === "custom"
                      ? "bg-indigo-500 text-white"
                      : "bg-slate-800/90 text-slate-300 hover:bg-slate-700"
                  }`}
                >
                  <MapPin className="h-3 w-3" />
                  Custom Click-Anywhere
                </button>
              </div>

              <button
                type="button"
                onClick={() => runInvestigation()}
                disabled={loading || !pointA}
                className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3.5 py-1.5 text-xs font-bold text-slate-950 transition hover:bg-emerald-400 disabled:opacity-50"
              >
                {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                Run Investigation
              </button>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-800/70 pt-2.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  Mystery Question:
                </span>
                <select
                  value={parameter}
                  onChange={(e) => handleSelectQuestion(e.target.value)}
                  className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-100 outline-none focus:border-cyan-400"
                >
                  {DETECTIVE_QUESTIONS.map((q) => (
                    <option key={q.parameter} value={q.parameter}>
                      {q.question} ({q.parameter})
                    </option>
                  ))}
                  <option value="PS">Where are pressure systems shifting? (PS)</option>
                </select>

                <button
                  type="button"
                  onClick={() => setShowTooltip((s) => !s)}
                  className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs text-cyan-300 hover:bg-slate-800"
                >
                  <HelpCircle className="h-3.5 w-3.5" />
                  What does NASA measure?
                </button>
              </div>

              <label className="flex items-center gap-2 text-xs text-slate-400">
                <span>MK Test:</span>
                <select
                  value={mkVariant}
                  onChange={(e) => {
                    const nextMk = e.target.value as "standard" | "hamed_rao";
                    setMkVariant(nextMk);
                    runInvestigation({ nextMk });
                  }}
                  className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-200"
                >
                  <option value="standard">Standard Mann-Kendall</option>
                  <option value="hamed_rao">Hamed-Rao Autocorrelation-Adjusted</option>
                </select>
              </label>
            </div>

            {/* Student-Friendly NASA Mission Translator Card */}
            {(showTooltip || activeMeta) && activeMeta && (
              <div
                className={`flex flex-wrap items-center justify-between gap-2 rounded-xl border border-cyan-500/20 bg-cyan-950/20 px-3 py-2 text-xs ${
                  showTooltip ? "ring-1 ring-cyan-400/40" : ""
                }`}
              >
                <div className="flex items-start gap-2">
                  <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-cyan-300" />
                  <div>
                    <span className="font-semibold text-cyan-200">
                      {activeMeta.parameter_name} ({activeMeta.parameter_code})
                    </span>{" "}
                    <span className="text-slate-300">— {activeMeta.plain_definition}</span>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                  <span className="rounded bg-slate-900 px-2 py-0.5 text-slate-200">
                    Unit: {activeMeta.unit}
                  </span>
                  <span className="rounded bg-slate-900 px-2 py-0.5 text-slate-200">
                    {activeMeta.mission_source}
                  </span>
                  <span className="rounded bg-slate-900 px-2 py-0.5 text-slate-300">
                    {activeMeta.resolution}
                  </span>
                </div>
              </div>
            )}
          </div>
        </header>

        {error && (
          <div className="rounded-xl border border-rose-500/40 bg-rose-950/60 px-4 py-3 text-xs text-rose-200">
            <strong>Investigation Error:</strong> {error}
          </div>
        )}

        {result?.response.fallback_note && (
          <div className="rounded-xl border border-amber-500/40 bg-amber-950/40 px-4 py-2 text-xs text-amber-200">
            {result.response.fallback_note}
          </div>
        )}

        {/* Dual Teleconnection SplitMap */}
        <SplitMap
          parameter={parameter}
          pointA={pointA}
          pointB={pointB}
          activeTarget={activeTarget}
          onChangeActiveTarget={setActiveTarget}
          onSelectPoint={handleSelectPoint}
          onClearPointB={handleClearPointB}
          onSwapPoints={handleSwapPoints}
          primaryStats={result?.response.primary_stats ?? null}
          comparisonStats={result?.response.comparison_stats ?? null}
          teleconnection={result?.response.teleconnection ?? null}
          primaryBBox={result?.response.primary_bounding_box ?? null}
          comparisonBBox={result?.response.comparison_bounding_box ?? null}
          fitVersion={fitVersion}
        />

        {/* Sprint 3 placeholder preview before Sprint 4 TrendLab replaces it */}
        {result && (
          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 text-xs text-slate-300">
            <p className="font-semibold text-white">{result.response.detective_brief.verdict_headline}</p>
            <p className="mt-1 text-slate-400">{result.response.detective_brief.physical_mechanism}</p>
          </div>
        )}

        {dossierOpen && result && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
            <div className="rounded-2xl border border-slate-700 bg-slate-900 p-6 text-sm">
              <p>Dossier preview loading...</p>
              <button
                type="button"
                onClick={() => setDossierOpen(false)}
                className="mt-3 rounded bg-cyan-500 px-3 py-1 text-slate-950"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
