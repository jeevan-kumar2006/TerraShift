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
import { Crosshair, ArrowLeftRight, Trash2, Radio, KeyRound, Globe, Layers } from "lucide-react";
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
): { hex: string; label: string } {
  if (slopePerYear === null || slopePerYear === undefined) {
    return { hex: "#94a3b8", label: "Pending analysis" };
  }
  if (!isSignificant) {
    return { hex: "#facc15", label: "Insignificant / Noise" };
  }
  const code = parameter.toUpperCase();
  if (code === "T2M") {
    return slopePerYear >= 0
      ? { hex: "#fb7185", label: "Significant Warming" }
      : { hex: "#38bdf8", label: "Significant Cooling" };
  }
  if (code === "PS") {
    return slopePerYear >= 0
      ? { hex: "#818cf8", label: "Rising Pressure" }
      : { hex: "#fbbf24", label: "Falling Pressure" };
  }
  return slopePerYear >= 0
    ? { hex: "#2dd4bf", label: "Significant Wetting" }
    : { hex: "#f59e0b", label: "Significant Drying" };
}

function createBadgeIcon(label: "A" | "B", colorHex: string, isActive: boolean): L.DivIcon {
  const ring = isActive
    ? `box-shadow: 0 0 0 4px rgba(34,211,238,0.35), 0 4px 14px rgba(0,0,0,0.65);`
    : `box-shadow: 0 4px 12px rgba(0,0,0,0.65);`;
  const html = `
    <div style="
      width: 30px;
      height: 30px;
      border-radius: 9999px;
      background: ${colorHex};
      border: 2.5px solid #020617;
      color: #020617;
      font-weight: 800;
      font-size: 13px;
      display: flex;
      align-items: center;
      justify-content: center;
      ${ring}
      transform: translate(-15px, -15px);
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
        providerBadge: "Satellite Imagery (Add Mapbox Key for Mapbox GL Tiles)",
      };
    }

    if (styleMode === "terrain") {
      return {
        key: "fallback-terrain",
        url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        attribution: "&copy; OpenTopoMap &copy; OpenStreetMap contributors",
        tileSize: 256,
        zoomOffset: 0,
        providerBadge: "Hydrology / Terrain",
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
      return { text: `Inverse Seesaw (r = ${rVal.toFixed(2)})`, cls: "border-rose-500/40 bg-rose-950/80 text-rose-200" };
    }
    if (rVal >= 0.25) {
      return { text: `Co-Moving (r = +${rVal.toFixed(2)})`, cls: "border-emerald-500/40 bg-emerald-950/80 text-emerald-200" };
    }
    return { text: `Weak Linear Link (r = ${rVal.toFixed(2)})`, cls: "border-slate-600/60 bg-slate-900/90 text-slate-200" };
  }, [teleconnection?.enabled, rVal]);

  return (
    <div className="relative flex flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/70 shadow-xl">
      {/* Top Overlay Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 bg-slate-900/95 px-4 py-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <Crosshair className="h-4 w-4 text-cyan-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Dual-Region Teleconnection Map
          </span>
          <span className="inline-flex items-center gap-1 rounded-full border border-cyan-500/30 bg-cyan-950/40 px-2 py-0.5 text-[10px] font-medium text-cyan-300">
            <Globe className="h-3 w-3" />
            {tileConfig.providerBadge}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {/* Mapbox Layer Switcher */}
          <div className="flex items-center rounded-lg border border-slate-800 bg-slate-950 p-0.5 text-[11px]">
            <Layers className="mx-1.5 h-3 w-3 text-slate-400" />
            {(["dark", "satellite", "terrain"] as MapStyleMode[]).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setStyleMode(m)}
                className={`rounded-md px-2 py-0.5 font-medium capitalize transition ${
                  styleMode === m
                    ? "bg-cyan-500 text-slate-950"
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
            className={`inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium transition ${
              useMapboxTiles
                ? "border border-emerald-500/40 bg-emerald-950/40 text-emerald-300"
                : "border border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700"
            }`}
          >
            <KeyRound className="h-3 w-3" />
            {useMapboxTiles ? "Mapbox Active" : "Mapbox Key"}
          </button>

          <button
            type="button"
            onClick={() => onChangeActiveTarget("A")}
            className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition ${
              activeTarget === "A"
                ? "bg-cyan-500/20 text-cyan-200 ring-1 ring-cyan-400/60"
                : "bg-slate-800 text-slate-400 hover:text-slate-200"
            }`}
          >
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: colorA.hex }}
            />
            Click sets Region A
          </button>

          <button
            type="button"
            onClick={() => onChangeActiveTarget("B")}
            className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition ${
              activeTarget === "B"
                ? "bg-indigo-500/25 text-indigo-200 ring-1 ring-indigo-400/60"
                : "bg-slate-800 text-slate-400 hover:text-slate-200"
            }`}
          >
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: colorB.hex }}
            />
            Click sets Region B
          </button>

          {pointA && pointB && (
            <button
              type="button"
              onClick={onSwapPoints}
              title="Swap Primary (A) and Comparison (B)"
              className="flex items-center gap-1 rounded-lg bg-slate-800 px-2 py-1 text-xs text-slate-300 transition hover:bg-slate-700"
            >
              <ArrowLeftRight className="h-3.5 w-3.5" />
              Swap
            </button>
          )}

          {pointB && (
            <button
              type="button"
              onClick={onClearPointB}
              title="Remove Comparison Region B"
              className="flex items-center gap-1 rounded-lg bg-slate-800 px-2 py-1 text-xs text-rose-300 transition hover:bg-rose-950/60"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Clear B
            </button>
          )}
        </div>
      </div>

      {/* Optional Mapbox API Token Bar */}
      {showTokenEditor && (
        <div className="border-b border-slate-800 bg-slate-950 px-4 py-2 text-xs">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-slate-300">
              Enter a Mapbox public token (<code className="text-cyan-300">pk.eyJ...</code>) or set{" "}
              <code className="text-cyan-300">VITE_MAPBOX_TOKEN</code> to enable Mapbox Static Tiles &amp; Reverse Geocoding:
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
                className="w-64 rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1 font-mono text-xs text-slate-100 outline-none focus:border-cyan-400"
              />
              <button
                type="button"
                onClick={handleSaveToken}
                className="rounded-lg bg-cyan-500 px-3 py-1 font-bold text-slate-950 hover:bg-cyan-400"
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

      {/* Map Canvas */}
      <div className={`relative h-[340px] w-full sm:h-[380px] ${(tileConfig as { isOsmDark?: boolean }).isOsmDark ? "osm-dark-tiles" : ""}`}>
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

          {/* MERRA-2 0.5 x 0.625 Grid Cell Bounding Boxes */}
          {boxA && (
            <Rectangle
              bounds={[
                [boxA.south, boxA.west],
                [boxA.north, boxA.east],
              ]}
              pathOptions={{ color: colorA.hex, weight: 1.5, fillOpacity: 0.16, dashArray: "3 3" }}
            />
          )}
          {boxB && (
            <Rectangle
              bounds={[
                [boxB.south, boxB.west],
                [boxB.north, boxB.east],
              ]}
              pathOptions={{ color: colorB.hex, weight: 1.5, fillOpacity: 0.16, dashArray: "3 3" }}
            />
          )}

          {/* Teleconnection Dashed Link */}
          {pointA && pointB && (
            <Polyline
              positions={[
                [pointA.lat, pointA.lon],
                [pointB.lat, pointB.lon],
              ]}
              pathOptions={{
                color: "#38bdf8",
                weight: 2,
                dashArray: "6 8",
                opacity: 0.85,
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
                  <p className="font-bold">Region A: {pointA.name}</p>
                  <p>
                    {pointA.lat.toFixed(2)}°, {pointA.lon.toFixed(2)}°
                  </p>
                  <p className="mt-1 font-medium">{colorA.label}</p>
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
                  <p className="font-bold">Region B: {pointB.name}</p>
                  <p>
                    {pointB.lat.toFixed(2)}°, {pointB.lon.toFixed(2)}°
                  </p>
                  <p className="mt-1 font-medium">{colorB.label}</p>
                </div>
              </Popup>
            </Marker>
          )}
        </MapContainer>

        {/* Floating Teleconnection Pill */}
        {teleBadge && (
          <div
            className={`pointer-events-none absolute right-3 top-3 z-[400] flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold backdrop-blur-md ${teleBadge.cls}`}
          >
            <Radio className="h-3.5 w-3.5" />
            {teleBadge.text}
          </div>
        )}

        {/* Map Legend */}
        <div className="pointer-events-none absolute bottom-3 left-3 z-[400] hidden flex-wrap items-center gap-2.5 rounded-lg border border-slate-700/80 bg-slate-950/85 px-2.5 py-1.5 text-[11px] text-slate-300 backdrop-blur-md sm:flex">
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-rose-400" /> Warming
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-sky-400" /> Cooling
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-teal-400" /> Wetting
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-amber-400" /> Drying
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-yellow-400" /> Insignificant
          </span>
        </div>
      </div>

      {/* Live Bounding-Box Coordinate Footer */}
      <div className="grid grid-cols-1 gap-2 border-t border-slate-800 bg-slate-950/70 px-4 py-2.5 text-xs sm:grid-cols-2">
        <div className="flex flex-col gap-0.5 rounded-lg border border-slate-800/80 bg-slate-900/60 px-3 py-2">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-cyan-300">
              Marker A · {pointA ? pointA.name : "Click map to select"}
            </span>
            <span className="text-[11px] font-medium" style={{ color: colorA.hex }}>
              {colorA.label}
            </span>
          </div>
          {pointA && boxA ? (
            <p className="font-mono text-[11px] text-slate-400">
              Pt ({pointA.lat.toFixed(2)}°, {pointA.lon.toFixed(2)}°) · Grid [{boxA.south.toFixed(2)}°..
              {boxA.north.toFixed(2)}°N, {boxA.west.toFixed(2)}°..{boxA.east.toFixed(2)}°E]
            </p>
          ) : (
            <p className="text-[11px] text-slate-500">No primary coordinates placed yet.</p>
          )}
        </div>

        <div className="flex flex-col gap-0.5 rounded-lg border border-slate-800/80 bg-slate-900/60 px-3 py-2">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-indigo-300">
              Marker B · {pointB ? pointB.name : "Optional comparison"}
            </span>
            <span className="text-[11px] font-medium" style={{ color: colorB.hex }}>
              {pointB ? colorB.label : "Inactive"}
            </span>
          </div>
          {pointB && boxB ? (
            <p className="font-mono text-[11px] text-slate-400">
              Pt ({pointB.lat.toFixed(2)}°, {pointB.lon.toFixed(2)}°) · Grid [{boxB.south.toFixed(2)}°..
              {boxB.north.toFixed(2)}°N, {boxB.west.toFixed(2)}°..{boxB.east.toFixed(2)}°E]
            </p>
          ) : (
            <p className="text-[11px] text-slate-500">
              Switch to &ldquo;Region B&rdquo; and click anywhere to compare teleconnections.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
