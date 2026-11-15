import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  BarChart3,
  BookOpen,
  Compass,
  Database,
  ExternalLink,
  FileText,
  Globe2,
  HelpCircle,
  Home,
  LineChart,
  Loader2,
  MapPin,
  Menu,
  Play,
  Satellite,
  Sparkles,
  Upload,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";
import SplitMap from "./SplitMap";
import TrendLab from "./TrendLab";
import DossierModal from "./DossierModal";
import HomePage, { type NavSection } from "./HomePage";
import StatsDashboard from "./StatsDashboard";
import { AboutView, HelpGuideView } from "./AboutAndHelp";
import type {
  GeoPoint,
  InvestigateResponse,
  ParameterMeta,
  PartnerIntelResponse,
  PresetCaseMeta,
} from "./types";

const DETECTIVE_QUESTIONS: { question: string; parameter: string; hint: string }[] = [
  {
    question: "Where is warming fastest?",
    parameter: "T2M",
    hint: "MERRA-2 / AIRS / CSA GeoMet 2m Air Temp (°C)",
  },
  {
    question: "Where is drought worsening?",
    parameter: "GWETROOT",
    hint: "GLDAS / SMAP / GES DISC Root-Zone Soil Moisture",
  },
  {
    question: "Where is rainfall accelerating?",
    parameter: "PRECTOTCORR",
    hint: "GPM / MERRA-2 / Giovanni Corrected Precipitation",
  },
  {
    question: "Where are forest canopies drying?",
    parameter: "GWETPROF",
    hint: "MODIS NDVI / AppEEARS / GLDAS Deep Soil Wetness",
  },
  {
    question: "Where is atmospheric humidity rising?",
    parameter: "QV2M",
    hint: "MERRA-2 2m Specific Humidity (g/kg)",
  },
];

function buildSampleGiovanniCsv(): string {
  const rows = [
    "# SYNTHETIC_DEMO_DATA: true",
    "# WARNING: Synthetic demonstration data generated for format testing only — NOT real NASA Giovanni or SeaWiFS observations.",
    "# Format: NASA Giovanni Area-Averaged Time Series CSV",
    "# Demo Region: Mississippi River Delta Plume (29.15N, 89.25W)",
    "time,chlorophyll_a_mg_m3",
  ];
  for (let yr = 1998; yr <= 2024; yr++) {
    for (let m = 1; m <= 12; m++) {
      const t = yr - 1998 + (m - 1) / 12;
      const seasonal = 2.4 * Math.sin((2 * Math.PI * (m - 3)) / 12);
      const val = 4.2 + 0.065 * t + seasonal + ((yr * 7 + m * 13) % 11 - 5) * 0.08;
      rows.push(`${yr}-${String(m).padStart(2, "0")}-01,${val.toFixed(4)}`);
    }
  }
  return rows.join("\n");
}

function buildSampleKnmiDat(): string {
  const rows = [
    "# SYNTHETIC_DEMO_DATA: true",
    "# WARNING: Synthetic demonstration data generated for format testing only — NOT real KNMI or CSA hydrometric observations.",
    "# Format: KNMI Climate Explorer Monthly Table (.dat)",
    "# Demo Station: Mackenzie River / Beaufort Delta Benchmark (68.80N, 134.40W)",
  ];
  for (let yr = 1995; yr <= 2024; yr++) {
    const vals: string[] = [];
    for (let m = 1; m <= 12; m++) {
      const t = yr - 1995 + (m - 1) / 12;
      const seasonal = 1.85 * Math.cos((2 * Math.PI * (m - 6)) / 12);
      const v = 1.1 + 0.028 * t + seasonal + ((yr * 3 + m * 5) % 9 - 4) * 0.04;
      vals.push(v.toFixed(3));
    }
    rows.push(`${yr} ${vals.join(" ")}`);
  }
  return rows.join("\n");
}

const API_BASE = ((import.meta as unknown as { env?: Record<string, string> }).env?.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

function parseApiErrorMessage(errJson: unknown, defaultMessage: string): string {
  if (!errJson || typeof errJson !== "object") return defaultMessage;
  const payload = errJson as { detail?: unknown; message?: unknown };
  if (typeof payload.detail === "string") return payload.detail;
  if (Array.isArray(payload.detail)) {
    return payload.detail
      .map((d: any) =>
        d.msg ? `${d.loc ? d.loc.filter((x: any) => x !== "body").join(".") + ": " : ""}${d.msg}` : JSON.stringify(d)
      )
      .join("; ");
  }
  if (typeof payload.message === "string") return String(payload.message);
  return defaultMessage;
}

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
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);

  // Multi-Agency Partner Hub & Universal Series Importer states
  const [showPartnerHub, setShowPartnerHub] = useState<boolean>(false);
  const [partnerIntel, setPartnerIntel] = useState<PartnerIntelResponse | null>(null);
  const [intelLoading, setIntelLoading] = useState<boolean>(false);
  const [showImportModal, setShowImportModal] = useState<boolean>(false);
  const [importText, setImportText] = useState<string>("");
  const [importRegionName, setImportRegionName] = useState<string>("NASA Giovanni / Partner Series");
  const [importUnit, setImportUnit] = useState<string>("mg/m³");
  const [importSourceHint, setImportSourceHint] = useState<string>("auto");

  const abortRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<number | null>(null);

  const fetchPartnerMetadata = useCallback(
    async (lat: number, lon: number, param: string, sYr: number, eYr: number) => {
      setIntelLoading(true);
      try {
        const qs = new URLSearchParams({
          lat: String(lat),
          lon: String(lon),
          parameter: param,
          start_year: String(sYr),
          end_year: String(eYr),
        });
        const resp = await fetch(`${API_BASE}/api/partner-intel?${qs.toString()}`);
        if (resp.ok) {
          const data: PartnerIntelResponse = await resp.json();
          setPartnerIntel(data);
        }
      } catch {
        // non-blocking metadata enrichment
      } finally {
        setIntelLoading(false);
      }
    },
    []
  );

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
        const resp = await fetch(`${API_BASE}/api/investigate`, {
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
          throw new Error(parseApiErrorMessage(errJson, `Backend returned HTTP ${resp.status}`));
        }
        const data: InvestigateResponse = await resp.json();
        setResult(data);
        setApiOnline(true);
        fetchPartnerMetadata(targetA.lat, targetA.lon, targetParam, targetWin[0], targetWin[1]);
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        setError((err as Error).message || "Unable to connect to TerraShift backend.");
      } finally {
        setLoading(false);
      }
    },
    [caseId, fetchPartnerMetadata, mkVariant, parameter, pointA, pointB, windowRange]
  );

  const loadInitialCases = useCallback(async () => {
    try {
      const [healthResp, casesResp] = await Promise.allSettled([
        fetch(`${API_BASE}/api/health`),
        fetch(`${API_BASE}/api/cases`),
      ]);
      if (healthResp.status === "fulfilled" && healthResp.value.ok) {
        setApiOnline(true);
      } else {
        setApiOnline(false);
      }

      if (casesResp.status === "fulfilled" && casesResp.value.ok) {
        const data = await casesResp.value.json();
        setCases(data.cases || []);
        setParameters(data.parameters || {});
        const initial =
          (data.cases || []).find((c: PresetCaseMeta) => c.case_id === "case_3_arctic") ||
          data.cases?.[0];
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
      setApiOnline(false);
    }
    await runInvestigation();
  }, [runInvestigation]);

  useEffect(() => {
    let mounted = true;
    if (mounted) {
      loadInitialCases();
    }
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

  const handleSelectPoint = (
    target: "A" | "B",
    lat: number,
    lon: number,
    resolvedName?: string
  ) => {
    setMode("custom");
    setCaseId(null);
    const coordLabel = `${lat >= 0 ? `${lat.toFixed(2)}°N` : `${Math.abs(lat).toFixed(2)}°S`}, ${
      lon >= 0 ? `${lon.toFixed(2)}°E` : `${Math.abs(lon).toFixed(2)}°W`
    }`;
    const newPt: GeoPoint = {
      name: resolvedName || (target === "A" ? `Region A (${coordLabel})` : `Region B (${coordLabel})`),
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

  const handleChangeWindow = (nextWindow: [number, number]) => {
    setWindowRange(nextWindow);
    if (!pointA) return;
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => {
      if (caseId === "imported_agency_series" && importText.trim()) {
        handleRunImportedSeries(nextWindow);
      } else {
        runInvestigation({ nextWindow });
      }
    }, 220);
  };

  const handleRunImportedSeries = async (customWindow?: [number, number]) => {
    if (!importText.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const win = customWindow ?? windowRange;
      const resp = await fetch(`${API_BASE}/api/import-series`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          raw_text: importText,
          source_hint: importSourceHint,
          region_name: importRegionName,
          lat: pointA?.lat ?? 29.15,
          lon: pointA?.lon ?? -89.25,
          unit: importUnit,
          mk_variant: mkVariant,
          start_year: win[0],
          end_year: win[1],
        }),
      });
      if (!resp.ok) {
        const errJson = await resp.json().catch(() => ({}));
        throw new Error(parseApiErrorMessage(errJson, `Import failed with HTTP ${resp.status}`));
      }
      const data: InvestigateResponse = await resp.json();
      setMode("custom");
      setCaseId("imported_agency_series");
      setPointA(data.request.primary_point);
      setPointB(null);
      setWindowRange([data.request.start_year, data.request.end_year]);
      setResult(data);
      setShowImportModal(false);
      setActiveSection("analysis");
    } catch (err) {
      setError((err as Error).message || "Failed to parse uploaded time series.");
    } finally {
      setLoading(false);
    }
  };

  const [activeSection, setActiveSection] = useState<NavSection>("home");
  const [mobileNavOpen, setMobileNavOpen] = useState<boolean>(false);

  const handleNavigate = (section: NavSection) => {
    setActiveSection(section);
    setMobileNavOpen(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleSelectCaseAndExplore = (selectedCaseId: string, targetSection: NavSection) => {
    const found = cases.find((c) => c.case_id === selectedCaseId);
    if (found) {
      handleSelectCase(found);
    }
    handleNavigate(targetSection);
  };

  const activeMeta = parameters[parameter] ?? result?.response.metadata;
  const activeStep = !pointA ? 2 : result ? 3 : 2;
  const dataStatus = result?.response.data_status;

  const navItems: { id: NavSection; label: string; icon: typeof Home }[] = [
    { id: "home", label: "Home", icon: Home },
    { id: "explore", label: "Explore Data", icon: Compass },
    { id: "analysis", label: "Trend Analysis", icon: LineChart },
    { id: "results", label: "Statistical Results", icon: BarChart3 },
    { id: "about", label: "About", icon: Database },
    { id: "help", label: "Help / Guide", icon: BookOpen },
  ];

  return (
    <div className="min-h-screen bg-[#060b16] text-slate-100">
      {/* Clean Top Navigation Bar */}
      <nav className="app-shell-hide-on-print sticky top-0 z-40 border-b border-slate-800/90 bg-slate-950/90 backdrop-blur-md">
        <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <button
            type="button"
            onClick={() => handleNavigate("home")}
            className="flex items-center gap-2.5 text-left"
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-cyan-500/15 ring-1 ring-cyan-400/40">
              <Satellite className="h-5 w-5 text-cyan-300" />
            </div>
            <div>
              <p className="text-sm font-extrabold tracking-tight text-white sm:text-base">
                TerraShift
              </p>
              <p className="hidden text-[10px] text-slate-400 sm:block">
                Earth System Trend Detective
              </p>
            </div>
          </button>

          {/* Desktop Navigation Links */}
          <div className="hidden items-center gap-1 lg:flex">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeSection === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => handleNavigate(item.id)}
                  className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold transition ${
                    isActive
                      ? "bg-cyan-500/15 text-cyan-300 ring-1 ring-cyan-400/40"
                      : "text-slate-300 hover:bg-slate-900 hover:text-white"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {item.label}
                </button>
              );
            })}
          </div>

          {/* Right Status + Field Dossier + Mobile Menu */}
          <div className="flex items-center gap-2">
            {apiOnline === false && (
              <span className="inline-flex items-center gap-1 rounded-full border border-rose-500/30 bg-rose-500/10 px-2.5 py-1 text-[11px] font-medium text-rose-300">
                <WifiOff className="h-3 w-3" /> Offline
              </span>
            )}
            {dataStatus === "cache" && (
              <span className="hidden items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-medium text-emerald-300 sm:inline-flex">
                <Database className="h-3 w-3" /> Cached
              </span>
            )}
            {dataStatus === "live" && (
              <span className="hidden items-center gap-1 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-1 text-[11px] font-medium text-cyan-300 sm:inline-flex">
                <Wifi className="h-3 w-3" /> Live NASA
              </span>
            )}
            {dataStatus === "synthetic" && (
              <span className="hidden items-center gap-1 rounded-full border border-rose-500/40 bg-rose-500/15 px-2.5 py-1 text-[11px] font-semibold text-rose-200 sm:inline-flex">
                Synthetic Demo
              </span>
            )}

            <button
              type="button"
              disabled={!result}
              onClick={() => setDossierOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-xl bg-slate-100 px-3 py-1.5 text-xs font-bold text-slate-950 shadow transition hover:bg-cyan-200 disabled:opacity-40"
            >
              <FileText className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Field Dossier</span>
            </button>

            <button
              type="button"
              onClick={() => setMobileNavOpen((v) => !v)}
              className="inline-flex items-center justify-center rounded-xl border border-slate-800 bg-slate-900 p-2 text-slate-300 lg:hidden"
              aria-label="Toggle navigation menu"
            >
              {mobileNavOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {/* Mobile Navigation Drawer */}
        {mobileNavOpen && (
          <div className="border-t border-slate-800 bg-slate-950 px-4 py-3 lg:hidden">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {navItems.map((item) => {
                const Icon = item.icon;
                const isActive = activeSection === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => handleNavigate(item.id)}
                    className={`flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold transition ${
                      isActive
                        ? "bg-cyan-500/15 text-cyan-300 ring-1 ring-cyan-400/40"
                        : "bg-slate-900 text-slate-300 hover:text-white"
                    }`}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {item.label}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </nav>

      <div className="app-shell-hide-on-print mx-auto flex max-w-[1440px] flex-col gap-5 px-4 py-5 sm:px-6">
        {dataStatus === "synthetic" && (
          <div className="rounded-xl border border-rose-500/40 bg-rose-950/40 px-4 py-2.5 text-xs text-rose-200">
            <strong>SYNTHETIC DEMO DATA ACTIVE:</strong> The current series was generated for format demonstration and testing only. It does not represent real NASA or partner agency observations.
          </div>
        )}

        {error && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-rose-500/40 bg-rose-950/60 px-4 py-3 text-xs text-rose-200">
            <div>
              <strong>Investigation Error:</strong> {error}
            </div>
            {cases.length === 0 && (
              <button
                type="button"
                onClick={() => loadInitialCases()}
                className="rounded-lg border border-rose-400/50 bg-rose-900/60 px-2.5 py-1 text-xs font-semibold text-rose-100 hover:bg-rose-800"
              >
                Retry Connection
              </button>
            )}
          </div>
        )}

        {activeSection === "home" && (
          <HomePage
            cases={cases}
            activeInvestigation={result}
            onNavigate={handleNavigate}
            onSelectCaseAndExplore={handleSelectCaseAndExplore}
          />
        )}

        {activeSection === "explore" && (
          <>
            {/* Explore Data Control Bar */}
            <header className="flex flex-col gap-4 rounded-2xl border border-slate-800 bg-gradient-to-br from-slate-900 via-slate-900/95 to-slate-950 p-4 shadow-xl">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h1 className="text-lg font-bold tracking-tight text-white sm:text-xl">
                    Explore Earth System Datasets
                  </h1>
                  <p className="text-xs text-slate-400">
                    Choose an environmental variable, click 1–2 regions on the map, and set your time period.
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setShowPartnerHub((s) => !s)}
                    className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-semibold transition ${
                      showPartnerHub
                        ? "border-cyan-400 bg-cyan-500/20 text-cyan-200"
                        : "border-slate-700 bg-slate-900 text-slate-200 hover:bg-slate-800"
                    }`}
                  >
                    <Globe2 className="h-3.5 w-3.5 text-cyan-400" />
                    NASA / CSA / Partner Hub
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      if (!importText) {
                        setImportText(buildSampleGiovanniCsv());
                      }
                      setShowImportModal(true);
                    }}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-indigo-500/40 bg-indigo-500/15 px-3 py-2 text-xs font-semibold text-indigo-200 transition hover:bg-indigo-500/25"
                  >
                    <Upload className="h-3.5 w-3.5" />
                    Import Giovanni / KNMI CSV
                  </button>

                  {result && (
                    <button
                      type="button"
                      onClick={() => handleNavigate("analysis")}
                      className="inline-flex items-center gap-1.5 rounded-xl bg-cyan-500 px-3.5 py-2 text-xs font-bold text-slate-950 transition hover:bg-cyan-400"
                    >
                      View Trend Chart
                      <ArrowRight className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </div>

          {/* 3-Step Detective Progress Strip */}
          <div className="grid grid-cols-1 gap-2 border-t border-slate-800/80 pt-3 sm:grid-cols-3">
            {[
              { step: 1, title: "1. Pick a Mystery", desc: "Load a Case File, Plain-English Question, or Giovanni/KNMI CSV" },
              { step: 2, title: "2. Place Region Markers", desc: "Click Marker A & optional Marker B on the Mapbox/Satellite map" },
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

          {/* Earth Detective Control Bar: 6 Case Files + Plain-English Question Picker */}
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
                      title={`${c.title} (${c.mission_label})`}
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

          {/* Multi-Agency NASA / NOAA / KNMI / CSA Partner Data & Resource Hub */}
          {showPartnerHub && partnerIntel && (
            <div className="space-y-3 rounded-xl border border-cyan-500/30 bg-slate-950/90 p-4 text-xs">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-2.5">
                <div className="flex items-center gap-2">
                  <Globe2 className="h-4 w-4 text-cyan-400" />
                  <span className="font-bold text-white">
                    Multi-Agency Satellite &amp; Partner Telemetry Hub — {pointA?.name} (
                    {partnerIntel.coordinates.lat.toFixed(2)}°, {partnerIntel.coordinates.lon.toFixed(2)}°)
                  </span>
                </div>
                {intelLoading && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-cyan-300">
                    <Loader2 className="h-3 w-3 animate-spin" /> Querying NASA CMR, AppEEARS &amp; CSA GeoMet...
                  </span>
                )}
              </div>

              {/* Live API Telemetry Strip: NASA CMR + AppEEARS + CSA GeoMet */}
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
                  <p className="font-semibold text-cyan-300">
                    NASA CMR Collection Metadata Discovery (SWOT / SeaWiFS / EOS)
                  </p>
                  <div className="mt-1.5 space-y-1.5">
                    {partnerIntel.cmr_collections.slice(0, 3).map((c) => (
                      <div key={c.short_name} className="rounded bg-slate-950/70 p-1.5">
                        <p className="font-mono text-[11px] font-bold text-white">{c.short_name}</p>
                        <p className="text-[11px] text-slate-400 line-clamp-1">{c.title}</p>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
                  <p className="font-semibold text-emerald-300">
                    NASA AppEEARS Catalog Discovery (Manual Export &rarr; Import)
                  </p>
                  <div className="mt-1.5 space-y-1.5">
                    {partnerIntel.appeears_products.slice(0, 3).map((p) => (
                      <div key={p.product_id} className="rounded bg-slate-950/70 p-1.5">
                        <p className="font-mono text-[11px] font-bold text-white">
                          {p.product_id} ({p.platform} · {p.resolution})
                        </p>
                        <p className="text-[11px] text-slate-400 line-clamp-1">{p.description}</p>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
                  <p className="font-semibold text-amber-300">
                    CSA / Geo.ca MSC GeoMet &amp; NOAA CDO Station Discovery
                  </p>
                  <div className="mt-1.5 space-y-1.5">
                    {partnerIntel.csa_geomet_stations.length > 0 ? (
                      partnerIntel.csa_geomet_stations.slice(0, 2).map((st, idx) => (
                        <div key={`${st.station_id}-${idx}`} className="rounded bg-slate-950/70 p-1.5">
                          <p className="font-mono text-[11px] font-bold text-white">
                            {st.station_name} ({st.province})
                          </p>
                          <p className="text-[11px] text-slate-400">{st.sample_metric}</p>
                        </div>
                      ))
                    ) : (
                      <div className="rounded bg-slate-950/70 p-2 text-[11px] text-slate-300">
                        Select <strong>CSA SWOT &amp; RCM Arctic (Case 6)</strong> or click any Canadian basin to query live MSC GeoMet hydrometric gauges.
                      </div>
                    )}
                    <p className="text-[10px] text-slate-400">{partnerIntel.noaa_cdo_status}</p>
                  </div>
                </div>
              </div>

              {/* Coordinate-Parameterized Deep Links across all 3 Agency Categories */}
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {partnerIntel.deep_links.map((link) => (
                  <a
                    key={link.id}
                    href={link.url}
                    target="_blank"
                    rel="noreferrer"
                    className="group flex flex-col justify-between rounded-lg border border-slate-800 bg-slate-900/60 p-2.5 transition hover:border-cyan-500/50 hover:bg-slate-900"
                  >
                    <div>
                      <div className="flex items-center justify-between gap-1">
                        <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-semibold text-cyan-300">
                          {link.agency}
                        </span>
                        <ExternalLink className="h-3 w-3 text-slate-500 group-hover:text-cyan-300" />
                      </div>
                      <p className="mt-1 font-semibold text-slate-100 group-hover:text-cyan-200">
                        {link.title}
                      </p>
                      <p className="mt-0.5 text-[11px] text-slate-400">{link.description}</p>
                    </div>
                  </a>
                ))}
              </div>
            </div>
          )}
        </header>

        {result?.response.fallback_note && (
          <div className="rounded-xl border border-amber-500/40 bg-amber-950/40 px-4 py-2 text-xs text-amber-200">
            {result.response.fallback_note}
          </div>
        )}

        {/* Dual Teleconnection SplitMap (Mapbox + Satellite + Reverse Geocoding) */}
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

        {result && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-3 text-xs">
            <div className="text-slate-300">
              <strong className="text-white">Dataset Ready:</strong>{" "}
              {result.request.primary_point.name} · {result.response.metadata.parameter_name} (
              {result.response.primary_stats.observation_months} months, {windowRange[0]}–{windowRange[1]})
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => handleNavigate("analysis")}
                className="inline-flex items-center gap-1.5 rounded-lg bg-cyan-500 px-3.5 py-2 text-xs font-bold text-slate-950 transition hover:bg-cyan-400"
              >
                <LineChart className="h-3.5 w-3.5" />
                Open Trend Analysis
              </button>
              <button
                type="button"
                onClick={() => handleNavigate("results")}
                className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500/20 px-3.5 py-2 text-xs font-bold text-emerald-200 ring-1 ring-emerald-500/40 transition hover:bg-emerald-500/30"
              >
                <BarChart3 className="h-3.5 w-3.5" />
                Open Statistical Results
              </button>
            </div>
          </div>
        )}
          </>
        )}

        {activeSection === "analysis" && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-3">
              <div>
                <h1 className="text-lg font-bold text-white">Time-Series &amp; Trend Analysis</h1>
                <p className="text-xs text-slate-400">
                  Switch between Raw Monthly Data, Deseasonalized Trend Lab (with linear regression &amp; 95% CI), and Regional Anomaly Comparison.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => handleNavigate("explore")}
                  className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:border-cyan-400"
                >
                  Change Region / Variable
                </button>
                <button
                  type="button"
                  onClick={() => handleNavigate("results")}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3.5 py-1.5 text-xs font-bold text-slate-950 hover:bg-emerald-400"
                >
                  View Statistical Results
                  <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>

            {result && pointA ? (
              <TrendLab
                investigation={result}
                pointA={pointA}
                pointB={pointB}
                windowRange={windowRange}
                onChangeWindow={handleChangeWindow}
                loading={loading}
              />
            ) : (
              <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-8 text-center text-sm text-slate-300">
                Select a dataset or region in{" "}
                <button
                  type="button"
                  onClick={() => handleNavigate("explore")}
                  className="font-bold text-cyan-300 underline"
                >
                  Explore Data
                </button>{" "}
                to visualize its time-series trends.
              </div>
            )}
          </>
        )}

        {activeSection === "results" && (
          result && pointA ? (
            <StatsDashboard
              investigation={result}
              pointA={pointA}
              pointB={pointB}
              mkVariant={mkVariant}
              onToggleMkVariant={(variant) => {
                setMkVariant(variant);
                runInvestigation({ nextMk: variant });
              }}
              onOpenDossier={() => setDossierOpen(true)}
              onGoToCharts={() => handleNavigate("analysis")}
            />
          ) : (
            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-8 text-center text-sm text-slate-300">
              Run an investigation in{" "}
              <button
                type="button"
                onClick={() => handleNavigate("explore")}
                className="font-bold text-cyan-300 underline"
              >
                Explore Data
              </button>{" "}
              to view the Statistical Results Dashboard.
            </div>
          )
        )}

        {activeSection === "about" && <AboutView onNavigate={handleNavigate} />}

        {activeSection === "help" && <HelpGuideView onNavigate={handleNavigate} />}

        {/* Detective Brief Summary Strip */}
        {result && activeSection !== "home" && activeSection !== "results" && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3 text-xs text-slate-300">
            <div className="max-w-4xl">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-semibold text-cyan-200">{result.response.detective_brief.verdict_headline}</p>
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                    result.response.detective_brief.ai_enhanced
                      ? "border border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                      : "border border-slate-700 bg-slate-800 text-slate-300"
                  }`}
                >
                  {result.response.detective_brief.ai_enhanced
                    ? "Gemini AI Grounded"
                    : "NASA Physics Synthesis"}
                </span>
              </div>
              <p className="mt-0.5 text-slate-400">{result.response.detective_brief.physical_mechanism}</p>
              <p className="mt-1 flex items-center gap-1.5 text-[11px] text-slate-500">
                <BookOpen className="h-3.5 w-3.5 text-cyan-400" />
                <span>Reference: {result.response.detective_brief.reference}</span>
              </p>
            </div>
            <button
              type="button"
              onClick={() => setDossierOpen(true)}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-xl border border-cyan-500/40 bg-cyan-500/10 px-3.5 py-2 text-xs font-semibold text-cyan-200 transition hover:bg-cyan-500/20"
            >
              <FileText className="h-3.5 w-3.5" />
              Open Full Field Dossier
            </button>
          </div>
        )}

        {/* Universal Multi-Agency CSV / ASCII / KNMI Importer Modal */}
        {showImportModal && (
          <div className="fixed inset-0 z-[900] flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm">
            <div className="w-full max-w-2xl rounded-2xl border border-slate-700 bg-slate-900 p-5 text-xs shadow-2xl">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div>
                  <h3 className="text-sm font-bold text-white">
                    Import External Space Agency Time-Series (Giovanni · GES DISC · AppEEARS · KNMI · NOAA CDO)
                  </h3>
                  <p className="text-[11px] text-slate-400">
                    Upload or paste monthly CSV, ASCII Data Rods, or KNMI 13-column (.dat) files to run STL decomposition &amp; Mann-Kendall tests.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowImportModal(false)}
                  className="rounded-lg px-2 py-1 text-slate-400 hover:bg-slate-800 hover:text-white"
                >
                  ✕
                </button>
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setImportRegionName("Synthetic Demo: Mississippi Delta Plume (Giovanni Format)");
                    setImportUnit("mg/m³");
                    setImportSourceHint("NASA Giovanni");
                    setImportText(buildSampleGiovanniCsv());
                  }}
                  className="rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-2.5 py-1 font-medium text-cyan-200 hover:bg-cyan-500/20"
                >
                  Load Synthetic Demo CSV (Giovanni Format)
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setImportRegionName("Synthetic Demo: Mackenzie Delta Gauge (KNMI Format)");
                    setImportUnit("m");
                    setImportSourceHint("KNMI Climate Explorer");
                    setImportText(buildSampleKnmiDat());
                  }}
                  className="rounded-lg border border-indigo-500/40 bg-indigo-500/10 px-2.5 py-1 font-medium text-indigo-200 hover:bg-indigo-500/20"
                >
                  Load Synthetic Demo Table (KNMI Format)
                </button>
                <label className="cursor-pointer rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 font-medium text-slate-200 hover:bg-slate-700">
                  Upload Local File (.csv / .dat / .txt)
                  <input
                    type="file"
                    accept=".csv,.dat,.txt,.asc"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (!file) return;
                      setImportRegionName(file.name.replace(/\.[^.]+$/, ""));
                      const reader = new FileReader();
                      reader.onload = () => {
                        setImportText(String(reader.result || ""));
                      };
                      reader.readAsText(file);
                    }}
                  />
                </label>
              </div>

              <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
                <label className="flex flex-col gap-1">
                  <span className="text-[11px] text-slate-400">Region / Station Label</span>
                  <input
                    type="text"
                    value={importRegionName}
                    onChange={(e) => setImportRegionName(e.target.value)}
                    className="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-slate-100"
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-[11px] text-slate-400">Physical Unit</span>
                  <input
                    type="text"
                    value={importUnit}
                    onChange={(e) => setImportUnit(e.target.value)}
                    className="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-slate-100"
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-[11px] text-slate-400">Agency Format</span>
                  <select
                    value={importSourceHint}
                    onChange={(e) => setImportSourceHint(e.target.value)}
                    className="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-slate-100"
                  >
                    <option value="auto">Auto-Detect Format</option>
                    <option value="NASA Giovanni">NASA Giovanni CSV</option>
                    <option value="NASA GES DISC Hydrology">GES DISC Hydrology ASCII/CSV</option>
                    <option value="NASA AppEEARS">NASA AppEEARS CSV</option>
                    <option value="KNMI Climate Explorer">KNMI Climate Explorer (.dat)</option>
                    <option value="NOAA CDO">NOAA Climate Data Online CSV</option>
                  </select>
                </label>
              </div>

              <textarea
                rows={8}
                value={importText}
                onChange={(e) => setImportText(e.target.value)}
                placeholder="Paste Giovanni CSV (YYYY-MM,value) or KNMI 13-column table here..."
                className="mt-3 w-full rounded-xl border border-slate-700 bg-slate-950 p-3 font-mono text-[11px] text-slate-200 outline-none focus:border-cyan-400"
              />

              <div className="mt-3 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowImportModal(false)}
                  className="rounded-lg border border-slate-700 px-3 py-1.5 text-slate-300 hover:bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => handleRunImportedSeries()}
                  className="rounded-lg bg-cyan-500 px-4 py-1.5 font-bold text-slate-950 hover:bg-cyan-400"
                >
                  Decompose &amp; Analyze Series
                </button>
              </div>
            </div>
          </div>
        )}

        {dossierOpen && result && pointA && (
          <DossierModal
            investigation={result}
            pointA={pointA}
            pointB={pointB}
            windowRange={windowRange}
            onClose={() => setDossierOpen(false)}
          />
        )}
      </div>
    </div>
  );
}
