"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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
  // Responses can arrive out of order (a changed path, an overlapping reload, a wait for a sleeping
  // server), so only the most recent request may update state.
  const latest = useRef(0);

  const load = useCallback(async () => {
    if (path === null) return;
    const request = ++latest.current;
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
      if (request !== latest.current) return;
      setData(result);
      setError(undefined);
    } catch (e) {
      if (request !== latest.current) return;
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (request === latest.current) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-mount is the intent
    void load();
  }, [load]);

  return { data, error, loading, reload: load };
}
