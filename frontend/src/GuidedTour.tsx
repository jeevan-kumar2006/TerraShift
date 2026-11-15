import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, Pause, Play, Sparkles, X } from "lucide-react";
import type { InvestigateResponse, TrendMapResponse } from "./types";

export interface GuidedTourConfig {
  id: "thar-greening" | "delhi-air" | "northeast-monsoon";
  title: string;
  subtitle: string;
  parameter: string;
  regionId: string;
  regionLabel: string;
  lat: number;
  lon: number;
  startYear: number;
  endYear: number;
}

export const INDIA_GUIDED_TOURS: GuidedTourConfig[] = [
  {
    id: "thar-greening",
    title: "Thar Desert & Canal-Irrigated Greening",
    subtitle: "Does satellite NDVI show vegetation greening in western Rajasthan?",
    parameter: "MOD13C2",
    regionId: "state_rajasthan",
    regionLabel: "Rajasthan",
    lat: 26.9,
    lon: 70.9,
    startYear: 2001,
    endYear: 2025,
  },
  {
    id: "delhi-air",
    title: "Delhi NCR Tropospheric NO2 Trend",
    subtitle: "How has satellite-observed urban NO2 changed over the National Capital Territory?",
    parameter: "OMNO2d",
    regionId: "state_delhi",
    regionLabel: "Delhi",
    lat: 28.61,
    lon: 77.21,
    startYear: 2005,
    endYear: 2025,
  },
  {
    id: "northeast-monsoon",
    title: "Northeast India Monsoon Rainfall Shift",
    subtitle: "Is GPM IMERG precipitation changing across Assam & the Brahmaputra valley?",
    parameter: "GPM_3IMERGM",
    regionId: "state_assam",
    regionLabel: "Assam",
    lat: 26.2,
    lon: 92.9,
    startYear: 2001,
    endYear: 2025,
  },
];

interface GuidedTourProps {
  activeTour: GuidedTourConfig | null;
  investigation: InvestigateResponse | null;
  trendMap: TrendMapResponse | null;
  loading: boolean;
  error: string | null;
  onStartTour: (tour: GuidedTourConfig) => void;
  onClose: () => void;
  onJumpToView: (view: "ask" | "map" | "results" | "report") => void;
}

export default function GuidedTour({
  activeTour,
  investigation,
  trendMap,
  loading,
  error,
  onStartTour,
  onClose,
  onJumpToView,
}: GuidedTourProps) {
  const [stepIndex, setStepIndex] = useState<number>(0);
  const [autoPlay, setAutoPlay] = useState<boolean>(false);

  const ps = investigation?.response.primary_stats ?? null;
  const meta = investigation?.response.metadata ?? null;
  const brief = investigation?.response.detective_brief ?? null;

  const steps = activeTour
    ? [
        {
          title: `1. Question & Region: ${activeTour.regionLabel}`,
          view: "ask" as const,
          body: `${activeTour.subtitle} TerraShift queries ${activeTour.parameter} over ${activeTour.startYear}–${activeTour.endYear} for ${activeTour.regionLabel} (${activeTour.lat.toFixed(2)}°N, ${activeTour.lon.toFixed(2)}°E).`,
        },
        {
          title: "2. Spatial Context & FDR Choropleth",
          view: "map" as const,
          body: trendMap
            ? `Across ${trendMap.summary.computed_regions} Indian regions, ${trendMap.summary.significant_fdr_count} pass Benjamini-Hochberg FDR (q < ${trendMap.summary.fdr_alpha}). Legend scale is computed from the 95th percentile (±${trendMap.legend_range.symmetric_abs_p95.toFixed(4)} ${trendMap.unit}/yr).`
            : `Inspect ${activeTour.regionLabel} on the India map with free cartographic tiles and state/district polygon boundaries.`,
        },
        {
          title: "3. Live Statistical Verdict",
          view: "results" as const,
          body: loading
            ? "Computing STL seasonal decomposition, Sen's slope, and Mann-Kendall significance from live data..."
            : error
              ? `Live retrieval returned an error: ${error}`
              : ps && meta && brief
                ? `${brief.verdict_headline} Estimated Sen's slope: ${ps.sens_slope_per_decade >= 0 ? "+" : ""}${ps.sens_slope_per_decade} ${meta.unit}/decade (Mann-Kendall p = ${ps.p_value < 0.0001 ? "< 0.0001" : ps.p_value.toFixed(4)}, ${ps.is_significant ? "statistically significant" : `not yet significant; ~${ps.years_to_significance} more yrs needed`}).`
                : "Run the tour investigation to populate live statistical metrics.",
        },
        {
          title: "4. Scientific Report & Export",
          view: "report" as const,
          body: brief
            ? `${brief.physical_mechanism} You can export the validated time series as CSV or JSON from the Report view.`
            : "Review the grounded physical brief and export CSV/JSON results.",
        },
      ]
    : [];

  useEffect(() => {
    if (!activeTour) {
      setStepIndex(0);
      setAutoPlay(false);
    }
  }, [activeTour]);

  useEffect(() => {
    if (!activeTour || !autoPlay || steps.length === 0) return;
    const timer = window.setInterval(() => {
      setStepIndex((prev) => {
        const next = (prev + 1) % steps.length;
        onJumpToView(steps[next].view);
        return next;
      });
    }, 5500);
    return () => window.clearInterval(timer);
  }, [activeTour, autoPlay, steps, onJumpToView]);

  if (!activeTour) return null;

  const current = steps[stepIndex] || steps[0];

  return (
    <aside
      aria-label="Guided Demo Tour"
      className="fixed bottom-4 right-4 z-[900] w-[calc(100vw-2rem)] max-w-md rounded-2xl border border-cyan-500/50 bg-slate-950/95 p-4 text-xs text-slate-200 shadow-2xl backdrop-blur-xl"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="flex items-center gap-1.5 font-bold text-cyan-300">
            <Sparkles className="h-3.5 w-3.5" />
            Guided Tour · {activeTour.title}
          </p>
          <p className="mt-0.5 text-slate-400">
            Step {stepIndex + 1} of {steps.length}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Skip guided tour"
          className="rounded-lg border border-slate-700 bg-slate-900 p-1 text-slate-300 hover:bg-slate-800"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Tour Switcher */}
      <div className="mt-2.5 flex flex-wrap gap-1.5">
        {INDIA_GUIDED_TOURS.map((tour) => (
          <button
            key={tour.id}
            type="button"
            onClick={() => {
              setStepIndex(0);
              onStartTour(tour);
            }}
            className={`rounded-lg px-2 py-1 text-xs font-semibold transition ${
              tour.id === activeTour.id
                ? "bg-cyan-500 text-slate-950"
                : "border border-slate-700 bg-slate-900 text-slate-300 hover:bg-slate-800"
            }`}
          >
            {tour.regionLabel}
          </button>
        ))}
      </div>

      {/* Step Content */}
      <div className="mt-3 rounded-xl border border-slate-800 bg-slate-900/80 p-3">
        <p className="font-bold text-white">{current.title}</p>
        <p className="mt-1 leading-relaxed text-slate-300">{current.body}</p>
      </div>

      {/* Navigation Controls */}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            disabled={stepIndex === 0}
            onClick={() => {
              const prev = Math.max(0, stepIndex - 1);
              setStepIndex(prev);
              onJumpToView(steps[prev].view);
            }}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 font-semibold text-slate-200 disabled:opacity-40"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back
          </button>
          <button
            type="button"
            onClick={() => {
              if (stepIndex + 1 >= steps.length) {
                onClose();
              } else {
                const next = stepIndex + 1;
                setStepIndex(next);
                onJumpToView(steps[next].view);
              }
            }}
            className="inline-flex items-center gap-1 rounded-lg bg-cyan-500 px-3 py-1.5 font-bold text-slate-950 hover:bg-cyan-400"
          >
            {stepIndex + 1 >= steps.length ? "Finish" : "Next"}
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setAutoPlay((p) => !p)}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 font-semibold text-slate-200 hover:bg-slate-800"
          >
            {autoPlay ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
            {autoPlay ? "Pause" : "Auto-play"}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-2 py-1.5 font-semibold text-slate-400 hover:text-white"
          >
            Skip
          </button>
        </div>
      </div>
    </aside>
  );
}
