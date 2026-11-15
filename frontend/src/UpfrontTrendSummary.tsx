import {
  CheckCircle2,
  Clock,
  Compass,
  Gauge,
  HelpCircle,
  MapPin,
  MinusCircle,
  ShieldAlert,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import type { GeoPoint, InvestigateResponse } from "./types";
import { synthesizeTrendFinding } from "./trendSynthesis";

interface UpfrontTrendSummaryProps {
  investigation: InvestigateResponse;
  pointA: GeoPoint;
  pointB: GeoPoint | null;
  windowRange: [number, number];
  variant?: "dark" | "light" | "print";
}

export default function UpfrontTrendSummary({
  investigation,
  pointA,
  pointB,
  windowRange,
  variant = "dark",
}: UpfrontTrendSummaryProps) {
  const finding = synthesizeTrendFinding(investigation, pointA, pointB, windowRange);

  const isPrint = variant === "print";
  const isLight = variant === "light" || isPrint;

  // Visual styles depending on theme
  const containerClasses = isLight
    ? finding.isSignificant
      ? finding.direction === "increasing"
        ? "border-emerald-300 bg-emerald-50/70 text-slate-900"
        : "border-cyan-300 bg-cyan-50/70 text-slate-900"
      : "border-amber-300 bg-amber-50/70 text-slate-900"
    : finding.isSignificant
      ? finding.direction === "increasing"
        ? "border-emerald-500/40 bg-gradient-to-br from-emerald-950/40 via-slate-900 to-slate-950 text-slate-100"
        : "border-cyan-500/40 bg-gradient-to-br from-cyan-950/40 via-slate-900 to-slate-950 text-slate-100"
      : "border-amber-500/40 bg-gradient-to-br from-amber-950/40 via-slate-900 to-slate-950 text-slate-100";

  const badgeClasses = isLight
    ? finding.isSignificant
      ? finding.direction === "increasing"
        ? "bg-emerald-700 text-white"
        : "bg-cyan-700 text-white"
      : "bg-amber-700 text-white"
    : finding.isSignificant
      ? finding.direction === "increasing"
        ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/50"
        : "bg-cyan-500/20 text-cyan-300 border border-cyan-500/50"
      : "bg-amber-500/20 text-amber-300 border border-amber-500/50";

  const itemBorder = isLight ? "border-slate-200 bg-white" : "border-slate-800/80 bg-slate-950/60";
  const labelColor = isLight ? "text-slate-600" : "text-slate-400";
  const valueColor = isLight ? "text-slate-950" : "text-white";

  return (
    <section
      className={`rounded-2xl border p-4 sm:p-5 shadow-lg ${containerClasses} print-section print:p-3 print:border-slate-300 print:bg-white`}
      aria-labelledby="trend-summary-title"
    >
      {/* Primary Question Prompt */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-current/15 pb-3">
        <div className="flex items-center gap-2">
          <HelpCircle className={`h-4 w-4 ${isLight ? "text-slate-700" : "text-cyan-400"}`} />
          <span className="text-[11px] font-extrabold uppercase tracking-wider opacity-80">
            Core Environmental Research Question
          </span>
        </div>
        <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-0.5 text-xs font-bold ${badgeClasses}`}>
          {finding.isSignificant ? (
            finding.direction === "increasing" ? (
              <TrendingUp className="h-3.5 w-3.5" />
            ) : (
              <TrendingDown className="h-3.5 w-3.5" />
            )
          ) : (
            <MinusCircle className="h-3.5 w-3.5" />
          )}
          {finding.isSignificant
            ? finding.direction === "increasing"
              ? "Monotonic Increase Confirmed (MK p < 0.05)"
              : "Monotonic Decrease Confirmed (MK p < 0.05)"
            : "No Monotonic Trend Confirmed (MK p ≥ 0.05)"}
        </span>
      </div>

      {/* Immediate Direct Answer */}
      <div className="mt-3">
        <h3 id="trend-summary-title" className="text-sm font-semibold opacity-75">
          Is there a clear indication of a trend in this environmental data?
        </h3>
        <p className={`mt-1 text-lg font-extrabold sm:text-xl ${isLight ? "text-slate-950" : "text-white"} print:text-base`}>
          {finding.plainHeadline}
        </p>
        <p className="mt-1 text-xs leading-relaxed opacity-90">{finding.plainMeaning}</p>
      </div>

      {/* 6 Key Structured Findings (Grid) */}
      <div className="mt-4 grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3 print:grid-cols-2 print:gap-2">
        {/* 1. Overall Finding */}
        <div className={`rounded-xl border p-3 ${itemBorder} print:p-2 print:border-slate-300`}>
          <div className="flex items-center gap-1.5 text-[11px] font-bold">
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
            <span className={labelColor}>1. Overall Finding</span>
          </div>
          <p className={`mt-1 text-xs font-semibold leading-snug ${valueColor}`}>
            {finding.overallFinding}
          </p>
        </div>

        {/* 2. Direction */}
        <div className={`rounded-xl border p-3 ${itemBorder} print:p-2 print:border-slate-300`}>
          <div className="flex items-center gap-1.5 text-[11px] font-bold">
            <Compass className="h-3.5 w-3.5 text-cyan-600 dark:text-cyan-400" />
            <span className={labelColor}>2. Direction of Change</span>
          </div>
          <p className={`mt-1 text-xs font-semibold leading-snug ${valueColor}`}>
            {finding.directionSummary}
          </p>
        </div>

        {/* 3. Magnitude */}
        <div className={`rounded-xl border p-3 ${itemBorder} print:p-2 print:border-slate-300`}>
          <div className="flex items-center gap-1.5 text-[11px] font-bold">
            <Gauge className="h-3.5 w-3.5 text-indigo-600 dark:text-indigo-400" />
            <span className={labelColor}>3. Magnitude of Change</span>
          </div>
          <p className={`mt-1 text-xs font-semibold leading-snug ${valueColor}`}>
            {finding.magnitudeSummary}
          </p>
          <div className="mt-1.5 rounded border border-slate-300/60 dark:border-slate-700/60 bg-slate-100/70 dark:bg-slate-900/70 px-2 py-0.5 font-mono text-[10px] text-slate-700 dark:text-slate-300">
            {finding.decadalSlopeWithCi}
          </div>
        </div>

        {/* 4. Confidence */}
        <div className={`rounded-xl border p-3 ${itemBorder} print:p-2 print:border-slate-300`}>
          <div className="flex items-center gap-1.5 text-[11px] font-bold">
            {finding.isSignificant ? (
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
            ) : (
              <ShieldAlert className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
            )}
            <span className={labelColor}>4. Statistical Confidence</span>
          </div>
          <p className={`mt-1 text-xs font-semibold leading-snug ${valueColor}`}>
            {finding.confidenceSummary}
          </p>
        </div>

        {/* 5. Time Period */}
        <div className={`rounded-xl border p-3 ${itemBorder} print:p-2 print:border-slate-300`}>
          <div className="flex items-center gap-1.5 text-[11px] font-bold">
            <Clock className="h-3.5 w-3.5 text-purple-600 dark:text-purple-400" />
            <span className={labelColor}>5. Analyzed Time Period</span>
          </div>
          <p className={`mt-1 text-xs font-semibold leading-snug ${valueColor}`}>
            {finding.timePeriodSummary}
          </p>
        </div>

        {/* 6. Regional Pattern */}
        <div className={`rounded-xl border p-3 ${itemBorder} print:p-2 print:border-slate-300`}>
          <div className="flex items-center gap-1.5 text-[11px] font-bold">
            <MapPin className="h-3.5 w-3.5 text-rose-600 dark:text-rose-400" />
            <span className={labelColor}>6. Regional Association</span>
          </div>
          <p className={`mt-1 text-xs font-semibold leading-snug ${valueColor}`}>
            {finding.regionalPatternSummary}
          </p>
        </div>
      </div>
    </section>
  );
}
