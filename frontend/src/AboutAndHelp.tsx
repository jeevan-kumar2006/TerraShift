import { ArrowRight, BookOpen, Compass, Database, HelpCircle, ShieldCheck } from "lucide-react";
import type { NavSection } from "./HomePage";

interface AboutViewProps {
  onNavigate: (section: NavSection) => void;
}

export function AboutView({ onNavigate }: AboutViewProps) {
  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-slate-800 bg-slate-900/75 p-6 shadow-xl">
        <div className="flex items-center gap-2 text-cyan-300">
          <Database className="h-5 w-5" />
          <span className="text-xs font-bold uppercase tracking-wider">About TerraShift</span>
        </div>
        <h2 className="mt-2 text-2xl font-extrabold text-white">
          India Earth System Trend Detective
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-slate-300">
          TerraShift was built for the NASA Space Apps Challenge with an exclusive geographical focus
          on India (6.0°N–37.5°N, 68.0°E–97.5°E). It makes multi-decade Earth observation time-series
          analysis accessible across India&apos;s physiographic regions—from the Himalayas and
          Indo-Gangetic Plains to the Thar Desert, Western Ghats, and coastal deltas—using transparent,
          peer-reviewed statistical methods.
        </p>

        <div className="mt-5 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => onNavigate("explore")}
            className="inline-flex items-center gap-1.5 rounded-xl bg-cyan-500 px-4 py-2 text-xs font-bold text-slate-950 transition hover:bg-cyan-400"
          >
            Explore Data Now
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() => onNavigate("help")}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-950 px-4 py-2 text-xs font-semibold text-slate-200 transition hover:border-cyan-400"
          >
            Read Beginner&apos;s Guide
          </button>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
          <h3 className="text-base font-bold text-white">Data Sources &amp; Space Agency Integrations</h3>
          <ul className="mt-3 space-y-2.5 text-xs leading-relaxed text-slate-300">
            <li>
              <strong className="text-cyan-300">NASA POWER (MERRA-2 Reanalysis &amp; Model Hydrology):</strong>{" "}
              Live monthly records (1981–present) on a 0.5° × 0.625° global grid for 2-meter temperature
              (<code className="text-cyan-200">T2M</code>), bias-corrected precipitation (
              <code className="text-cyan-200">PRECTOTCORR</code>), root-zone soil wetness (
              <code className="text-cyan-200">GWETROOT</code>), and profile soil moisture (
              <code className="text-cyan-200">GWETPROF</code>).
            </li>
            <li>
              <strong className="text-cyan-300">NASA CMR &amp; AppEEARS Discovery:</strong> Live collection
              and product catalog discovery for MODIS, GPM, SMAP, GRACE-FO, AIRS, Landsat, and ECOSTRESS over India.
            </li>
            <li>
              <strong className="text-emerald-300">IMD &amp; ISRO / MOSDAC Climatological Context:</strong>{" "}
              Indian Meteorological Department seasonal framing (DJF, MAM, JJAS, ON) and Indian
              states/districts/physiographic regions alongside NASA satellite &amp; MERRA-2 reanalysis records.
            </li>
            <li>
              <strong className="text-indigo-300">NASA Giovanni, GES DISC &amp; AppEEARS:</strong>{" "}
              Direct CSV / ASCII time-series importer for analyzing exported NASA Earth observation records.
            </li>
          </ul>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-emerald-400" />
            <h3 className="text-base font-bold text-white">Scientific Guardrails &amp; Limitations</h3>
          </div>
          <ul className="mt-3 space-y-2.5 text-xs leading-relaxed text-slate-300">
            <li>
              <strong>No Fabricated Data:</strong> Every calculation uses real retrieved, cached, or user-imported
              observations. Synthetic demo files are clearly labeled and never presented as NASA observations.
            </li>
            <li>
              <strong>Gap &amp; Outlier Integrity:</strong> Missing months are tracked on a complete monthly calendar.
              Gaps longer than 3 consecutive months are rejected rather than invented; statistical outliers are flagged
              without automatic deletion.
            </li>
            <li>
              <strong>Honest Uncertainty:</strong> A p-value &ge; 0.05 means insufficient evidence to reject natural
              variability — it does not prove zero physical change. Cross-correlation never proves causation.
            </li>
            <li>
              <strong>AI Grounding Boundary:</strong> Gemini explanations strictly interpret computed statistics and
              never alter or invent numbers.
            </li>
          </ul>
        </div>
      </section>
    </div>
  );
}

export function HelpGuideView({ onNavigate }: AboutViewProps) {
  const steps = [
    { n: "1", title: "Discover", desc: "Learn what Earth System Trend Detection means on the Home page." },
    { n: "2", title: "Explore", desc: "Open Explore Data to pick a variable, region on the map, and time window." },
    { n: "3", title: "Visualize", desc: "Switch between Raw Monthly Data and Deseasonalized Trend Lab to see seasonal swings vs. long-term anomalies." },
    { n: "4", title: "Analyze", desc: "Inspect the linear regression line and rate of change in real physical units." },
    { n: "5", title: "Test", desc: "Check Student's t-test and Mann-Kendall (including Hamed-Rao for autocorrelated data) in Statistical Results." },
    { n: "6", title: "Estimate", desc: "Compare Sen's robust slope against OLS and inspect the 95% confidence interval." },
    { n: "7", title: "Interpret", desc: "Expand any beginner guide card to understand what each number means." },
    { n: "8", title: "Conclude", desc: "Export a printable PDF Field Dossier or JSON report with full provenance and limitations." },
  ];

  const glossary = [
    {
      term: "Seasonality & STL Decomposition",
      def: "Weather repeats every year (warmer summers, colder winters). STL separates that repeating annual cycle from the data so slow, multi-decade trends become visible.",
    },
    {
      term: "p-value (Threshold 0.05)",
      def: "The probability of seeing a trend at least this strong if there were actually no real long-term change. Values below 0.05 are treated as statistically significant.",
    },
    {
      term: "Mann-Kendall Test (S, tau, Z)",
      def: "A rank-based test that checks whether values consistently rise or fall over time without being thrown off by extreme weather spikes.",
    },
    {
      term: "Sen's Slope",
      def: "The median rate of change across all pairs of months — a robust backup to standard linear regression when extreme years occur.",
    },
    {
      term: "95% Confidence Interval (CI)",
      def: "A range of plausible values for the true trend rate. Narrower intervals mean higher precision.",
    },
    {
      term: "Autocorrelation",
      def: "When one month's weather resembles the next (e.g., multi-year El Niño or drought). Hamed-Rao Modified MK adjusts for this so p-values stay honest.",
    },
  ];

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-slate-800 bg-slate-900/75 p-6 shadow-xl">
        <div className="flex items-center gap-2 text-emerald-300">
          <BookOpen className="h-5 w-5" />
          <span className="text-xs font-bold uppercase tracking-wider">Help &amp; Beginner&apos;s Guide</span>
        </div>
        <h2 className="mt-2 text-2xl font-extrabold text-white">Your 8-Step Trend Detective Journey</h2>
        <p className="mt-2 text-sm text-slate-300">
          Follow these eight steps to go from raw environmental measurements to a scientifically valid conclusion.
        </p>

        <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map((s) => (
            <div key={s.n} className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
              <div className="flex items-center gap-2">
                <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-cyan-500/20 font-mono text-xs font-bold text-cyan-300">
                  {s.n}
                </span>
                <h3 className="text-sm font-bold text-white">{s.title}</h3>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-slate-400">{s.desc}</p>
            </div>
          ))}
        </div>

        <div className="mt-5">
          <button
            type="button"
            onClick={() => onNavigate("explore")}
            className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-cyan-400 to-emerald-400 px-5 py-2.5 text-xs font-bold text-slate-950 transition hover:brightness-110"
          >
            <Compass className="h-4 w-4" />
            Start Step 2: Explore Data
          </button>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/75 p-6 shadow-xl">
        <div className="flex items-center gap-2 text-cyan-300">
          <HelpCircle className="h-5 w-5" />
          <h3 className="text-lg font-bold text-white">Plain-Language Statistical Glossary</h3>
        </div>
        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          {glossary.map((g) => (
            <div key={g.term} className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
              <p className="text-sm font-bold text-cyan-200">{g.term}</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-300">{g.def}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
