/**
 * Pure helpers that relate lecture time to transcript segments, chapters and chunk
 * citations. Kept free of React so they can be tested directly.
 */

/** "02:14", or "1:02:14" past an hour (lecture timestamps, always zero-padded). */
export function formatClock(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const hours = Math.floor(total / 3600);
  const minutes = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const secs = String(total % 60).padStart(2, "0");
  return hours > 0 ? `${hours}:${minutes}:${secs}` : `${minutes}:${secs}`;
}

/**
 * Index of the item playing at `time`: the last one that started at or before it.
 * Items must be sorted by `startKey`. Returns -1 before the first item.
 */
export function findActiveIndex(items, time, startKey = "start") {
  let low = 0;
  let high = items.length - 1;
  let found = -1;
  while (low <= high) {
    const middle = (low + high) >> 1;
    if (items[middle][startKey] <= time) {
      found = middle;
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }
  return found;
}

/** Index of the chapter that contains `time` (chapters are contiguous and ordered). */
export function findChapterIndex(chapters, time) {
  const index = findActiveIndex(chapters, time, "start_seconds");
  return index === -1 && chapters.length ? 0 : index;
}

/** Map of chunk sequence → {start, end}, for turning chunk citations into timestamps. */
export function chunkTimeMap(chunks) {
  return new Map((chunks || []).map((chunk) => [chunk.sequence, chunk]));
}

/** Start time of the earliest cited chunk, or null when none of the citations is known. */
export function citationStart(chunkRefs, chunkMap) {
  const starts = (chunkRefs || []).map((ref) => chunkMap.get(ref)?.start).filter((start) => start !== undefined);
  return starts.length ? Math.min(...starts) : null;
}

/** Case-insensitive search: indices of segments whose text contains the query. */
export function searchSegments(segments, query) {
  const needle = query.trim().toLowerCase();
  if (needle.length < 2) return [];
  const matches = [];
  segments.forEach((segment, index) => {
    if (segment.text.toLowerCase().includes(needle)) matches.push(index);
  });
  return matches;
}

/** Split text around case-insensitive occurrences of the query, for highlighting. */
export function highlightParts(text, query) {
  const needle = query.trim();
  if (needle.length < 2) return [{ text, match: false }];
  const lower = text.toLowerCase();
  const target = needle.toLowerCase();
  const parts = [];
  let cursor = 0;
  let index = lower.indexOf(target);
  while (index !== -1) {
    if (index > cursor) parts.push({ text: text.slice(cursor, index), match: false });
    parts.push({ text: text.slice(index, index + needle.length), match: true });
    cursor = index + needle.length;
    index = lower.indexOf(target, cursor);
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor), match: false });
  return parts;
}
