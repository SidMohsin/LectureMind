/**
 * Lecture artwork.
 *
 * YouTube lectures use YouTube's public thumbnail image (served by YouTube, nothing
 * stored by us). Other lectures get a generated cover: a colour picked from the
 * subject and its initials, so the same subject always looks the same.
 */

const YOUTUBE_ID = /^[A-Za-z0-9_-]{11}$/;

export function youtubeId(url) {
  if (!url) return null;
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  const host = parsed.hostname.replace(/^www\.|^m\./, "");
  let id = null;
  if (host === "youtu.be") id = parsed.pathname.slice(1).split("/")[0];
  else if (host === "youtube.com" || host === "youtube-nocookie.com" || host === "music.youtube.com") {
    id = parsed.searchParams.get("v");
    const match = parsed.pathname.match(/^\/(?:embed|shorts|live|v)\/([^/?#]+)/);
    if (!id && match) id = match[1];
  }
  return id && YOUTUBE_ID.test(id) ? id : null;
}

/** 320x180 (16:9, no letterbox) - right size for list tiles. */
export function thumbnailUrl(lecture) {
  const id = lecture?.source_type === "url" ? youtubeId(lecture.source_url) : null;
  return id ? `https://i.ytimg.com/vi/${id}/mqdefault.jpg` : null;
}

const COVER_HUES = [222, 200, 262, 168, 18, 340, 140, 290];

export function coverStyle(seed = "") {
  let hash = 0;
  for (const char of seed) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  const hue = COVER_HUES[hash % COVER_HUES.length];
  return {
    background: `linear-gradient(135deg, hsl(${hue} 55% 34%) 0%, hsl(${(hue + 28) % 360} 60% 46%) 100%)`,
  };
}

export function coverInitials(lecture) {
  const source = (lecture?.subject || lecture?.title || "").trim();
  const words = source.split(/\s+/).filter(Boolean);
  if (words.length === 0) return "";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}
