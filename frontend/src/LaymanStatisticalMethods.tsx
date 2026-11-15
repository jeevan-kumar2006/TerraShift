import { useState } from "react";
import { BookOpen, ChevronDown, ChevronUp } from "lucide-react";
import type { SeriesStats } from "./types";
import { buildLaymanMethodsTable } from "./trendSynthesis";

interface LaymanStatisticalMethodsProps {
  stats: SeriesStats;
  unit: string;
  variant?: "dark" | "light" | "print";
}

export default function LaymanStatisticalMethods({
  stats,
  unit,
  variant = "dark",
}: LaymanStatisticalMethodsProps) {
  const [showTechnicalDetails, setShowTechnicalDetails] = useState<boolean>(true);
  const rows = buildLaymanMethodsTable(stats, unit);

  const isLight = variant === "light" || variant === "print";

  const tableBorder = isLight ? "border-slate-300" : "border-slate-800";
  const headerBg = isLight ? "bg-slate-100 text-slate-900" : "bg-slate-950 text-slate-200";
  const rowEven = isLight ? "bg-white" : "bg-slate-900/60";
  const rowOdd = isLight ? "bg-slate-50" : "bg-slate-950/40";
  const textPrimary = isLight ? "text-slate-950" : "text-white";
  const textMuted = isLight ? "text-slate-600" : "text-slate-300";

  return (
    <div className={`space-y-3 rounded-2xl border ${tableBorder} ${isLight ? "bg-white p-4" : "bg-slate-900/70 p-5"} print:border-slate-300 print:p-2 print-section`}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-current/15 pb-2.5">
        <div className="flex items-center gap-2">
          <BookOpen className={`h-4 w-4 ${isLight ? "text-slate-700" : "text-cyan-400"}`} />
          <h4 className={`text-sm font-bold ${textPrimary}`}>
            Statistical Methods in Layman&apos;s Terms
          </h4>
        </div>

        <button
          type="button"
          onClick={() => setShowTechnicalDetails((v) => !v)}
          className={`no-print inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-semibold transition ${
            isLight
              ? "bg-slate-200 text-slate-800 hover:bg-slate-300"
              : "bg-slate-800 text-slate-200 hover:bg-slate-700"
          }`}
        >
          {showTechnicalDetails ? (
            <>
              Hide Technical Details <ChevronUp className="h-3 w-3" />
            </>
          ) : (
            <>
              Show Technical Calculations <ChevronDown className="h-3 w-3" />
            </>
          )}
        </button>
      </div>

      <p className={`text-xs ${textMuted}`}>
        Our application uses peer-reviewed statistical tests to evaluate whether changes are genuine. Below is what each test measures in simple terms alongside its actual calculated mathematical result.
      </p>

      <div className="overflow-x-auto print:overflow-visible">
        <table className={`w-full text-left text-xs ${tableBorder} border-collapse`}>
          <thead>
            <tr className={`border-b ${tableBorder} ${headerBg} font-bold text-[11px] uppercase tracking-wider`}>
              <th className="p-2.5 w-[20%]">Statistical Method</th>
              <th className="p-2.5 w-[35%]">Simple Explanation</th>
              {showTechnicalDetails && (
                <>
                  <th className="p-2.5 w-[20%] font-mono">Calculated Value</th>
                  <th className="p-2.5 w-[25%]">Scientific Interpretation</th>
                </>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-current/10">
            {rows.map((row, idx) => (
              <tr key={row.concept} className={idx % 2 === 0 ? rowEven : rowOdd}>
                <td className="p-2.5 align-top font-bold">
                  <div className={textPrimary}>{row.concept}</div>
                  <div className="text-[10px] text-slate-500 font-normal">{row.scientificMetric}</div>
                </td>
                <td className={`p-2.5 align-top leading-relaxed ${textMuted}`}>
                  {row.simpleExplanation}
                </td>
                {showTechnicalDetails && (
                  <>
                    <td className="p-2.5 align-top font-mono text-[11px] font-bold text-cyan-600 dark:text-cyan-300 print:text-slate-900">
                      {row.calculatedValue}
                    </td>
                    <td className={`p-2.5 align-top text-[11px] leading-relaxed ${textMuted}`}>
                      {row.scientificInterpretation}
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
