import { describe, expect, it } from "vitest";
import { lecturePath, statusInfo } from "./lectureStatus";
import { parseTags, validateMediaFile, validateSourceUrl } from "./lectureInput";
import { formatDate, formatDuration, formatFileSize } from "../utils/format";

describe("statusInfo", () => {
  it("maps terminal states", () => {
    expect(statusInfo("READY")).toMatchObject({ group: "ready", tone: "success", label: "Ready" });
    expect(statusInfo("FAILED")).toMatchObject({ group: "failed", tone: "error" });
  });

  it("derives the stage number from the real lifecycle", () => {
    expect(statusInfo("CHUNKING")).toMatchObject({ group: "processing", stage: 5, totalStages: 8 });
    expect(statusInfo("QUEUED").stage).toBe(1);
    expect(statusInfo("UPLOADED").stage).toBeUndefined();
  });

  it("routes ready lectures to the workspace and others to processing details", () => {
    expect(lecturePath({ id: "a", status: "READY" })).toBe("/lectures/a");
    expect(lecturePath({ id: "a", status: "TRANSCRIBING" })).toBe("/lectures/a/processing");
    expect(lecturePath({ id: "a", status: "FAILED" })).toBe("/lectures/a/processing");
  });
});

describe("formatting", () => {
  it("formats durations like the approved screens", () => {
    expect(formatDuration(3522)).toBe("58:42");
    expect(formatDuration(4460)).toBe("1:14:20");
    expect(formatDuration(5)).toBe("0:05");
    expect(formatDuration(null)).toBeNull();
  });

  it("formats calendar dates without timezone drift", () => {
    expect(formatDate("2026-10-05")).toBe("Oct 5, 2026");
    expect(formatDate(null)).toBeNull();
  });

  it("formats file sizes", () => {
    expect(formatFileSize(684.2 * 1024 ** 2)).toBe("684.2 MB");
    expect(formatFileSize(2 * 1024 ** 3)).toBe("2.0 GB");
  });
});

describe("lecture input validation", () => {
  const file = (name, type, size = 1000) => ({ name, type, size });

  it("accepts supported media by type or extension", () => {
    expect(validateMediaFile(file("lecture.mp4", "video/mp4"), "video")).toBeNull();
    expect(validateMediaFile(file("talk.MKV", ""), "video")).toBeNull();
    expect(validateMediaFile(file("talk.m4a", "audio/x-m4a"), "audio")).toBeNull();
  });

  it("rejects wrong types, empty and oversized files", () => {
    expect(validateMediaFile(file("notes.pdf", "application/pdf"), "video")).toMatch(/isn't supported/);
    expect(validateMediaFile(file("clip.mp4", "video/mp4"), "audio")).toMatch(/isn't supported/);
    expect(validateMediaFile(file("a.mp3", "audio/mpeg", 0), "audio")).toMatch(/empty/);
    expect(validateMediaFile(file("a.mp3", "audio/mpeg", 501 * 1024 ** 2), "audio")).toMatch(/500.0 MB limit/);
  });

  it("validates supported source URLs", () => {
    expect(validateSourceUrl("https://www.youtube.com/watch?v=abc123")).toBeNull();
    expect(validateSourceUrl("https://youtu.be/abc123")).toBeNull();
    expect(validateSourceUrl("")).toMatch(/Enter a video URL/);
    expect(validateSourceUrl("youtube.com/watch?v=x")).toMatch(/complete URL/);
    expect(validateSourceUrl("https://vimeo.com/123")).toMatch(/Only YouTube/);
    expect(validateSourceUrl("https://www.youtube.com/@channel")).toMatch(/single video/);
    expect(validateSourceUrl("javascript:alert(1)")).toMatch(/web/);
  });

  it("parses tags, dropping blanks and duplicates", () => {
    expect(parseTags(" ML, Optimization,, ml ,KKT ")).toEqual(["ML", "Optimization", "KKT"]);
  });
});
