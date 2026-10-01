import { describe, expect, it } from "vitest";
import {
  chunkTimeMap,
  citationStart,
  findActiveIndex,
  findChapterIndex,
  formatClock,
  highlightParts,
  searchSegments,
} from "./timeline";

const segments = [
  { start: 3, end: 6, text: "Welcome to CS229 Machine Learning." },
  { start: 6, end: 9, text: "Some of you know this class." },
  { start: 9, end: 12, text: "Machine learning is everywhere." },
];

describe("timeline helpers", () => {
  it("formats lecture timestamps", () => {
    expect(formatClock(0)).toBe("00:00");
    expect(formatClock(134.9)).toBe("02:14");
    expect(formatClock(4274)).toBe("1:11:14");
  });

  it("finds the segment playing at a time", () => {
    expect(findActiveIndex(segments, 0)).toBe(-1); // before the first segment
    expect(findActiveIndex(segments, 3)).toBe(0);
    expect(findActiveIndex(segments, 8.9)).toBe(1);
    expect(findActiveIndex(segments, 500)).toBe(2);
  });

  it("finds the current chapter, defaulting to the first", () => {
    const chapters = [{ start_seconds: 3 }, { start_seconds: 357 }];
    expect(findChapterIndex(chapters, 0)).toBe(0);
    expect(findChapterIndex(chapters, 400)).toBe(1);
  });

  it("maps chunk citations to the earliest cited timestamp", () => {
    const map = chunkTimeMap([
      { sequence: 4, start: 240, end: 300 },
      { sequence: 2, start: 120, end: 180 },
    ]);
    expect(citationStart([4, 2], map)).toBe(120);
    expect(citationStart([99], map)).toBeNull();
    expect(citationStart([], map)).toBeNull();
  });

  it("finds and highlights matches case-insensitively", () => {
    expect(searchSegments(segments, "machine LEARNING")).toEqual([0, 2]);
    expect(searchSegments(segments, "m")).toEqual([]); // too short to search
    expect(highlightParts("Machine learning, machine.", "machine")).toEqual([
      { text: "Machine", match: true },
      { text: " learning, ", match: false },
      { text: "machine", match: true },
      { text: ".", match: false },
    ]);
  });
});
