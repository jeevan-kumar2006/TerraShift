import {
  ArrowRight,
  BarChart3,
  BookOpen,
  Compass,
  Database,
  Globe2,
  LineChart,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import type { InvestigateResponse, PresetCaseMeta } from "./types";

export type NavSection = "home" | "explore" | "analysis" | "results" | "about" | "help";

interface HomePageProps {
  cases: PresetCaseMeta[];
  activeInvestigation: InvestigateResponse | null;
  onNavigate: (section: NavSection) => void;
  onSelectCaseAndExplore: (caseId: string, targetSection: NavSection) => void;
}

export default function HomePage({
  cases,
  activeInvestigation,
  onNavigate,
  onSelectCaseAndExplore,
}: HomePageProps) {
  const featuredCases = cases.slice(0, 4);
  const activeStats = activeInvestigation?.response.primary_stats;
  const activeMeta = activeInvestigation?.response.metadata;

  return (
    <div className="space-y-8">
      {/* Hero Section */}
      <section className="relative overflow-hidden rounded-3xl border border-slate-800/90 bg-gradient-to-br from-slate-900 via-[#0a1628] to-slate-950 p-6 shadow-2xl sm:p-10">
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-cyan-500/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 left-1/3 h-72 w-72 rounded-full bg-emerald-500/10 blur-3xl" />

        <div className="relative grid grid-cols-1 items-center gap-8 lg:grid-cols-12">
          <div className="space-y-5 lg:col-span-7">
            <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3.5 py-1 text-xs font-semibold text-cyan-300">
              <Sparkles className="h-3.5 w-3.5" />
              NASA Space Apps Challenge · Earth Observation &amp; Trend Science
            </div>

            <h1 className="text-3xl font-extrabold tracking-tight text-white sm:text-5xl">
              Be An Earth System Trend Detective!
            </h1>

            <p className="max-w-2xl text-base leading-relaxed text-slate-300 sm:text-lg">
              Explore real NASA climate and water datasets from anywhere on Earth. Spot hidden
              multi-decade shifts beneath noisy seasonal swings, test whether changes are
              statistically real, and read clear, plain-language explanations.
            </p>

            <div className="flex flex-wrap items-center gap-3 pt-1">
              <button
                type="button"
                onClick={() => onNavigate("explore")}
                className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-cyan-400 to-emerald-400 px-6 py-3 text-sm font-bold text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:brightness-110"
              >
                Start Exploring
                <ArrowRight className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => onNavigate("analysis")}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900/80 px-5 py-3 text-sm font-semibold text-slate-100 transition hover:border-cyan-400/60 hover:bg-slate-800"
              >
                <LineChart className="h-4 w-4 text-cyan-400" />
                View Live Trend Chart
              </button>
              <button
                type="button"
                onClick={() => onNavigate("help")}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-800 bg-transparent px-4 py-3 text-sm font-medium text-slate-300 transition hover:text-white"
              >
                <BookOpen className="h-4 w-4 text-emerald-400" />
                Beginner&apos;s Guide
              </button>
            </div>
          </div>

          {/* Engaging Live Earth Snapshot Card */}
          <div className="lg:col-span-5">
            <div className="rounded-2xl border border-slate-700/80 bg-slate-950/85 p-5 shadow-xl">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div className="flex items-center gap-2">
                  <Globe2 className="h-5 w-5 text-cyan-400" />
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
                    Active Earth Investigation
                  </span>
                </div>
                <span className="rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-300">
                  NASA POWER
                </span>
              </div>

              {activeInvestigation && activeStats && activeMeta ? (
                <div className="mt-4 space-y-3">
                  <div>
                    <p className="text-xs text-slate-400">Region &amp; Variable</p>
                    <p className="text-base font-bold text-white">
                      {activeInvestigation.request.primary_point.name} — {activeMeta.parameter_name}
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-3 rounded-xl border border-slate-800 bg-slate-900/70 p-3">
                    <div>
                      <p className="text-[11px] text-slate-400">Rate of Change</p>
                      <p className="font-mono text-lg font-bold text-cyan-300">
                        {activeStats.sens_slope_per_decade >= 0 ? "+" : ""}
                        {activeStats.sens_slope_per_decade} {activeMeta.unit}/dec
                      </p>
                    </div>
                    <div>
                      <p className="text-[11px] text-slate-400">Statistical Verdict</p>
                      <p
                        className={`text-sm font-bold ${
                          activeStats.is_significant ? "text-emerald-400" : "text-amber-300"
                        }`}
                      >
                        {activeStats.is_significant
                          ? activeStats.sens_slope_per_year >= 0
                            ? "Significant Increase"
                            : "Significant Decrease"
                          : "Not Significant (p >= 0.05)"}
                      </p>
                    </div>
                  </div>

                  <p className="text-xs leading-relaxed text-slate-300">
                    {activeInvestigation.response.detective_brief.verdict_headline}
                  </p>

                  <div className="flex gap-2 pt-1">
                    <button
                      type="button"
                      onClick={() => onNavigate("analysis")}
                      className="flex-1 rounded-lg bg-cyan-500/15 px-3 py-2 text-xs font-semibold text-cyan-200 transition hover:bg-cyan-500/25"
                    >
                      Inspect Chart
                    </button>
                    <button
                      type="button"
                      onClick={() => onNavigate("results")}
                      className="flex-1 rounded-lg bg-emerald-500/15 px-3 py-2 text-xs font-semibold text-emerald-200 transition hover:bg-emerald-500/25"
                    >
                      Statistical Results
                    </button>
                  </div>
                </div>
              ) : (
                <div className="mt-4 space-y-2 text-xs text-slate-400">
                  <p>Loading featured NASA Earth observation investigation...</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* How the Platform Works (4 Simple Steps) */}
      <section className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-xl font-bold text-white">How It Works</h2>
            <p className="text-sm text-slate-400">
              No statistics degree required — follow four clear steps from raw data to evidence-based conclusions.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-cyan-500/20 font-mono text-sm font-bold text-cyan-300">
              1
            </span>
            <h3 className="mt-3 text-sm font-bold text-white">Pick a Region &amp; Variable</h3>
            <p className="mt-1.5 text-xs leading-relaxed text-slate-400">
              Choose temperature, rainfall, or soil moisture, click any spot on Earth, and select a multi-year window.
            </p>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-cyan-500/20 font-mono text-sm font-bold text-cyan-300">
              2
            </span>
            <h3 className="mt-3 text-sm font-bold text-white">Separate Seasons from Trends</h3>
            <p className="mt-1.5 text-xs leading-relaxed text-slate-400">
              Winter-to-summer swings can hide slow climate shifts. We strip repeating seasonal cycles to reveal anomalies.
            </p>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/20 font-mono text-sm font-bold text-emerald-300">
              3
            </span>
            <h3 className="mt-3 text-sm font-bold text-white">Run Real Statistical Tests</h3>
            <p className="mt-1.5 text-xs leading-relaxed text-slate-400">
              Compute Linear Regression, Student&apos;s t-test, Mann-Kendall, Sen&apos;s Slope, and 95% Confidence Intervals.
            </p>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/20 font-mono text-sm font-bold text-emerald-300">
              4
            </span>
            <h3 className="mt-3 text-sm font-bold text-white">Interpret with Confidence</h3>
            <p className="mt-1.5 text-xs leading-relaxed text-slate-400">
              Read plain-language explanations of what each number means, including uncertainty and dataset limitations.
            </p>
          </div>
        </div>
      </section>

      {/* Featured Case Studies */}
      {featuredCases.length > 0 && (
        <section className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-xl font-bold text-white">Ready-to-Explore Earth Mysteries</h2>
              <p className="text-sm text-slate-400">
                Click any real-world case study to jump straight into its time-series chart and statistical results.
              </p>
            </div>
            <button
              type="button"
              onClick={() => onNavigate("explore")}
              className="text-xs font-semibold text-cyan-300 hover:underline"
            >
              Or pick your own coordinates &rarr;
            </button>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {featuredCases.map((c) => (
              <div
                key={c.case_id}
                className="flex flex-col justify-between rounded-2xl border border-slate-800 bg-slate-900/70 p-5 transition hover:border-cyan-500/50"
              >
                <div className="space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="rounded-full bg-cyan-500/15 px-2.5 py-0.5 text-[11px] font-semibold text-cyan-300">
                      {c.parameter_name} ({c.unit})
                    </span>
                    <span className="text-[11px] text-slate-400">
                      {c.default_window[0]}–{c.default_window[1]}
                    </span>
                  </div>
                  <h3 className="text-base font-bold text-white">{c.title}</h3>
                  <p className="text-xs leading-relaxed text-slate-400">{c.mechanism_teaser}</p>
                </div>

                <div className="mt-4 flex flex-wrap gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => onSelectCaseAndExplore(c.case_id, "analysis")}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-cyan-500 px-3 py-1.5 text-xs font-bold text-slate-950 transition hover:bg-cyan-400"
                  >
                    <LineChart className="h-3.5 w-3.5" />
                    Visualize Trend
                  </button>
                  <button
                    type="button"
                    onClick={() => onSelectCaseAndExplore(c.case_id, "results")}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs font-semibold text-slate-200 transition hover:border-emerald-400/60"
                  >
                    <BarChart3 className="h-3.5 w-3.5 text-emerald-400" />
                    Statistical Results
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Quick Access to Core Platform Sections */}
      <section className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <button
          type="button"
          onClick={() => onNavigate("explore")}
          className="flex items-start gap-3 rounded-2xl border border-slate-800 bg-slate-900/50 p-5 text-left transition hover:border-cyan-500/50 hover:bg-slate-900"
        >
          <Compass className="mt-0.5 h-6 w-6 shrink-0 text-cyan-400" />
          <div>
            <p className="text-sm font-bold text-white">Explore Data</p>
            <p className="mt-1 text-xs text-slate-400">
              Select variables, map coordinates, time ranges, or import NASA Giovanni / KNMI CSVs.
            </p>
          </div>
        </button>

        <button
          type="button"
          onClick={() => onNavigate("results")}
          className="flex items-start gap-3 rounded-2xl border border-slate-800 bg-slate-900/50 p-5 text-left transition hover:border-emerald-500/50 hover:bg-slate-900"
        >
          <ShieldCheck className="mt-0.5 h-6 w-6 shrink-0 text-emerald-400" />
          <div>
            <p className="text-sm font-bold text-white">Statistical Results</p>
            <p className="mt-1 text-xs text-slate-400">
              Inspect Linear Regression, Student&apos;s t-test, Mann-Kendall, Sen&apos;s Slope, and 95% CIs.
            </p>
          </div>
        </button>

        <button
          type="button"
          onClick={() => onNavigate("about")}
          className="flex items-start gap-3 rounded-2xl border border-slate-800 bg-slate-900/50 p-5 text-left transition hover:border-indigo-500/50 hover:bg-slate-900"
        >
          <Database className="mt-0.5 h-6 w-6 shrink-0 text-indigo-400" />
          <div>
            <p className="text-sm font-bold text-white">Scientific Rigor &amp; Sources</p>
            <p className="mt-1 text-xs text-slate-400">
              Learn about NASA MERRA-2, satellite metadata, autocorrelation checks, and limitations.
            </p>
          </div>
        </button>
      </section>
    </div>
  );
}
