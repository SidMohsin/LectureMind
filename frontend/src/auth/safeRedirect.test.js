import { describe, expect, it } from "vitest";
import { safeAppPath } from "./safeRedirect";

const BACKSLASH = String.fromCharCode(92);

describe("safeAppPath", () => {
  it("keeps same-app paths with their query", () => {
    expect(safeAppPath("/lectures/abc", "?t=30")).toBe("/lectures/abc?t=30");
    expect(safeAppPath("/library")).toBe("/library");
  });

  it("rejects anything that could leave the app", () => {
    const unsafe = [
      "//evil.example",
      `/${BACKSLASH}evil.example`,
      `/${BACKSLASH}/evil.example`,
      "https://evil.example",
      "evil",
      "",
      null,
      `/a${BACKSLASH}b`,
      `/x${String.fromCharCode(0)}y`,
    ];
    for (const path of unsafe) {
      expect(safeAppPath(path)).toBe("/dashboard");
    }
    expect(safeAppPath("/library", `?q=${BACKSLASH}evil`)).toBe("/library");
  });
});
