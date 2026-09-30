/**
 * What the Ingest Lecture page accepts. MIME types mirror the `lectures`
 * storage bucket's allow-list (supabase/migrations/..._lecture_media_storage.sql).
 */
import { formatFileSize } from "../utils/format";

const GB = 1024 ** 3;
const MB = 1024 ** 2;

export const INPUT_KINDS = {
  video: {
    label: "Video File",
    summary: "MP4, MOV <2GB",
    formats: "MP4, MOV, WebM, MKV",
    maxBytes: 2 * GB,
    extensions: [".mp4", ".mov", ".webm", ".mkv"],
    mimeTypes: ["video/mp4", "video/quicktime", "video/webm", "video/x-matroska"],
  },
  audio: {
    label: "Audio Recording",
    summary: "MP3, WAV <500MB",
    formats: "MP3, WAV, M4A, WebM, OGG",
    maxBytes: 500 * MB,
    extensions: [".mp3", ".wav", ".m4a", ".webm", ".ogg"],
    mimeTypes: ["audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp4", "audio/x-m4a", "audio/webm", "audio/ogg"],
  },
};

export function validateMediaFile(file, kind) {
  const rules = INPUT_KINDS[kind];
  const name = file.name.toLowerCase();
  const typeOk = rules.mimeTypes.includes(file.type) || rules.extensions.some((ext) => name.endsWith(ext));
  if (!typeOk) return `This file type isn't supported. Choose a ${rules.formats} file.`;
  if (file.size === 0) return "This file is empty.";
  if (file.size > rules.maxBytes) return `This file is larger than the ${formatFileSize(rules.maxBytes)} limit.`;
  return null;
}

// Only platforms the ingestion pipeline is designed to fetch from. Whether a
// specific video is accessible is checked when ingestion runs.
const SUPPORTED_HOSTS = ["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"];

export function validateSourceUrl(value) {
  const trimmed = value.trim();
  if (!trimmed) return "Enter a video URL.";
  let url;
  try {
    url = new URL(trimmed);
  } catch {
    return "Enter a complete URL, including https://.";
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") return "Enter a web (https://) URL.";
  if (!SUPPORTED_HOSTS.includes(url.hostname.toLowerCase())) return "Only YouTube links are supported right now.";
  const hasVideoId =
    url.hostname === "youtu.be" ? url.pathname.length > 1 : url.searchParams.has("v") || /^\/(shorts|live)\/.+/.test(url.pathname);
  if (!hasVideoId) return "This doesn't look like a link to a single video.";
  return null;
}

export function parseTags(value) {
  const seen = new Set();
  return value
    .split(",")
    .map((tag) => tag.trim())
    .filter((tag) => tag && !seen.has(tag.toLowerCase()) && seen.add(tag.toLowerCase()));
}
