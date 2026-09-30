import { createClient } from "@supabase/supabase-js";
import { readAuthRedirect } from "../auth/authRedirect";

const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

export const isSupabaseConfigured = Boolean(url && anonKey);

// Read before createClient(): the client consumes the URL fragment on startup.
export const initialAuthRedirect = readAuthRedirect(window.location);

// A failed email link carries nothing the client can use; drop it from the URL
// so a refresh doesn't replay the error. Successful links are left for the
// client to turn into a session.
if (initialAuthRedirect?.errorCode) {
  window.history.replaceState(window.history.state, "", window.location.pathname);
}

export const supabase = isSupabaseConfigured
  ? createClient(url, anonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
        flowType: "implicit",
      },
    })
  : null;

export function authRedirectFor(pathname) {
  return initialAuthRedirect?.pathname === pathname ? initialAuthRedirect : null;
}
