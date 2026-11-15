import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  Download,
  ExternalLink,
  FileCheck2,
  FolderArchive,
  Globe2,
  KeyRound,
  Layers,
  Loader2,
  MapPin,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import type {
  AcquisitionAuthStatus,
  AcquisitionCatalogEntry,
  AcquisitionDomain,
  AcquisitionDownloadResponse,
  AcquisitionGranule,
  AcquisitionManifestData,
  AcquisitionMatrixRow,
  AcquisitionRegion,
  AcquisitionVariableSpec,
} from "./types";

interface DataAcquisitionViewProps {
  apiBase: string;
  onAnalyzeDataset?: (opts: { variable: string; regionId: string; startYear?: number; endYear?: number }) => void;
}

const DOMAIN_LABELS: { id: "all" | AcquisitionDomain; label: string }[] = [
  { id: "all", label: "All Domains (19 Variables)" },
  { id: "atmospheric", label: "Atmospheric Composition" },
  { id: "climate", label: "Climate & Meteorological" },
  { id: "hydrology", label: "Hydrology & Water Cycle" },
  { id: "vegetation", label: "Vegetation & Land Surface" },
];

export default function DataAcquisitionView({ apiBase, onAnalyzeDataset }: DataAcquisitionViewProps) {
  const [domainFilter, setDomainFilter] = useState<"all" | AcquisitionDomain>("all");
  const [variables, setVariables] = useState<AcquisitionVariableSpec[]>([]);
  const [datasets, setDatasets] = useState<AcquisitionCatalogEntry[]>([]);
  const [matrix, setMatrix] = useState<AcquisitionMatrixRow[]>([]);
  const [authStatus, setAuthStatus] = useState<AcquisitionAuthStatus | null>(null);
  const [regions, setRegions] = useState<AcquisitionRegion[]>([]);
  const [manifestData, setManifestData] = useState<AcquisitionManifestData | null>(null);

  const [selectedDatasetId, setSelectedDatasetId] = useState<string>("NASA_POWER_AG");
  const [selectedRegionId, setSelectedRegionId] = useState<string>("north");
  const [selectedVariable, setSelectedVariable] = useState<string>("T2M");
  const [startDate, setStartDate] = useState<string>("2023-01-01");
  const [endDate, setEndDate] = useState<string>("2023-12-31");
  const [maxGranules, setMaxGranules] = useState<number>(3);

  const [loadingInit, setLoadingInit] = useState<boolean>(true);
  const [searchingCmr, setSearchingCmr] = useState<boolean>(false);
  const [downloading, setDownloading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [cmrGranules, setCmrGranules] = useState<AcquisitionGranule[]>([]);
  const [cmrNote, setCmrNote] = useState<string | null>(null);
  const [jobResult, setJobResult] = useState<AcquisitionDownloadResponse | null>(null);
  const [confirmModalData, setConfirmModalData] = useState<AcquisitionDownloadResponse | null>(null);
  const [showMatrix, setShowMatrix] = useState<boolean>(false);

  const loadAcquisitionState = useCallback(async () => {
    setLoadingInit(true);
    setErrorMsg(null);
    try {
      const [catRes, boundRes, manRes] = await Promise.all([
        fetch(`${apiBase}/api/acquisition/catalog`),
        fetch(`${apiBase}/api/acquisition/boundaries`),
        fetch(`${apiBase}/api/acquisition/manifest`),
      ]);
      if (!catRes.ok) throw new Error(`Catalog HTTP ${catRes.status}`);
      const catJson = await catRes.json();
      setVariables(catJson.variables ?? []);
      setDatasets(catJson.datasets ?? []);
      setMatrix(catJson.availability_matrix ?? []);
      setAuthStatus(catJson.auth_status ?? null);

      if (boundRes.ok) {
        const boundJson = await boundRes.json();
        setRegions(boundJson.regions ?? []);
      }
      if (manRes.ok) {
        const manJson = await manRes.json();
        setManifestData(manJson);
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to initialize Data Acquisition Subsystem.");
    } finally {
      setLoadingInit(false);
    }
  }, [apiBase]);

  useEffect(() => {
    loadAcquisitionState();
  }, [loadAcquisitionState]);

  const filteredDatasets = useMemo(() => {
    if (domainFilter === "all") return datasets;
    return datasets.filter((d) => d.domain === domainFilter);
  }, [datasets, domainFilter]);

  const selectedDataset = useMemo(
    () => datasets.find((d) => d.dataset_id === selectedDatasetId) ?? filteredDatasets[0] ?? null,
    [datasets, filteredDatasets, selectedDatasetId]
  );

  useEffect(() => {
    if (selectedDataset && !selectedDataset.variable_names.includes(selectedVariable)) {
      setSelectedVariable(selectedDataset.variable_names[0] ?? "");
    }
  }, [selectedDataset, selectedVariable]);

  const selectedRegion = useMemo(
    () => regions.find((r) => r.region_id === selectedRegionId) ?? null,
    [regions, selectedRegionId]
  );

  const handleCmrSearch = async () => {
    if (!selectedDataset) return;
    setSearchingCmr(true);
    setErrorMsg(null);
    setCmrNote(null);
    try {
      const qs = new URLSearchParams({
        dataset_id: selectedDataset.dataset_id,
        start_date: startDate,
        end_date: endDate,
        region_id: selectedRegionId,
        page_size: String(Math.max(5, Math.min(20, maxGranules))),
      });
      const res = await fetch(`${apiBase}/api/acquisition/cmr-search?${qs.toString()}`);
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || `CMR Search HTTP ${res.status}`);
      setCmrGranules(json.granules ?? []);
      if (json.note) setCmrNote(json.note);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "NASA CMR granule search failed.");
    } finally {
      setSearchingCmr(false);
    }
  };

  const executeDownload = async (confirmLarge: boolean) => {
    if (!selectedDataset) return;
    setDownloading(true);
    setErrorMsg(null);
    setConfirmModalData(null);
    try {
      const res = await fetch(`${apiBase}/api/acquisition/download`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dataset_id: selectedDataset.dataset_id,
          variable: selectedVariable || undefined,
          start_date: startDate,
          end_date: endDate,
          region_id: selectedRegionId,
          max_granules: maxGranules,
          confirm_large_download: confirmLarge,
        }),
      });
      const json: AcquisitionDownloadResponse = await res.json();
      if (!res.ok) {
        throw new Error((json as unknown as { detail?: string }).detail || `Acquisition HTTP ${res.status}`);
      }
      if (json.status === "confirmation_required") {
        setConfirmModalData(json);
      } else {
        setJobResult(json);
        if (json.granules && json.granules.length > 0) {
          setCmrGranules(json.granules);
        }
        const manRes = await fetch(`${apiBase}/api/acquisition/manifest`);
        if (manRes.ok) {
          setManifestData(await manRes.json());
        }
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Download request failed.");
    } finally {
      setDownloading(false);
    }
  };

  const activeValidation = jobResult?.validation ?? jobResult?.pilot_inspection?.validation ?? null;
  const activeQc = jobResult?.qc ?? jobResult?.pilot_inspection?.qc ?? null;
  const activeSubset = jobResult?.spatial_subset ?? jobResult?.pilot_inspection?.spatial_subset ?? null;

  return (
    <div className="space-y-4">
      {/* Header Banner */}
      <header className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-800 bg-gradient-to-br from-slate-900 via-slate-900/95 to-slate-950 p-4 shadow-xl">
        <div>
          <div className="flex items-center gap-2">
            <Database className="h-5 w-5 text-cyan-400" />
            <h1 className="text-lg font-bold tracking-tight text-white sm:text-xl">
              NASA Earth Observation Data Acquisition &amp; QC Engine
            </h1>
          </div>
          <p className="mt-1 text-xs text-slate-400">
            Search official 19-variable Earth observation catalogs, verify Earthdata authentication, inspect NetCDF/HDF5
            quality flags, and mask grids strictly inside authoritative India GeoJSON polygons.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setShowMatrix((s) => !s)}
            className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-semibold transition ${
              showMatrix
                ? "border-cyan-400 bg-cyan-500/20 text-cyan-200"
                : "border-slate-700 bg-slate-900 text-slate-200 hover:bg-slate-800"
            }`}
          >
            <Layers className="h-3.5 w-3.5 text-cyan-400" />
            19-Variable Matrix
          </button>
          <button
            type="button"
            onClick={loadAcquisitionState}
            disabled={loadingInit}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loadingInit ? "animate-spin text-cyan-400" : ""}`} />
            Refresh State
          </button>
        </div>
      </header>

      {errorMsg && (
        <div className="flex items-start gap-2 rounded-xl border border-rose-500/40 bg-rose-950/50 p-3 text-xs text-rose-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-400" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Panel 5: Authentication Status Diagnostics (Zero secret values exposed) */}
      {authStatus && (
        <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 text-xs">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 font-bold text-white">
              <KeyRound className="h-4 w-4 text-amber-300" />
              Authentication &amp; Provider Readiness
            </div>
            <div className="flex flex-wrap gap-2">
              <span
                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 font-semibold ${
                  authStatus.earthdata_authenticated
                    ? "border border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
                    : "border border-amber-500/40 bg-amber-500/10 text-amber-200"
                }`}
              >
                {authStatus.earthdata_authenticated ? (
                  <ShieldCheck className="h-3 w-3" />
                ) : (
                  <ShieldAlert className="h-3 w-3" />
                )}
                NASA Earthdata: {authStatus.earthdata_method}
              </span>
              <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/40 bg-emerald-500/15 px-2.5 py-0.5 font-semibold text-emerald-300">
                <CheckCircle2 className="h-3 w-3" />
                NASA POWER Regional NetCDF: Ready (No Auth)
              </span>
            </div>
          </div>
          {authStatus.setup_instructions.length > 0 && (
            <div className="mt-2 space-y-1 text-xs text-slate-400">
              {authStatus.setup_instructions.map((tip, idx) => (
                <p key={idx}>• {tip}</p>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Panel 10: 19-Variable Physical Matrix (Collapsible) */}
      {showMatrix && matrix.length > 0 && (
        <section className="rounded-2xl border border-cyan-500/30 bg-slate-900/80 p-4 text-xs">
          <h2 className="mb-2 text-sm font-bold text-cyan-200">
            Official 19-Variable Physical Distinction &amp; Coverage Matrix ({variables.length} Variables)
          </h2>
          <div className="max-h-72 overflow-auto rounded-xl border border-slate-800">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-slate-950 text-slate-300">
                <tr>
                  <th className="p-2">Code</th>
                  <th className="p-2">Variable</th>
                  <th className="p-2">Domain</th>
                  <th className="p-2">Primary Dataset</th>
                  <th className="p-2">Units</th>
                  <th className="p-2">Physical Distinction</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {matrix.map((row) => (
                  <tr key={row.variable_code} className="hover:bg-slate-800/40">
                    <td className="p-2 font-mono font-bold text-cyan-300">{row.variable_code}</td>
                    <td className="p-2 font-semibold text-white">{row.variable_name}</td>
                    <td className="p-2 capitalize text-slate-300">{row.domain}</td>
                    <td className="p-2 font-mono text-slate-200">{row.primary_dataset}</td>
                    <td className="p-2 text-slate-300">{row.canonical_units}</td>
                    <td className="p-2 text-slate-400">{row.physical_distinction_note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Main Two-Column Acquisition Workspace */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        {/* Left Column: Panel 1 (Dataset Explorer) + Panel 2 (Metadata Viewer) */}
        <div className="space-y-4 lg:col-span-5">
          <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 text-xs">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold text-white">1. Dataset Explorer ({filteredDatasets.length})</h2>
              <span className="text-xs text-slate-400">Official CMR / Direct Catalog</span>
            </div>

            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {DOMAIN_LABELS.map((d) => (
                <button
                  key={d.id}
                  type="button"
                  onClick={() => setDomainFilter(d.id)}
                  className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition ${
                    domainFilter === d.id
                      ? "bg-cyan-500/20 text-cyan-200 ring-1 ring-cyan-400/50"
                      : "bg-slate-950 text-slate-400 hover:text-white"
                  }`}
                >
                  {d.label}
                </button>
              ))}
            </div>

            <div className="mt-3 max-h-80 space-y-2 overflow-y-auto pr-1">
              {filteredDatasets.map((ds) => {
                const isSelected = selectedDataset?.dataset_id === ds.dataset_id;
                return (
                  <button
                    key={ds.dataset_id}
                    type="button"
                    onClick={() => {
                      setSelectedDatasetId(ds.dataset_id);
                      setCmrGranules([]);
                      setJobResult(null);
                    }}
                    className={`w-full rounded-xl border p-3 text-left transition ${
                      isSelected
                        ? "border-cyan-400 bg-cyan-500/10"
                        : "border-slate-800 bg-slate-950/70 hover:border-slate-700"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs font-bold text-cyan-300">{ds.dataset_id}</span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                          ds.authentication_required
                            ? "bg-amber-500/15 text-amber-200"
                            : "bg-emerald-500/15 text-emerald-300"
                        }`}
                      >
                        {ds.authentication_required ? ds.auth_provider : "Open / No Auth"}
                      </span>
                    </div>
                    <p className="mt-1 font-semibold text-white">{ds.dataset_name}</p>
                    <p className="mt-0.5 text-xs text-slate-400">
                      {ds.scientific_variable} · {ds.spatial_resolution} · {ds.file_format}
                    </p>
                  </button>
                );
              })}
            </div>
          </section>

          {/* Panel 2: Dataset Metadata Viewer */}
          {selectedDataset && (
            <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 text-xs">
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-sm font-bold text-white">2. Scientific Dataset Metadata</h2>
                <a
                  href={selectedDataset.official_docs_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-xs font-semibold text-cyan-300 hover:underline"
                >
                  Official Docs <ExternalLink className="h-3 w-3" />
                </a>
              </div>

              <dl className="mt-3 grid grid-cols-2 gap-2 rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-xs">
                <div>
                  <dt className="text-slate-400">CMR Concept ID</dt>
                  <dd className="font-mono text-slate-200">{selectedDataset.collection_concept_id || "Direct REST API"}</dd>
                </div>
                <div>
                  <dt className="text-slate-400">Provider / Version</dt>
                  <dd className="text-slate-200">
                    {selectedDataset.data_provider} (v{selectedDataset.product_version})
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-400">Resolution (Spatial / Temp)</dt>
                  <dd className="text-slate-200">
                    {selectedDataset.spatial_resolution} · {selectedDataset.temporal_resolution}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-400">Units / Format</dt>
                  <dd className="text-slate-200">
                    {selectedDataset.units} · {selectedDataset.file_format}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-400">Temporal Coverage</dt>
                  <dd className="text-slate-200">
                    {selectedDataset.first_available_date} to {selectedDataset.last_available_date}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-400">Download Mechanism</dt>
                  <dd className="text-slate-200">{selectedDataset.download_mechanism}</dd>
                </div>
              </dl>

              <p className="mt-2.5 text-xs text-slate-300">
                <strong className="text-cyan-300">Scientific Justification:</strong> {selectedDataset.scientific_justification}
              </p>
              <p className="mt-1.5 text-xs text-amber-200/90">
                <strong>Known Limitations:</strong> {selectedDataset.data_limitations}
              </p>
            </section>
          )}
        </div>

        {/* Right Column: Panels 3, 4, 6, 7, 8 (Spatial/Temporal Pickers + CMR + Download + Validation & QC Inspector) */}
        <div className="space-y-4 lg:col-span-7">
          <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 text-xs">
            <h2 className="text-sm font-bold text-white">
              3. Spatial &amp; Temporal Subset Configurator (India Polygons)
            </h2>

            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1">
                <span className="flex items-center gap-1 text-xs text-slate-400">
                  <MapPin className="h-3.5 w-3.5 text-cyan-400" />
                  India Polygon Boundary ({regions.length} loaded)
                </span>
                <select
                  value={selectedRegionId}
                  onChange={(e) => setSelectedRegionId(e.target.value)}
                  className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 outline-none focus:border-cyan-400"
                >
                  {regions.map((r) => (
                    <option key={r.region_id} value={r.region_id}>
                      [{r.level.toUpperCase()}] {r.name} ({r.vertex_count} vertices)
                    </option>
                  ))}
                </select>
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Target Dataset Variable</span>
                <select
                  value={selectedVariable}
                  onChange={(e) => setSelectedVariable(e.target.value)}
                  className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 outline-none focus:border-cyan-400"
                >
                  {(selectedDataset?.variable_names ?? []).map((v) => (
                    <option key={v} value={v}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">Start Date (YYYY-MM-DD)</span>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 outline-none focus:border-cyan-400"
                />
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">End Date (YYYY-MM-DD)</span>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100 outline-none focus:border-cyan-400"
                />
              </label>
            </div>

            {selectedRegion && (
              <div className="mt-2.5 flex flex-wrap items-center gap-3 rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-xs text-slate-300">
                <span>
                  <strong className="text-cyan-300">Polygon:</strong> {selectedRegion.name}
                </span>
                <span>Vertices: {selectedRegion.vertex_count}</span>
                <span>BBox [W, S, E, N]: {selectedRegion.bbox.join(", ")}</span>
              </div>
            )}

            <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
              <label className="flex items-center gap-2 text-xs text-slate-300">
                <span>Max Granules:</span>
                <input
                  type="number"
                  min={1}
                  max={60}
                  value={maxGranules}
                  onChange={(e) => setMaxGranules(Math.max(1, Math.min(60, Number(e.target.value) || 3)))}
                  className="w-16 rounded-lg border border-slate-700 bg-slate-950 px-2 py-1 text-center text-white"
                />
              </label>

              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={handleCmrSearch}
                  disabled={searchingCmr || !selectedDataset}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800 px-3.5 py-2 text-xs font-semibold text-slate-100 transition hover:bg-slate-700 disabled:opacity-50"
                >
                  {searchingCmr ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
                  Discover NASA CMR Granules
                </button>

                <button
                  type="button"
                  onClick={() => executeDownload(false)}
                  disabled={downloading || !selectedDataset}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-cyan-500 px-4 py-2 text-xs font-bold text-slate-950 transition hover:bg-cyan-400 disabled:opacity-50"
                >
                  {downloading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                  Acquire, Validate &amp; Subset India
                </button>
              </div>
            </div>
          </section>

          {/* CMR Discovery Table */}
          {(cmrNote || cmrGranules.length > 0) && (
            <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 text-xs">
              <h3 className="text-xs font-bold text-white">
                Live NASA CMR Granule Results ({cmrGranules.length})
              </h3>
              {cmrNote && <p className="mt-1 text-xs text-amber-200">{cmrNote}</p>}
              {cmrGranules.length > 0 && (
                <div className="mt-2 max-h-48 overflow-auto rounded-xl border border-slate-800">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-950 text-slate-400">
                      <tr>
                        <th className="p-2">Title</th>
                        <th className="p-2">Start</th>
                        <th className="p-2">Size (MB)</th>
                        <th className="p-2">Access Link</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {cmrGranules.map((g) => (
                        <tr key={g.granule_id}>
                          <td className="p-2 font-mono text-cyan-200">{g.title}</td>
                          <td className="p-2 text-slate-300">{g.time_start?.slice(0, 10) || "—"}</td>
                          <td className="p-2 text-slate-300">{g.size_mb ?? "—"}</td>
                          <td className="p-2">
                            {g.download_url ? (
                              <a
                                href={g.download_url}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1 text-cyan-300 hover:underline"
                              >
                                Archive URL <ExternalLink className="h-3 w-3" />
                              </a>
                            ) : (
                              "—"
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}

          {/* Panel 7 & 8: Download Progress + Validation & QC Inspector */}
          {jobResult && (
            <section className="space-y-3 rounded-2xl border border-slate-800 bg-slate-900/70 p-4 text-xs">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2 font-bold text-white">
                  <FileCheck2 className="h-4 w-4 text-emerald-400" />
                  Acquisition, Structural Validation &amp; Polygon Masking Report
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${
                      jobResult.status === "completed"
                        ? "bg-emerald-500/15 text-emerald-300"
                        : "bg-amber-500/15 text-amber-200"
                    }`}
                  >
                    {jobResult.status.toUpperCase()}
                  </span>
                  {onAnalyzeDataset && (
                    <button
                      type="button"
                      onClick={() =>
                        onAnalyzeDataset({
                          variable: selectedVariable,
                          regionId: selectedRegionId,
                          startYear: Number(startDate.slice(0, 4)) || 1990,
                          endYear: Number(endDate.slice(0, 4)) || 2025,
                        })
                      }
                      className="rounded-lg bg-cyan-500 px-3 py-1 text-xs font-bold text-slate-950 transition hover:bg-cyan-400"
                    >
                      Analyse this data
                    </button>
                  )}
                </div>
              </div>

              {jobResult.message && (
                <p className="rounded-xl border border-amber-500/30 bg-amber-950/30 p-2.5 text-xs text-amber-200">
                  {jobResult.message}
                </p>
              )}

              {jobResult.pilot_inspection && (
                <p className="rounded-xl border border-cyan-500/30 bg-cyan-950/30 p-2 text-xs text-cyan-200">
                  Showing validated India-bounded MOP03JM pilot sample (`{jobResult.pilot_inspection.retrieval_mode}`)
                  while Earthdata Login is unconfigured.
                </p>
              )}

              {activeValidation && (
                <div className="grid grid-cols-2 gap-2 rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-xs sm:grid-cols-4">
                  <div>
                    <span className="text-slate-400">Format / Size</span>
                    <p className="font-semibold text-white">
                      {activeValidation.file_format} · {(activeValidation.file_size_bytes / 1024).toFixed(1)} KB
                    </p>
                  </div>
                  <div>
                    <span className="text-slate-400">Dimensions</span>
                    <p className="font-mono text-cyan-200">
                      {Object.entries(activeValidation.dimensions)
                        .map(([k, v]) => `${k}:${v}`)
                        .join(", ")}
                    </p>
                  </div>
                  <div>
                    <span className="text-slate-400">Missing Values</span>
                    <p className="font-semibold text-white">{activeValidation.missing_value_pct}%</p>
                  </div>
                  <div>
                    <span className="text-slate-400">Duplicates / Gaps</span>
                    <p className="font-semibold text-white">
                      {activeValidation.duplicate_timestamps_count} dup · {activeValidation.missing_timestamps_count} gaps
                    </p>
                  </div>
                </div>
              )}

              {activeQc && (
                <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-xs">
                  <p className="font-semibold text-white">
                    QC Profile: <span className="font-mono text-cyan-300">{activeQc.qc_profile}</span> · Valid:{" "}
                    {activeQc.valid_after_qc} / {activeQc.total_observations} (Filtered: {activeQc.filtered_fill_count} fill,{" "}
                    {activeQc.filtered_qc_flag_count} QC-flagged, {activeQc.filtered_out_of_range_count} out-of-range)
                  </p>
                  <p className="mt-1 text-slate-400">Applied filters: {activeQc.applied_filters.join(" · ")}</p>
                </div>
              )}

              {activeSubset && (
                <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-3 text-xs">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-bold text-emerald-200">
                      <Globe2 className="mr-1 inline h-3.5 w-3.5" />
                      Polygon Masking: {activeSubset.region_name} ({activeSubset.grid_cells_inside_mask} /{" "}
                      {activeSubset.grid_cells_total} grid cells inside {activeSubset.polygon_vertex_count}-vertex GeoJSON)
                    </span>
                    <span className="font-mono text-emerald-300">
                      Area-Weighted Mean: {activeSubset.regional_mean ?? "—"} {activeSubset.units}
                    </span>
                  </div>
                  {activeSubset.time_series.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {activeSubset.time_series.slice(0, 12).map((pt) => (
                        <span
                          key={pt.timestamp}
                          className="rounded-md border border-slate-800 bg-slate-950 px-2 py-0.5 font-mono text-xs text-slate-200"
                        >
                          {pt.timestamp}: {pt.area_weighted_mean ?? "—"}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </section>
          )}
        </div>
      </div>

      {/* Panel 9: Download Manifest & Validation Report Table */}
      <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 text-xs">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 font-bold text-white">
            <FolderArchive className="h-4 w-4 text-cyan-400" />
            Local Acquisition Manifest (`metadata/download_manifest.csv`)
          </div>
          <span className="text-xs text-slate-400">
            {manifestData?.manifest.length ?? 0} registered files · {manifestData?.validations.length ?? 0} validation checks
          </span>
        </div>

        <div className="mt-3 max-h-64 overflow-auto rounded-xl border border-slate-800">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-slate-950 text-slate-300">
              <tr>
                <th className="p-2">Dataset</th>
                <th className="p-2">Granule</th>
                <th className="p-2">Var</th>
                <th className="p-2">Region</th>
                <th className="p-2">Size</th>
                <th className="p-2">Retrieval</th>
                <th className="p-2">Validation</th>
                <th className="p-2">SHA-256 (Prefix)</th>
                <th className="p-2">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {(manifestData?.manifest ?? []).slice(-20).reverse().map((row, i) => (
                <tr key={`${row.manifest_id}-${i}`} className="hover:bg-slate-800/40">
                  <td className="p-2 font-mono font-bold text-cyan-300">{row.dataset_id}</td>
                  <td className="p-2 font-mono text-slate-200">{row.granule_id}</td>
                  <td className="p-2 text-slate-300">{row.variable_code}</td>
                  <td className="p-2 text-slate-300">{row.region_id}</td>
                  <td className="p-2 text-slate-300">{row.file_size_bytes} B</td>
                  <td className="p-2 text-slate-200">{row.retrieval_status}</td>
                  <td className="p-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-bold ${
                        row.validation_status === "validated"
                          ? "bg-emerald-500/15 text-emerald-300"
                          : row.validation_status === "rejected"
                          ? "bg-rose-500/15 text-rose-300"
                          : "bg-slate-700 text-slate-300"
                      }`}
                    >
                      {row.validation_status}
                    </span>
                  </td>
                  <td className="p-2 font-mono text-slate-400">{(row.sha256 || "").slice(0, 12)}…</td>
                  <td className="p-2">
                    {onAnalyzeDataset && (
                      <button
                        type="button"
                        onClick={() =>
                          onAnalyzeDataset({
                            variable: row.variable_code || selectedVariable,
                            regionId: row.region_id || selectedRegionId,
                          })
                        }
                        className="rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-2.5 py-1 text-xs font-semibold text-cyan-200 hover:bg-cyan-500/20"
                      >
                        Analyse this data
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {(!manifestData || manifestData.manifest.length === 0) && (
                <tr>
                  <td colSpan={9} className="p-4 text-center text-slate-400">
                    No downloaded datasets registered yet. Run a live NASA POWER or Earthdata download above.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Panel 6: Large-Download Confirmation Modal */}
      {confirmModalData && (
        <div className="fixed inset-0 z-[920] flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-amber-500/40 bg-slate-900 p-5 text-xs shadow-2xl">
            <div className="flex items-center gap-2 text-sm font-bold text-amber-200">
              <AlertTriangle className="h-5 w-5 text-amber-400" />
              Confirm Large Archive Download
            </div>
            <p className="mt-2 text-slate-300">{confirmModalData.message}</p>
            <div className="mt-3 rounded-xl border border-slate-800 bg-slate-950 p-3 text-xs text-slate-300">
              <p>Dataset: <strong>{confirmModalData.dataset_id}</strong></p>
              <p>Estimated months: <strong>{confirmModalData.estimated_months}</strong></p>
              <p>Estimated granules: <strong>{confirmModalData.estimated_granules}</strong> (~{confirmModalData.estimated_size_mb} MB)</p>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirmModalData(null)}
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-slate-300 hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => executeDownload(true)}
                className="rounded-lg bg-amber-400 px-4 py-1.5 font-bold text-slate-950 hover:bg-amber-300"
              >
                Proceed with Download
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
