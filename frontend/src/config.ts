const rawApiBaseUrl = (
  (import.meta as unknown as { env?: Record<string, string | undefined> }).env?.VITE_API_BASE_URL ||
  "http://localhost:8000"
).trim();

export const API_BASE_URL = rawApiBaseUrl.replace(/\/+$/, "");

export const STATISTICAL_ALPHA = 0.05;

export const INDIA_BOUNDS = {
  latMin: 6.0,
  latMax: 37.5,
  lonMin: 68.0,
  lonMax: 97.5,
  maxBounds: [
    [4.5, 65.0],
    [39.0, 100.0],
  ] as [[number, number], [number, number]],
  center: [22.5, 82.0] as [number, number],
};

export const FREE_MAP_TILES = {
  dark: {
    key: "osm-dark",
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    providerBadge: "OpenStreetMap (India Dark)",
    isOsmDark: true,
  },
  terrain: {
    key: "topo-free",
    url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    attribution: "&copy; OpenTopoMap &copy; OpenStreetMap contributors",
    providerBadge: "OpenTopoMap",
    isOsmDark: false,
  },
  satellite: {
    key: "esri-sat",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "Tiles &copy; Esri &mdash; Source: Esri, NASA, USGS",
    providerBadge: "Esri World Imagery",
    isOsmDark: false,
  },
} as const;
