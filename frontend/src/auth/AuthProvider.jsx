import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { supabase } from "../lib/supabase";
import { getMe } from "../services/account";
import { AuthContext } from "./AuthContext";

/**
 * Single source of truth for the signed-in session.
 *
 * status: "loading" until Supabase has restored (or ruled out) a stored
 * session, then "authenticated" | "unauthenticated". Route guards wait on
 * "loading" so protected UI never flashes for signed-out users.
 *
 * signOutReason: "signed_out" after an explicit logout, "expired" when the
 * session ended on its own (refresh failed, token rejected by the API).
 */
export default function AuthProvider({ children }) {
  const [status, setStatus] = useState("loading");
  const [session, setSession] = useState(null);
  const [profile, setProfile] = useState(null);
  const [signOutReason, setSignOutReason] = useState(null);
  const hadSession = useRef(false);
  const signingOut = useRef(false);

  useEffect(() => {
    // Only synchronous state updates here: awaiting Supabase calls inside this
    // callback can deadlock the client's internal auth lock.
    const { data } = supabase.auth.onAuthStateChange((event, nextSession) => {
      if (nextSession) {
        setSignOutReason(null);
      } else if (hadSession.current) {
        setSignOutReason(signingOut.current ? "signed_out" : "expired");
      }
      signingOut.current = false;
      hadSession.current = Boolean(nextSession);
      setSession(nextSession);
      setStatus(nextSession ? "authenticated" : "unauthenticated");
    });
    return () => data.subscription.unsubscribe();
  }, []);

  const userId = session?.user?.id;

  useEffect(() => {
    setProfile(null);
    if (!userId) return undefined;

    const controller = new AbortController();
    getMe({ signal: controller.signal })
      .then((me) => {
        if (!controller.signal.aborted) setProfile(me);
      })
      .catch((error) => {
        // Identity still comes from the session; the shell falls back to it.
        if (error.name !== "AbortError") console.warn("Could not load profile:", error.message);
      });
    return () => controller.abort();
  }, [userId]);

  // scope "global" also revokes the user's sessions on every other device.
  const signOut = useCallback(async ({ scope } = {}) => {
    signingOut.current = true;
    const { error } = await supabase.auth.signOut(scope ? { scope } : undefined);
    // If the server couldn't be reached, still end the session on this device.
    if (error) await supabase.auth.signOut({ scope: "local" });
  }, []);

  const value = useMemo(
    () => ({
      status,
      session,
      user: session?.user ?? null,
      profile,
      signOutReason,
      signOut,
    }),
    [status, session, profile, signOutReason, signOut]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
