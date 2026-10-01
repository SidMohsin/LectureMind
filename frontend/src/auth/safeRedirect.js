/**
 * Only same-app paths may be used as a post-login destination: a single leading "/"
 * and no "//", backslashes or control characters, which browsers can turn into a
 * different origin (an open redirect). Anything else falls back to the dashboard.
 */
const BACKSLASH = String.fromCharCode(92);

function hasControlCharacters(value) {
  for (let index = 0; index < value.length; index += 1) {
    if (value.charCodeAt(index) < 32) return true;
  }
  return false;
}

export function safeAppPath(pathname, search = "", fallback = "/dashboard") {
  if (typeof pathname !== "string" || !pathname.startsWith("/") || pathname.startsWith("//")) return fallback;
  if (pathname.includes(BACKSLASH) || hasControlCharacters(pathname)) return fallback;
  const query =
    typeof search === "string" && search.startsWith("?") && !search.includes(BACKSLASH) && !hasControlCharacters(search)
      ? search
      : "";
  return `${pathname}${query}`;
}
