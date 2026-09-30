import { useCallback, useEffect, useState } from "react";

/**
 * Loads data for a page and exposes { status, data, error, reload }.
 * status: "loading" | "ready" | "error". Stale requests are aborted when the
 * inputs change, so an old response can never overwrite a newer one.
 */
export function useAsyncData(load, deps) {
  const [state, setState] = useState({ status: "loading", data: null, error: null });
  const [attempt, setAttempt] = useState(0);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(load, deps);

  useEffect(() => {
    const controller = new AbortController();
    setState((current) => ({ status: "loading", data: current.data, error: null }));
    run({ signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) setState({ status: "ready", data, error: null });
      })
      .catch((error) => {
        if (!controller.signal.aborted && error.name !== "AbortError") {
          setState({ status: "error", data: null, error });
        }
      });
    return () => controller.abort();
  }, [run, attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  return { ...state, reload };
}
