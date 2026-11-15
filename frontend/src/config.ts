const rawApiBaseUrl =
  ((import.meta as unknown as { env?: Record<string, string | undefined> }).env?.VITE_API_BASE_URL ?? "").trim();

export const API_BASE_URL = rawApiBaseUrl.replace(/\/$/, "");
