/**
 * Supabase email links (verification, password recovery) land back on the app
 * with their result in the URL: tokens in the fragment on success, or
 * error / error_code / error_description on failure.
 */
export function readAuthRedirect(location) {
  const params = new URLSearchParams(location.hash.replace(/^#/, ""));
  new URLSearchParams(location.search).forEach((value, key) => {
    if (!params.has(key)) params.set(key, value);
  });

  const hasSession = params.has("access_token");
  const errorCode = params.get("error_code") || params.get("error");
  if (!hasSession && !errorCode) return null;

  return {
    pathname: location.pathname,
    type: params.get("type"),
    hasSession,
    errorCode,
  };
}
