import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import TranscriptPanel from "./Workspace/TranscriptPanel";

const transcript = {
  language: "en",
  segments: [
    { sequence: 0, start: 0, end: 5, text: "Welcome to the course." },
    { sequence: 1, start: 5, end: 12, text: "Today we cover gradient descent." },
    { sequence: 2, start: 12, end: 20, text: "First, the learning rate." },
  ],
};

function mockScreen(phone) {
  vi.stubGlobal("matchMedia", (query) => ({
    matches: phone,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

afterEach(() => vi.unstubAllGlobals());

describe("Transcript on phones", () => {
  it("starts collapsed to the line being spoken and expands on request", () => {
    mockScreen(true);
    render(<TranscriptPanel transcript={transcript} currentTime={6} onSeek={() => {}} />);

    const toggle = screen.getByRole("button", { name: /Show transcript/ });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.getByText("Today we cover gradient descent.", { selector: ".transcript__now-text" })).toBeTruthy();
    expect(screen.getByText(/Now playing · 00:05/)).toBeTruthy();
    expect(document.getElementById("transcript-body").hidden).toBe(true);

    fireEvent.click(toggle);
    expect(document.getElementById("transcript-body").hidden).toBe(false);
    expect(screen.getByRole("button", { name: /Hide/ }).getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByPlaceholderText("Find in transcript…")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Hide/ }));
    expect(document.getElementById("transcript-body").hidden).toBe(true);
  });

  it("is always open on larger screens, with no toggle", () => {
    mockScreen(false);
    render(<TranscriptPanel transcript={transcript} currentTime={6} onSeek={() => {}} />);
    expect(screen.queryByRole("button", { name: /Show transcript/ })).toBeNull();
    expect(document.getElementById("transcript-body").hidden).toBe(false);
    expect(screen.getByText("3 segments · EN")).toBeTruthy();
  });
});
