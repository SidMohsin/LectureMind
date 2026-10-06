import { useEffect } from "react";
import { Outlet, ScrollRestoration, useLocation, useNavigationType } from "react-router-dom";

// Last scroll position of each history entry (keyed by location.key).
const positions = new Map();
const RESTORE_FOR_MS = 3000;

/**
 * ScrollRestoration restores Back/Forward positions once, on the first render. Our
 * pages load their data after that, so the page can still be too short to reach the
 * old position. This keeps trying while the content grows (up to 3 s) and stops as
 * soon as the reader scrolls, taps or types themselves.
 */
function useRestoreAfterLoad() {
  const location = useLocation();
  const navigationType = useNavigationType();

  useEffect(() => {
    const key = location.key;
    const remember = () => positions.set(key, window.scrollY);
    window.addEventListener("scroll", remember, { passive: true });
    return () => window.removeEventListener("scroll", remember);
  }, [location.key]);

  useEffect(() => {
    if (navigationType !== "POP") return undefined;
    const target = positions.get(location.key);
    if (!target) return undefined;

    let done = false;
    let frame = 0;
    const stop = () => {
      done = true;
      cancelAnimationFrame(frame);
    };
    const userEvents = ["wheel", "touchstart", "keydown", "mousedown"];
    userEvents.forEach((name) => window.addEventListener(name, stop, { passive: true, once: true }));
    const started = performance.now();
    const tick = () => {
      if (done) return;
      if (Math.abs(window.scrollY - target) <= 2) return stop();
      const reachable = document.documentElement.scrollHeight - window.innerHeight;
      if (reachable >= target - 2) window.scrollTo(0, target);
      if (performance.now() - started < RESTORE_FOR_MS) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => {
      stop();
      userEvents.forEach((name) => window.removeEventListener(name, stop));
    };
  }, [location.key, navigationType]);
}

/**
 * Wraps every route. ScrollRestoration makes a single-page app scroll like normal
 * pages: opening a page starts at the top, and Back/Forward return to where you were.
 * In-page URL updates (filters, sorting) opt out with `preventScrollReset`.
 */
export default function RootLayout() {
  useRestoreAfterLoad();
  return (
    <>
      <ScrollRestoration />
      <Outlet />
    </>
  );
}
