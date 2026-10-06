/** Text helpers for displaying generated lecture content. */

/**
 * The summary is often one long block. Keep the model's own paragraph breaks; a
 * single long paragraph is split into groups of three sentences so it reads easily.
 */
export function readableParagraphs(summary, sentencesPerParagraph = 3) {
  const blocks = summary.split(/\n\s*\n/).map((text) => text.trim()).filter(Boolean);
  if (blocks.length !== 1 || blocks[0].length < 420) return blocks;
  const sentences = blocks[0].split(/(?<=[.!?])\s+(?=[A-Z0-9“"(])/);
  const grouped = [];
  for (let index = 0; index < sentences.length; index += sentencesPerParagraph) {
    grouped.push(sentences.slice(index, index + sentencesPerParagraph).join(" "));
  }
  return grouped;
}

const FILLERS = /(^|[\s,.;:!?(])(?:uh|um|uhm|erm|hmm)(?=[\s,.;:!?)]|$)[,.]?/gi;
// A word cut off by a hyphen and a space ("I- I think", "It- you know") is a false
// start; hyphenated words ("non-linear") have no space and are kept.
const STUTTER = /\b[A-Za-z']+-\s+(?=[A-Za-z])/g;

/**
 * Display-only tidy-up of a verbatim transcript passage: drops filler words
 * ("uh", "um") and false starts ("I- I think" -> "I think"). The stored text is
 * unchanged; this only makes search results easier to read.
 */
export function tidyTranscript(text) {
  return text
    .replace(FILLERS, "$1")
    .replace(STUTTER, "")
    .replace(/\s+([,.;:!?])/g, "$1")
    .replace(/([,;:])(?:\s*[,;:])+/g, "$1")
    .replace(/^[\s,.;:]+/, "")
    .replace(/\s{2,}/g, " ")
    .trim()
    .replace(/^./, (first) => first.toUpperCase());
}
