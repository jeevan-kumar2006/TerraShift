import { useEffect, useMemo, useState } from "react";
import L from "leaflet";
import {
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
  KeyRound,
  Layers,
  MapPin,
  Radio,
  Trash2,
} from "lucide-react";
import type { BoundingBox, GeoPoint, SeriesStats, TeleconnectionSummary } from "./types";

type MapStyleMode = "dark" | "satellite" | "terrain";

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
}

const ENV_MAPBOX_TOKEN =
  ((import.meta as unknown as { env?: Record<string, string | undefined> }).env?.VITE_MAPBOX_TOKEN || "").trim();
const STORAGE_KEY = "terrashift_mapbox_token";

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

async function reverseGeocodeMapbox(lat: number, lon: number, token: string): Promise<string | undefined> {
  if (!token) return undefined;
  try {
    const url = `https://api.mapbox.com/geocoding/v5/mapbox.places/${lon},${lat}.json?types=place,region,country&limit=1&access_token=${encodeURIComponent(token)}`;
    const resp = await fetch(url);
    if (!resp.ok) return undefined;
    const data = await resp.json();
    const feat = data?.features?.[0];
    if (feat?.place_name) {
      return String(feat.place_name);
    }
  } catch {
    // ignore geocoding network errors and fall back to coordinates
  }
  return undefined;
}

function MapClickHandler({
  activeTarget,
  mapboxToken,
  onSelectPoint,
}: {
  activeTarget: "A" | "B";
  mapboxToken: string;
  onSelectPoint: (target: "A" | "B", lat: number, lon: number, resolvedName?: string) => void;
}) {
  useMapEvents({
    async click(e) {
      const wrapped = e.latlng.wrap();
      const lat = Number(wrapped.lat.toFixed(3));
      const lon = Number(wrapped.lng.toFixed(3));
      const resolvedName = await reverseGeocodeMapbox(lat, lon, mapboxToken);
      onSelectPoint(activeTarget, lat, lon, resolvedName);
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
      map.fitBounds(bounds.pad(0.35), { maxZoom: 5, animate: true, duration: 0.7 });
    } else if (pointA) {
      map.flyTo([pointA.lat, pointA.lon], 4, { duration: 0.7 });
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
}: SplitMapProps) {
  const [styleMode, setStyleMode] = useState<MapStyleMode>("dark");
  const [mapboxToken, setMapboxToken] = useState<string>(() => {
    if (ENV_MAPBOX_TOKEN && ENV_MAPBOX_TOKEN.startsWith("pk.")) return ENV_MAPBOX_TOKEN;
    try {
      const saved = localStorage.getItem(STORAGE_KEY) || "";
      return saved.startsWith("pk.") ? saved : "";
    } catch {
      return "";
    }
  });
  const [showTokenEditor, setShowTokenEditor] = useState<boolean>(false);
  const [tokenDraft, setTokenDraft] = useState<string>(mapboxToken);
  const [mapboxError, setMapboxError] = useState<boolean>(false);
  const [tokenValidationError, setTokenValidationError] = useState<string | null>(null);
  const [mobileLegendOpen, setMobileLegendOpen] = useState<boolean>(false);

  const useMapboxTiles = mapboxToken.trim().startsWith("pk.") && !mapboxError;

  const tileConfig = useMemo(() => {
    if (useMapboxTiles) {
      const styleId =
        styleMode === "satellite"
          ? "mapbox/satellite-streets-v12"
          : styleMode === "terrain"
            ? "mapbox/outdoors-v12"
            : "mapbox/dark-v11";
      return {
        key: `mb-${styleId}-${mapboxToken.slice(-6)}`,
        url: `https://api.mapbox.com/styles/v1/${styleId}/tiles/512/{z}/{x}/{y}@2x?access_token=${encodeURIComponent(
          mapboxToken.trim()
        )}`,
        attribution:
          '&copy; <a href="https://www.mapbox.com/about/maps/">Mapbox</a> &copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        tileSize: 512,
        zoomOffset: -1,
        providerBadge: `Mapbox (${styleMode})`,
      };
    }

    if (styleMode === "satellite") {
      return {
        key: "fallback-sat",
        url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attribution: "Tiles &copy; Esri &mdash; Source: Esri, NASA, USGS",
        tileSize: 256,
        zoomOffset: 0,
        providerBadge: "Satellite Imagery (Esri)",
      };
    }

    if (styleMode === "terrain") {
      return {
        key: "fallback-terrain",
        url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        attribution: "&copy; OpenTopoMap &copy; OpenStreetMap contributors",
        tileSize: 256,
        zoomOffset: 0,
        providerBadge: "Hydrology / Topo",
      };
    }

    return {
      key: "osm-dark",
      url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      tileSize: 256,
      zoomOffset: 0,
      providerBadge: "Leaflet + OpenStreetMap (Dark)",
      isOsmDark: true,
    };
  }, [mapboxToken, styleMode, useMapboxTiles]);

  const handleSaveToken = () => {
    const cleaned = tokenDraft.trim();
    if (cleaned && !cleaned.startsWith("pk.")) {
      setTokenValidationError(
        cleaned.startsWith("sk.")
          ? "Secret Mapbox tokens (sk.*) must never be used in the browser. Enter a public token starting with pk."
          : "Invalid token format: Mapbox browser tokens must start with pk."
      );
      return;
    }
    setTokenValidationError(null);
    setMapboxToken(cleaned);
    setMapboxError(false);
    try {
      if (cleaned) {
        localStorage.setItem(STORAGE_KEY, cleaned);
      } else {
        localStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      // ignore storage errors
    }
    setShowTokenEditor(false);
  };

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
          <span className="inline-flex items-center gap-1 rounded-full border border-cyan-500/30 bg-cyan-950/40 px-2.5 py-0.5 text-[10px] font-medium text-cyan-300">
            <Globe className="h-3 w-3" />
            {tileConfig.providerBadge}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Map Layer Switcher */}
          <div className="flex items-center rounded-lg border border-slate-800 bg-slate-950 p-0.5 text-[11px]">
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

          <button
            type="button"
            onClick={() => {
              setTokenDraft(mapboxToken);
              setShowTokenEditor((s) => !s);
            }}
            title="Configure Mapbox token for high-resolution vector and satellite tiles"
            className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] font-medium transition ${
              useMapboxTiles
                ? "border border-emerald-500/40 bg-emerald-950/40 text-emerald-300"
                : "border border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700"
            }`}
          >
            <KeyRound className="h-3 w-3" />
            {useMapboxTiles ? "Mapbox Active" : "Mapbox Key"}
          </button>

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

      {/* Optional Mapbox API Token Drawer */}
      {showTokenEditor && (
        <div className="border-b border-slate-800 bg-slate-950 px-4 py-2.5 text-xs">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-slate-300">
              Enter a Mapbox public token (<code className="text-cyan-300">pk.eyJ...</code>) or configure{" "}
              <code className="text-cyan-300">VITE_MAPBOX_TOKEN</code> in your environment:
            </span>
            <div className="flex items-center gap-2">
              <input
                type="password"
                value={tokenDraft}
                onChange={(e) => {
                  setTokenDraft(e.target.value);
                  if (tokenValidationError) setTokenValidationError(null);
                }}
                placeholder="pk.eyJ1Ijoi..."
                className="w-64 rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 font-mono text-xs text-slate-100 outline-none focus:border-cyan-400"
              />
              <button
                type="button"
                onClick={handleSaveToken}
                className="rounded-lg bg-cyan-500 px-3 py-1.5 font-bold text-slate-950 hover:bg-cyan-400"
              >
                Apply
              </button>
            </div>
          </div>
          {tokenValidationError && (
            <p className="mt-1.5 text-[11px] font-medium text-rose-400">{tokenValidationError}</p>
          )}
        </div>
      )}

      {/* Map Canvas with Leaflet */}
      <div
        className={`relative h-[340px] w-full sm:h-[400px] ${(tileConfig as { isOsmDark?: boolean }).isOsmDark ? "osm-dark-tiles" : ""}`}
      >
        <MapContainer
          center={[20, 0]}
          zoom={2}
          minZoom={2}
          maxZoom={12}
          worldCopyJump={true}
          className="h-full w-full"
        >
          <TileLayer
            key={tileConfig.key}
            attribution={tileConfig.attribution}
            url={tileConfig.url}
            tileSize={tileConfig.tileSize}
            zoomOffset={tileConfig.zoomOffset}
            eventHandlers={{
              tileerror() {
                if (useMapboxTiles) {
                  setMapboxError(true);
                }
              },
            }}
          />

          <MapClickHandler
            activeTarget={activeTarget}
            mapboxToken={useMapboxTiles ? mapboxToken : ""}
            onSelectPoint={onSelectPoint}
          />
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
                async dragend(e) {
                  const pos = e.target.getLatLng().wrap();
                  const lat = Number(pos.lat.toFixed(3));
                  const lon = Number(pos.lng.toFixed(3));
                  const resolvedName = await reverseGeocodeMapbox(
                    lat,
                    lon,
                    useMapboxTiles ? mapboxToken : ""
                  );
                  onSelectPoint("A", lat, lon, resolvedName);
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
                async dragend(e) {
                  const pos = e.target.getLatLng().wrap();
                  const lat = Number(pos.lat.toFixed(3));
                  const lon = Number(pos.lng.toFixed(3));
                  const resolvedName = await reverseGeocodeMapbox(
                    lat,
                    lon,
                    useMapboxTiles ? mapboxToken : ""
                  );
                  onSelectPoint("B", lat, lon, resolvedName);
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
        <div className="pointer-events-none absolute bottom-3 left-3 z-[400] hidden flex-col gap-1 rounded-xl border border-slate-700/80 bg-slate-950/90 p-2.5 text-[11px] text-slate-200 shadow-xl backdrop-blur-md sm:flex">
          <p className="font-bold uppercase tracking-wider text-slate-400 text-[10px]">
            Map Status Legend ({parameter.toUpperCase()})
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
              <p className="font-bold text-[10px] uppercase tracking-wider text-slate-400">
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
              className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
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
              <p className="font-mono text-[11px] text-slate-400">
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
                <p className="text-[11px] text-slate-300">
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
            <p className="text-[11px] text-slate-400">Click on the map to place Marker A.</p>
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
              className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
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
              <p className="font-mono text-[11px] text-slate-400">
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
                <p className="text-[11px] text-slate-300">
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
            <div className="flex flex-col gap-1 text-[11px] text-slate-400">
              <p>Compare teleconnections across distant Earth systems.</p>
              <button
                type="button"
                onClick={() => onChangeActiveTarget("B")}
                className="mt-0.5 inline-flex w-fit items-center gap-1 rounded bg-indigo-500/20 px-2 py-0.5 text-[11px] font-semibold text-indigo-300 hover:bg-indigo-500/30"
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
