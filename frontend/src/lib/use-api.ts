"use client";

import { useCallback, useEffect, useState } from "react";
import { api, isUnavailable, waitForServer } from "./api";

export interface Resource<T> {
  data: T | undefined;
  error: string | undefined;
  loading: boolean;
  reload: () => Promise<void>;
}

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
