import { useEffect, useState } from "react";
import { API_BASE_URL } from "./config";

const COLD_START_DELAY_MS = 4000;

function isBackendApiRequest(input: RequestInfo | URL): boolean {
  const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  return (API_BASE_URL && url.startsWith(API_BASE_URL)) || url.includes("/api/");
}

/**
 * Monitors in-flight backend API requests and returns true whenever
 * any backend call has been waiting longer than 4 seconds (e.g. Render cold start).
 */
export function useColdStartStatus(): boolean {
  const [isColdStartWaiting, setIsColdStartWaiting] = useState(false);

  useEffect(() => {
    const originalFetch = window.fetch.bind(window);
    let activeCount = 0;
    let timerId: number | null = null;

    const clearTimer = () => {
      if (timerId !== null) {
        window.clearTimeout(timerId);
        timerId = null;
      }
    };

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      if (!isBackendApiRequest(input)) {
        return originalFetch(input, init);
      }

      activeCount += 1;
      if (activeCount === 1 && timerId === null) {
        timerId = window.setTimeout(() => {
          if (activeCount > 0) {
            setIsColdStartWaiting(true);
          }
        }, COLD_START_DELAY_MS);
      }

      try {
        return await originalFetch(input, init);
      } finally {
        activeCount = Math.max(0, activeCount - 1);
        if (activeCount === 0) {
          clearTimer();
          setIsColdStartWaiting(false);
        }
      }
    };

    return () => {
      clearTimer();
      window.fetch = originalFetch;
    };
  }, []);

  return isColdStartWaiting;
}
