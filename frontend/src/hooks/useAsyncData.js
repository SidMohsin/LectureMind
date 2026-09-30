import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Loads data for a page and exposes { status, data, error, reload }.
 * status: "loading" | "ready" | "error". Stale requests are aborted when the
 * inputs change, so an old response can never overwrite a newer one.
 *
 * `poll: { intervalMs, while: (data) => boolean }` re-fetches quietly (no
 * loading state) only while the condition holds, e.g. while a job is running.
 */
export function useAsyncData(load, deps, { poll } = {}) {
  const [state, setState] = useState({ status: "loading", data: null, error: null });
  const [attempt, setAttempt] = useState(0);
  const quiet = useRef(false);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(load, deps);

  useEffect(() => {
    const controller = new AbortController();
    const silent = quiet.current;
    quiet.current = false;
    if (!silent) setState((current) => ({ status: "loading", data: current.data, error: null }));
    run({ signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) setState({ status: "ready", data, error: null });
      })
      .catch((error) => {
        if (controller.signal.aborted || error.name === "AbortError") return;
        // A failed background refresh keeps showing the last good data.
        setState((current) => (silent && current.data ? current : { status: "error", data: null, error }));
      });
    return () => controller.abort();
  }, [run, attempt]);

  const pollWhile = poll?.while;
  const pollInterval = poll?.intervalMs;
  useEffect(() => {
    if (!pollInterval || state.status !== "ready" || !pollWhile?.(state.data)) return undefined;
    const timer = setTimeout(() => {
      quiet.current = true;
      setAttempt((n) => n + 1);
    }, pollInterval);
    return () => clearTimeout(timer);
  }, [state, pollInterval, pollWhile]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  return { ...state, reload };
}
