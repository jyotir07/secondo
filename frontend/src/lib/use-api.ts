"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "./api";

export interface Resource<T> {
  data: T | undefined;
  error: string | undefined;
  loading: boolean;
  reload: () => Promise<void>;
}

// The hosted demo's API sleeps when idle and takes about a minute to start. Until then requests
// fail with a dropped connection or a 5xx, so GETs wait for the server instead of failing at once.
const WAKE_TIMEOUT_MS = 90_000;
let waking: Promise<boolean> | undefined;

/** Polls /health until the server answers; false if it never does. Concurrent callers share one poll. */
function waitForServer(): Promise<boolean> {
  waking ??= (async () => {
    const deadline = Date.now() + WAKE_TIMEOUT_MS;
    for (let delay = 1_000; Date.now() < deadline; delay = Math.min(delay * 2, 8_000)) {
      try {
        await api("/health");
        return true;
      } catch {
        await new Promise((resolve) => setTimeout(resolve, delay));
      }
    }
    return false;
  })().finally(() => {
    waking = undefined;
  });
  return waking;
}

const isUnavailable = (e: unknown) => e instanceof ApiError && (e.status === 0 || e.status >= 500);

/** Fetches a GET endpoint on mount and whenever `path` changes. Pass null to skip. */
export function useApi<T>(path: string | null): Resource<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(path !== null);

  const load = useCallback(async () => {
    if (path === null) return;
    setLoading(true);
    try {
      let result: T;
      try {
        result = await api<T>(path);
      } catch (e) {
        // A server that is up but erroring answers /health at once, so a real 5xx surfaces after one retry.
        if (!isUnavailable(e) || !(await waitForServer())) throw e;
        result = await api<T>(path);
      }
      setData(result);
      setError(undefined);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-mount is the intent
    void load();
  }, [load]);

  return { data, error, loading, reload: load };
}
