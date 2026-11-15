import { useEffect, useMemo, useState } from "react";
import L from "leaflet";
import {
  GeoJSON as LeafletGeoJSON,
  MapContainer,
  Marker,
  Polyline,
  Popup,
  Rectangle,
  TileLayer,
  useMap,
  useMapEvents,
} from "react-leaflet";
import {
  ArrowLeftRight,
  Crosshair,
  Globe,
  HelpCircle,
  Layers,
  MapPin,
  Radio,
  Trash2,
} from "lucide-react";
import { API_BASE_URL, FREE_MAP_TILES } from "./config";
import type {
  BoundingBox,
  GeoPoint,
  SeriesStats,
  TeleconnectionSummary,
  TrendMapRegion,
  TrendMapResponse,
} from "./types";

type MapStyleMode = "dark" | "satellite" | "terrain";

function getDivergingSlopeColor(slope: number, maxAbs: number): string {
  const safeMax = Math.max(maxAbs, 1e-6);
  const ratio = Math.max(-1, Math.min(1, slope / safeMax));
  if (ratio >= 0) {
    const t = Math.min(1, ratio);
    // Warm amber -> crimson
    const r = Math.round(251 - t * 26);
    const g = Math.round(191 - t * 135);
    const b = Math.round(36 + t * 30);
    return `rgb(${r}, ${g}, ${b})`;
  }
  const t = Math.min(1, -ratio);
  // Teal -> deep cyan/blue
  const r = Math.round(45 - t * 31);
  const g = Math.round(212 - t * 47);
  const b = Math.round(191 + t * 42);
  return `rgb(${r}, ${g}, ${b})`;
}

interface SplitMapProps {
  parameter: string;
  pointA: GeoPoint | null;
  pointB: GeoPoint | null;
  activeTarget: "A" | "B";
  onChangeActiveTarget: (target: "A" | "B") => void;
  onSelectPoint: (target: "A" | "B", lat: number, lon: number, resolvedName?: string) => void;
  onClearPointB: () => void;
  onSwapPoints: () => void;
  primaryStats: SeriesStats | null;
  comparisonStats: SeriesStats | null;
  teleconnection: TeleconnectionSummary | null;
  primaryBBox: BoundingBox | null;
  comparisonBBox: BoundingBox | null;
  fitVersion: number;
  trendMap?: TrendMapResponse | null;
  onSelectRegion?: (region: TrendMapRegion) => void;
}

function getSlopeColor(
  parameter: string,
  slopePerYear: number | null | undefined,
  isSignificant: boolean | null | undefined
): { hex: string; label: string; positive: boolean } {
  if (slopePerYear === null || slopePerYear === undefined) {
    return { hex: "#94a3b8", label: "Pending Analysis", positive: true };
  }
  if (!isSignificant) {
    return { hex: "#facc15", label: "Insignificant / Natural Noise (p ≥ 0.05)", positive: slopePerYear >= 0 };
  }
  const code = parameter.toUpperCase();
  if (code === "T2M") {
    return slopePerYear >= 0
      ? { hex: "#fb7185", label: "Significant Warming (p < 0.05)", positive: true }
      : { hex: "#38bdf8", label: "Significant Cooling (p < 0.05)", positive: false };
  }
  if (code === "PS") {
    return slopePerYear >= 0
      ? { hex: "#818cf8", label: "Rising Surface Pressure", positive: true }
      : { hex: "#fbbf24", label: "Falling Surface Pressure", positive: false };
  }
  return slopePerYear >= 0
    ? { hex: "#2dd4bf", label: "Significant Wetting (p < 0.05)", positive: true }
    : { hex: "#f59e0b", label: "Significant Drying (p < 0.05)", positive: false };
}

function getParameterLegendItems(parameter: string): { label: string; hex: string; description: string }[] {
  const code = parameter.toUpperCase();
  if (code === "T2M") {
    return [
      { label: "Significant Warming", hex: "#fb7185", description: "Temperature rising (p < 0.05)" },
      { label: "Significant Cooling", hex: "#38bdf8", description: "Temperature falling (p < 0.05)" },
      { label: "Insignificant / Noise", hex: "#facc15", description: "Natural variability (p ≥ 0.05)" },
    ];
  }
  if (code === "PS") {
    return [
      { label: "Rising Pressure", hex: "#818cf8", description: "Surface pressure increasing (p < 0.05)" },
      { label: "Falling Pressure", hex: "#fbbf24", description: "Surface pressure decreasing (p < 0.05)" },
      { label: "Insignificant / Noise", hex: "#facc15", description: "Natural variability (p ≥ 0.05)" },
    ];
  }
  return [
    { label: "Significant Wetting", hex: "#2dd4bf", description: "Moisture increasing (p < 0.05)" },
    { label: "Significant Drying", hex: "#f59e0b", description: "Moisture decreasing (p < 0.05)" },
    { label: "Insignificant / Noise", hex: "#facc15", description: "Natural variability (p ≥ 0.05)" },
  ];
}

function createBadgeIcon(label: "A" | "B", colorHex: string, isActive: boolean): L.DivIcon {
  const ring = isActive
    ? `box-shadow: 0 0 0 4px rgba(34,211,238,0.45), 0 4px 16px rgba(0,0,0,0.75); transform: translate(-16px, -16px) scale(1.1);`
    : `box-shadow: 0 4px 12px rgba(0,0,0,0.65); transform: translate(-15px, -15px);`;
  const html = `
    <div style="
      width: 32px;
      height: 32px;
      border-radius: 9999px;
      background: ${colorHex};
      border: 2.5px solid #020617;
      color: #020617;
      font-weight: 800;
      font-size: 13px;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: transform 0.15s ease-out;
      ${ring}
    ">${label}</div>
  `;
  return L.divIcon({
    className: "terrashift-marker-icon",
    html,
    iconSize: [0, 0],
    iconAnchor: [0, 0],
  });
}

function MapClickHandler({
  activeTarget,
  onSelectPoint,
}: {
  activeTarget: "A" | "B";
  onSelectPoint: (target: "A" | "B", lat: number, lon: number, resolvedName?: string) => void;
}) {
  useMapEvents({
    click(e) {
      const wrapped = e.latlng.wrap();
      const lat = Number(Math.min(37.5, Math.max(6.0, wrapped.lat)).toFixed(3));
      const lon = Number(Math.min(97.5, Math.max(68.0, wrapped.lng)).toFixed(3));
      onSelectPoint(activeTarget, lat, lon);
    },
  });
  return null;
}

function ViewportController({
  pointA,
  pointB,
  fitVersion,
}: {
  pointA: GeoPoint | null;
  pointB: GeoPoint | null;
  fitVersion: number;
}) {
  const map = useMap();

  useEffect(() => {
    if (fitVersion === 0) return;
    if (pointA && pointB) {
      const bounds = L.latLngBounds([pointA.lat, pointA.lon], [pointB.lat, pointB.lon]);
      map.fitBounds(bounds.pad(0.35), { maxZoom: 6, animate: true, duration: 0.7 });
    } else if (pointA) {
      map.flyTo([pointA.lat, pointA.lon], 6, { duration: 0.7 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitVersion]);

  return null;
}

function computeLocalBBox(point: GeoPoint): BoundingBox {
  return {
    south: Number((point.lat - 0.25).toFixed(4)),
    north: Number((point.lat + 0.25).toFixed(4)),
    west: Number((point.lon - 0.3125).toFixed(4)),
    east: Number((point.lon + 0.3125).toFixed(4)),
  };
}

export default function SplitMap({
  parameter,
  pointA,
  pointB,
  activeTarget,
  onChangeActiveTarget,
  onSelectPoint,
  onClearPointB,
  onSwapPoints,
  primaryStats,
  comparisonStats,
  teleconnection,
  primaryBBox,
  comparisonBBox,
  fitVersion,
  trendMap,
  onSelectRegion,
}: SplitMapProps) {
  const [styleMode, setStyleMode] = useState<MapStyleMode>("dark");
  const [mobileLegendOpen, setMobileLegendOpen] = useState<boolean>(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [indiaGeoJson, setIndiaGeoJson] = useState<any>(null);

  useEffect(() => {
    const apiBase = API_BASE_URL.replace(/\/$/, "");
    fetch(`${apiBase}/api/india/boundaries-geojson`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data && data.type) setIndiaGeoJson(data);
      })
      .catch(() => {
        // Ignore if boundary GeoJSON cannot be fetched
      });
  }, []);

  const tileConfig = useMemo(() => {
    const tile = FREE_MAP_TILES[styleMode];
    return {
      key: `free-${styleMode}`,
      url: tile.url,
      attribution: tile.attribution,
      tileSize: 256,
      zoomOffset: 0,
      providerBadge: tile.providerBadge,
      isOsmDark: styleMode === "dark",
    };
  }, [styleMode]);

  const colorA = getSlopeColor(parameter, primaryStats?.sens_slope_per_year, primaryStats?.is_significant);
  const colorB = getSlopeColor(
    parameter,
    comparisonStats?.sens_slope_per_year ?? teleconnection?.comparison_sens_slope_per_year,
    comparisonStats?.is_significant ?? teleconnection?.comparison_is_significant
  );

  const iconA = useMemo(
    () => createBadgeIcon("A", colorA.hex, activeTarget === "A"),
    [colorA.hex, activeTarget]
  );
  const iconB = useMemo(
    () => createBadgeIcon("B", colorB.hex, activeTarget === "B"),
    [colorB.hex, activeTarget]
  );

  const boxA = primaryBBox ?? (pointA ? computeLocalBBox(pointA) : null);
  const boxB = comparisonBBox ?? (pointB ? computeLocalBBox(pointB) : null);

  const rVal = teleconnection?.cross_correlation_r;
  const teleBadge = useMemo(() => {
    if (!teleconnection?.enabled || rVal === null || rVal === undefined) return null;
    if (rVal <= -0.25) {
      return {
        text: `Inverse Seesaw Dipole (r = ${rVal.toFixed(2)})`,
        cls: "border-rose-500/40 bg-rose-950/85 text-rose-200",
      };
    }
    if (rVal >= 0.25) {
      return {
        text: `Synchronized Co-Movement (r = +${rVal.toFixed(2)})`,
        cls: "border-emerald-500/40 bg-emerald-950/85 text-emerald-200",
      };
    }
    return {
      text: `Decoupled Systems (r = ${rVal.toFixed(2)})`,
      cls: "border-slate-600/60 bg-slate-900/90 text-slate-200",
    };
  }, [teleconnection?.enabled, rVal]);

  const legendItems = useMemo(() => getParameterLegendItems(parameter), [parameter]);

  return (
    <div className="relative flex flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/70 shadow-xl">
      {/* Top Toolbar with Target Selectors and Map Options */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 border-b border-slate-800 bg-slate-900/95 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <Crosshair className="h-4 w-4 text-cyan-400" />
          <span className="text-xs font-bold uppercase tracking-wider text-slate-200">
            Dual-Region Teleconnection Map
          </span>
          <span className="inline-flex items-center gap-1 rounded-full border border-cyan-500/30 bg-cyan-950/40 px-2.5 py-0.5 text-xs font-medium text-cyan-300">
            <Globe className="h-3 w-3" />
            {tileConfig.providerBadge}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Map Layer Switcher */}
          <div className="flex items-center rounded-lg border border-slate-800 bg-slate-950 p-0.5 text-xs">
            <Layers className="mx-1.5 h-3 w-3 text-slate-400" />
            {(["dark", "satellite", "terrain"] as MapStyleMode[]).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setStyleMode(m)}
                className={`rounded-md px-2.5 py-1 font-medium capitalize transition ${
                  styleMode === m
                    ? "bg-cyan-500 font-bold text-slate-950"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {m}
              </button>
            ))}
          </div>

          {/* Region A Selector Button */}
          <button
            type="button"
            onClick={() => onChangeActiveTarget("A")}
            title="Clicking the globe will set Primary Region A"
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
              activeTarget === "A"
                ? "bg-cyan-500 text-slate-950 ring-2 ring-cyan-300/80 shadow-md"
                : "bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white"
            }`}
          >
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: activeTarget === "A" ? "#020617" : colorA.hex }}
            />
            {activeTarget === "A" ? "Clicking sets Region A" : "Set Region A"}
          </button>

          {/* Region B Selector Button */}
          <button
            type="button"
            onClick={() => onChangeActiveTarget("B")}
            title="Clicking the globe will set Comparison Region B for teleconnection analysis"
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
              activeTarget === "B"
                ? "bg-indigo-500 text-white ring-2 ring-indigo-300/80 shadow-md"
                : "bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white"
            }`}
          >
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: activeTarget === "B" ? "#ffffff" : colorB.hex }}
            />
            {activeTarget === "B" ? "Clicking sets Region B" : "Set Region B"}
          </button>

          {pointA && pointB && (
            <button
              type="button"
              onClick={onSwapPoints}
              title="Swap Region A and Region B"
              className="flex items-center gap-1 rounded-lg bg-slate-800 px-2.5 py-1.5 text-xs font-medium text-slate-300 transition hover:bg-slate-700"
            >
              <ArrowLeftRight className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Swap</span>
            </button>
          )}

          {pointB && (
            <button
              type="button"
              onClick={onClearPointB}
              title="Remove Comparison Region B"
              className="flex items-center gap-1 rounded-lg bg-slate-800 px-2.5 py-1.5 text-xs font-medium text-rose-300 transition hover:bg-rose-950/60"
            >
              <Trash2 className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Clear B</span>
            </button>
          )}
        </div>
      </div>

      {/* Map Canvas with Leaflet */}
      <div
        className={`relative h-[340px] w-full sm:h-[400px] ${(tileConfig as { isOsmDark?: boolean }).isOsmDark ? "osm-dark-tiles" : ""}`}
      >
        <MapContainer
          center={[22.5, 82.0]}
          zoom={4}
          minZoom={4}
          maxZoom={11}
          maxBounds={[
            [4.5, 65.0],
            [39.0, 100.0],
          ]}
          maxBoundsViscosity={0.9}
          className="h-full w-full"
        >
          <TileLayer
            key={tileConfig.key}
            attribution={tileConfig.attribution}
            url={tileConfig.url}
            tileSize={tileConfig.tileSize}
            zoomOffset={tileConfig.zoomOffset}
          />

          {trendMap?.geojson && (
            <LeafletGeoJSON
              key={`trend-choro-${trendMap.cache_id}`}
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              data={trendMap.geojson as any}
              style={(feature) => {
                const props = (feature?.properties || {}) as Record<string, unknown>;
                const slope = typeof props.slope_per_year === "number" ? props.slope_per_year : 0;
                const sigFdr = Boolean(props.significant_fdr);
                const maxAbs = trendMap.legend_range?.symmetric_abs_p95 || 0.05;
                return {
                  color: sigFdr ? "#f8fafc" : "#64748b",
                  weight: sigFdr ? 1.6 : 0.8,
                  dashArray: sigFdr ? undefined : "3 3",
                  opacity: 0.9,
                  fillColor: getDivergingSlopeColor(slope, maxAbs),
                  fillOpacity: sigFdr ? 0.78 : 0.28,
                };
              }}
              onEachFeature={(feature, layer) => {
                const props = (feature?.properties || {}) as Record<string, unknown>;
                const regId = String(props.region_id || "");
                const name = String(props.name || regId);
                const slope = typeof props.slope_per_year === "number" ? props.slope_per_year : 0;
                const pVal = typeof props.p_value === "number" ? props.p_value : 1;
                const qVal = typeof props.q_value === "number" ? props.q_value : 1;
                const sigFdr = Boolean(props.significant_fdr);
                layer.bindTooltip(
                  `<div style="font-size:12px"><strong>${name}</strong><br/>Slope: ${slope >= 0 ? "+" : ""}${slope.toFixed(4)} ${trendMap.unit}/yr<br/>p = ${pVal.toFixed(4)} | q(FDR) = ${qVal.toFixed(4)}<br/><em>${sigFdr ? "FDR significant (q < 0.05)" : "Not FDR significant"}</em></div>`,
                  { sticky: true }
                );
                layer.on("click", () => {
                  const found = trendMap.regions.find((r) => r.region_id === regId);
                  if (found && onSelectRegion) {
                    onSelectRegion(found);
                  }
                });
              }}
            />
          )}

          {!trendMap && indiaGeoJson && (
            <LeafletGeoJSON
              data={indiaGeoJson}
              style={{
                color: "#22d3ee",
                weight: 1,
                opacity: 0.45,
                fillColor: "#06b6d4",
                fillOpacity: 0.03,
              }}
            />
          )}

          <MapClickHandler activeTarget={activeTarget} onSelectPoint={onSelectPoint} />
          <ViewportController pointA={pointA} pointB={pointB} fitVersion={fitVersion} />

          {/* Grid Cell Bounding Boxes */}
          {boxA && (
            <Rectangle
              bounds={[
                [boxA.south, boxA.west],
                [boxA.north, boxA.east],
              ]}
              pathOptions={{ color: colorA.hex, weight: 1.8, fillOpacity: 0.18, dashArray: "4 4" }}
            />
          )}
          {boxB && (
            <Rectangle
              bounds={[
                [boxB.south, boxB.west],
                [boxB.north, boxB.east],
              ]}
              pathOptions={{ color: colorB.hex, weight: 1.8, fillOpacity: 0.18, dashArray: "4 4" }}
            />
          )}

          {/* Teleconnection Dashed Link Line */}
          {pointA && pointB && (
            <Polyline
              positions={[
                [pointA.lat, pointA.lon],
                [pointB.lat, pointB.lon],
              ]}
              pathOptions={{
                color: "#38bdf8",
                weight: 2.2,
                dashArray: "6 8",
                opacity: 0.9,
              }}
            />
          )}

          {pointA && (
            <Marker
              position={[pointA.lat, pointA.lon]}
              icon={iconA}
              draggable={true}
              eventHandlers={{
                dragend(e) {
                  const pos = e.target.getLatLng().wrap();
                  const lat = Number(pos.lat.toFixed(3));
                  const lon = Number(pos.lng.toFixed(3));
                  onSelectPoint("A", lat, lon);
                },
              }}
            >
              <Popup>
                <div className="text-xs text-slate-900">
                  <p className="font-bold text-cyan-900">Primary Region (Marker A)</p>
                  <p className="font-semibold text-slate-800">{pointA.name}</p>
                  <p className="font-mono text-slate-600">
                    {pointA.lat.toFixed(2)}°, {pointA.lon.toFixed(2)}°
                  </p>
                  <p className="mt-1 font-medium" style={{ color: colorA.hex }}>
                    Status: {colorA.label}
                  </p>
                </div>
              </Popup>
            </Marker>
          )}

          {pointB && (
            <Marker
              position={[pointB.lat, pointB.lon]}
              icon={iconB}
              draggable={true}
              eventHandlers={{
                dragend(e) {
                  const pos = e.target.getLatLng().wrap();
                  const lat = Number(pos.lat.toFixed(3));
                  const lon = Number(pos.lng.toFixed(3));
                  onSelectPoint("B", lat, lon);
                },
              }}
            >
              <Popup>
                <div className="text-xs text-slate-900">
                  <p className="font-bold text-indigo-900">Comparison Region (Marker B)</p>
                  <p className="font-semibold text-slate-800">{pointB.name}</p>
                  <p className="font-mono text-slate-600">
                    {pointB.lat.toFixed(2)}°, {pointB.lon.toFixed(2)}°
                  </p>
                  <p className="mt-1 font-medium" style={{ color: colorB.hex }}>
                    Status: {colorB.label}
                  </p>
                </div>
              </Popup>
            </Marker>
          )}
        </MapContainer>

        {/* Floating Teleconnection Pill */}
        {teleBadge && (
          <div
            className={`pointer-events-none absolute right-3 top-3 z-[400] flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-bold shadow-lg backdrop-blur-md ${teleBadge.cls}`}
          >
            <Radio className="h-3.5 w-3.5" />
            {teleBadge.text}
          </div>
        )}

        {/* Dynamic Desktop Legend */}
        <div className="pointer-events-none absolute bottom-3 left-3 z-[400] hidden flex-col gap-1 rounded-xl border border-slate-700/80 bg-slate-950/90 p-2.5 text-xs text-slate-200 shadow-xl backdrop-blur-md sm:flex">
          <p className="font-bold uppercase tracking-wider text-slate-400 text-xs">
            {trendMap
              ? `Choropleth Slope (${trendMap.unit}/yr, ±${trendMap.legend_range.symmetric_abs_p95.toFixed(3)})`
              : `Map Status Legend (${parameter.toUpperCase()})`}
          </p>
          <div className="flex flex-wrap items-center gap-3">
            {legendItems.map((item) => (
              <span key={item.label} className="flex items-center gap-1.5">
                <span
                  className="h-2.5 w-2.5 rounded-full ring-1 ring-slate-900"
                  style={{ backgroundColor: item.hex }}
                />
                <span className="font-medium">{item.label}</span>
              </span>
            ))}
          </div>
        </div>

        {/* Mobile Legend Button & Drawer */}
        <div className="absolute bottom-3 left-3 z-[400] sm:hidden">
          <button
            type="button"
            onClick={() => setMobileLegendOpen((o) => !o)}
            className="flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-950/90 px-2.5 py-1 text-xs font-semibold text-cyan-300 shadow backdrop-blur-md"
          >
            <HelpCircle className="h-3.5 w-3.5" />
            {mobileLegendOpen ? "Close Legend" : "Map Legend"}
          </button>
          {mobileLegendOpen && (
            <div className="mt-1.5 rounded-xl border border-slate-700 bg-slate-950/95 p-2.5 text-xs text-slate-200 shadow-xl">
              <p className="font-bold text-xs uppercase tracking-wider text-slate-400">
                Status Legend ({parameter.toUpperCase()})
              </p>
              <div className="mt-1.5 space-y-1">
                {legendItems.map((item) => (
                  <div key={item.label} className="flex items-center gap-2">
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-full"
                      style={{ backgroundColor: item.hex }}
                    />
                    <span>{item.label}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Computed Opposite Trends Panel (when choropleth trendMap is loaded) */}
      {trendMap && (
        <div className="grid grid-cols-1 gap-2.5 border-t border-slate-800 bg-slate-950/90 px-4 py-3 text-xs sm:grid-cols-2">
          <div className="rounded-xl border border-rose-500/30 bg-rose-950/20 p-3">
            <p className="font-bold text-rose-300">Top Positive Trends (FDR-corrected)</p>
            <div className="mt-1.5 space-y-1">
              {(trendMap.opposite_trends?.top_positive || []).slice(0, 3).map((reg) => (
                <button
                  key={reg.region_id}
                  type="button"
                  onClick={() => onSelectRegion?.(reg)}
                  className="flex w-full items-center justify-between rounded-lg px-2 py-1 text-left transition hover:bg-rose-900/30"
                >
                  <span className="font-medium text-slate-100">{reg.name}</span>
                  <span className="font-mono text-rose-300">
                    +{reg.slope_per_year.toFixed(4)} {trendMap.unit}/yr (q={reg.q_value.toFixed(3)})
                  </span>
                </button>
              ))}
              {(!trendMap.opposite_trends?.top_positive || trendMap.opposite_trends.top_positive.length === 0) && (
                <p className="text-slate-400">No positive trends in this window.</p>
              )}
            </div>
          </div>
          <div className="rounded-xl border border-cyan-500/30 bg-cyan-950/20 p-3">
            <p className="font-bold text-cyan-300">Top Negative Trends (FDR-corrected)</p>
            <div className="mt-1.5 space-y-1">
              {(trendMap.opposite_trends?.top_negative || []).slice(0, 3).map((reg) => (
                <button
                  key={reg.region_id}
                  type="button"
                  onClick={() => onSelectRegion?.(reg)}
                  className="flex w-full items-center justify-between rounded-lg px-2 py-1 text-left transition hover:bg-cyan-900/30"
                >
                  <span className="font-medium text-slate-100">{reg.name}</span>
                  <span className="font-mono text-cyan-300">
                    {reg.slope_per_year.toFixed(4)} {trendMap.unit}/yr (q={reg.q_value.toFixed(3)})
                  </span>
                </button>
              ))}
              {(!trendMap.opposite_trends?.top_negative || trendMap.opposite_trends.top_negative.length === 0) && (
                <p className="text-slate-400">No negative trends in this window.</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Informative Coordinate & Regional Comparison Footer */}
      <div className="grid grid-cols-1 gap-2.5 border-t border-slate-800 bg-slate-950/80 px-4 py-3 text-xs sm:grid-cols-2">
        {/* Region A Profile */}
        <div className="flex flex-col gap-1 rounded-xl border border-slate-800 bg-slate-900/70 p-3">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 font-bold text-cyan-300">
              <MapPin className="h-3.5 w-3.5" />
              Primary Investigation Site (Marker A)
            </span>
            <span
              className="rounded-full px-2 py-0.5 text-xs font-semibold"
              style={{
                backgroundColor: `${colorA.hex}22`,
                color: colorA.hex,
                border: `1px solid ${colorA.hex}44`,
              }}
            >
              {colorA.label}
            </span>
          </div>
          {pointA ? (
            <>
              <p className="font-semibold text-white">{pointA.name}</p>
              <p className="font-mono text-xs text-slate-400">
                Coords: {pointA.lat >= 0 ? `${pointA.lat.toFixed(2)}°N` : `${Math.abs(pointA.lat).toFixed(2)}°S`},{" "}
                {pointA.lon >= 0 ? `${pointA.lon.toFixed(2)}°E` : `${Math.abs(pointA.lon).toFixed(2)}°W`}
                {boxA && (
                  <span>
                    {" "}
                    · Grid Cell [{boxA.south.toFixed(2)}°..{boxA.north.toFixed(2)}°N, {boxA.west.toFixed(2)}°..
                    {boxA.east.toFixed(2)}°E]
                  </span>
                )}
              </p>
              {primaryStats && (
                <p className="text-xs text-slate-300">
                  Rate:{" "}
                  <strong className="font-mono text-cyan-200">
                    {primaryStats.sens_slope_per_decade >= 0 ? "+" : ""}
                    {primaryStats.sens_slope_per_decade}/decade
                  </strong>{" "}
                  · Mann-Kendall p ={" "}
                  <strong className="font-mono text-slate-200">
                    {primaryStats.p_value < 0.0001 ? "< 0.0001" : primaryStats.p_value.toFixed(4)}
                  </strong>
                </p>
              )}
            </>
          ) : (
            <p className="text-xs text-slate-400">Click on the map to place Marker A.</p>
          )}
        </div>

        {/* Region B Profile */}
        <div className="flex flex-col gap-1 rounded-xl border border-slate-800 bg-slate-900/70 p-3">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 font-bold text-indigo-300">
              <Radio className="h-3.5 w-3.5" />
              Teleconnection Comparison Site (Marker B)
            </span>
            <span
              className="rounded-full px-2 py-0.5 text-xs font-semibold"
              style={{
                backgroundColor: pointB ? `${colorB.hex}22` : "#33415522",
                color: pointB ? colorB.hex : "#94a3b8",
                border: `1px solid ${pointB ? colorB.hex : "#334155"}44`,
              }}
            >
              {pointB ? colorB.label : "Inactive"}
            </span>
          </div>
          {pointB ? (
            <>
              <p className="font-semibold text-white">{pointB.name}</p>
              <p className="font-mono text-xs text-slate-400">
                Coords: {pointB.lat >= 0 ? `${pointB.lat.toFixed(2)}°N` : `${Math.abs(pointB.lat).toFixed(2)}°S`},{" "}
                {pointB.lon >= 0 ? `${pointB.lon.toFixed(2)}°E` : `${Math.abs(pointB.lon).toFixed(2)}°W`}
                {boxB && (
                  <span>
                    {" "}
                    · Grid Cell [{boxB.south.toFixed(2)}°..{boxB.north.toFixed(2)}°N, {boxB.west.toFixed(2)}°..
                    {boxB.east.toFixed(2)}°E]
                  </span>
                )}
              </p>
              {teleconnection && (
                <p className="text-xs text-slate-300">
                  Rate:{" "}
                  <strong className="font-mono text-indigo-200">
                    {(teleconnection.comparison_sens_slope_per_decade ?? 0) >= 0 ? "+" : ""}
                    {teleconnection.comparison_sens_slope_per_decade ?? "0"}/decade
                  </strong>{" "}
                  · Correlation r ={" "}
                  <strong className="font-mono text-white">
                    {teleconnection.cross_correlation_r !== null && teleconnection.cross_correlation_r !== undefined
                      ? teleconnection.cross_correlation_r.toFixed(3)
                      : "N/A"}
                  </strong>
                </p>
              )}
            </>
          ) : (
            <div className="flex flex-col gap-1 text-xs text-slate-400">
              <p>Compare teleconnections across distant Earth systems.</p>
              <button
                type="button"
                onClick={() => onChangeActiveTarget("B")}
                className="mt-0.5 inline-flex w-fit items-center gap-1 rounded bg-indigo-500/20 px-2 py-0.5 text-xs font-semibold text-indigo-300 hover:bg-indigo-500/30"
              >
                Click here then select a point on the globe
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
