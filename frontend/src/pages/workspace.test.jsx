import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ToastProvider } from "../components/ui/Toast";

const workspaceApi = vi.hoisted(() => ({
  getWorkspace: vi.fn(),
  getMedia: vi.fn(),
  listQuestions: vi.fn(),
  askQuestion: vi.fn(),
}));
vi.mock("../services/workspace", () => workspaceApi);

const { default: Workspace } = await import("./Workspace");

const LECTURE_ID = "5b3d0c3e-0000-4000-8000-000000000001";

const lecture = (overrides = {}) => ({
  id: LECTURE_ID,
  title: "Machine Learning Lecture 1",
  subject: "ML",
  topic: null,
  instructor: "Andrew Ng",
  lecture_date: null,
  tags: [],
  source_type: "url",
  source_url: "https://www.youtube.com/watch?v=abc",
  status: "READY",
  duration_seconds: 600,
  created_at: "2026-10-01T10:00:00Z",
  updated_at: "2026-10-01T10:00:00Z",
  ...overrides,
});

const workspaceData = (overrides = {}) => ({
  lecture: lecture(),
  transcript: {
    language: "en",
    model: "faster-whisper/small",
    segments: [
      { sequence: 0, start: 3, end: 6, text: "Welcome to machine learning." },
      { sequence: 1, start: 6, end: 9, text: "Supervised learning uses labels." },
      { sequence: 2, start: 130, end: 140, text: "Gradient descent and the learning rate." },
    ],
  },
  chapters: [
    { sequence: 0, title: "Course overview", description: "Logistics.", start_seconds: 3, end_seconds: 125, first_chunk: 0, last_chunk: 1 },
    { sequence: 1, title: "Gradient descent", description: null, start_seconds: 125, end_seconds: 600, first_chunk: 2, last_chunk: 3 },
  ],
  intelligence: {
    summary: "The lecture introduces machine learning.\n\nIt then covers gradient descent.",
    topics: [{ name: "Optimization", subtopics: ["Learning rate"], chunks: [2] }],
    key_concepts: [{ name: "Supervised learning", explanation: "Learning from labelled data.", chunks: [1] }],
    definitions: [{ term: "learning rate", definition: "The step size.", chunks: [3] }],
    keywords: ["gradient descent"],
    important_points: [{ point: "Labels are required.", chunks: [1] }],
    examples: [],
    model: "openai/gpt-oss-20b",
    prompt_version: "lecture-intelligence/v3",
  },
  chunks: [
    { sequence: 0, start: 3, end: 60 },
    { sequence: 1, start: 55, end: 125 },
    { sequence: 2, start: 120, end: 200 },
    { sequence: 3, start: 195, end: 260 },
  ],
  ...overrides,
});

const answered = {
  id: "q-1",
  question: "What is supervised learning?",
  outcome: "answered",
  answer: "It learns from labelled examples.",
  sources: [
    { number: 1, chunk_id: "c1", sequence: 1, start_seconds: 55, end_seconds: 125, similarity: 0.8, text: "Supervised learning uses labels and examples.", cited: true },
    { number: 2, chunk_id: "c2", sequence: 2, start_seconds: 120, end_seconds: 200, similarity: 0.7, text: "Gradient descent text.", cited: false },
  ],
  latency_ms: 1400,
  created_at: "2026-10-01T10:05:00Z",
};

const insufficient = {
  id: "q-2",
  question: "What is the capital of France?",
  outcome: "insufficient_evidence",
  answer: "I couldn't find enough information in this lecture to answer that reliably.",
  sources: [],
  latency_ms: 80,
  created_at: "2026-10-01T10:06:00Z",
};

// jsdom has no media pipeline; give media elements a controllable clock.
beforeAll(() => {
  Object.defineProperty(HTMLMediaElement.prototype, "currentTime", {
    configurable: true,
    get() {
      return this._time || 0;
    },
    set(value) {
      this._time = value;
    },
  });
  Object.defineProperty(HTMLMediaElement.prototype, "duration", { configurable: true, get: () => 600 });
  Object.defineProperty(HTMLMediaElement.prototype, "readyState", { configurable: true, get: () => 4 });
  HTMLMediaElement.prototype.play = vi.fn(() => Promise.resolve());
  HTMLMediaElement.prototype.pause = vi.fn();
});

beforeEach(() => {
  vi.clearAllMocks();
  workspaceApi.getWorkspace.mockResolvedValue(workspaceData());
  workspaceApi.getMedia.mockResolvedValue({ kind: "audio", mime_type: "audio/mp4", url: "https://storage.example/signed?token=t", expires_in: 3600, duration_seconds: 600 });
  workspaceApi.listQuestions.mockResolvedValue({ items: [] });
});

function renderWorkspace() {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[`/lectures/${LECTURE_ID}`]}>
        <Routes>
          <Route path="/lectures/:id" element={<Workspace />} />
        </Routes>
      </MemoryRouter>
    </ToastProvider>
  );
}

async function readyPlayer() {
  renderWorkspace();
  await screen.findByRole("heading", { name: "Machine Learning Lecture 1" });
  const media = await waitFor(() => {
    const element = document.querySelector("audio");
    if (!element) throw new Error("no media element");
    return element;
  });
  fireEvent.loadedMetadata(media);
  return media;
}

function playAt(media, seconds) {
  media.currentTime = seconds;
  fireEvent.timeUpdate(media);
}

const activeRow = () => document.querySelector(".transcript__segment.is-active");

describe("Lecture workspace", () => {
  it("rejects a lecture that isn't the user's with not-found", async () => {
    workspaceApi.getWorkspace.mockRejectedValue(Object.assign(new Error("Lecture not found."), { status: 404 }));
    renderWorkspace();
    expect(await screen.findByText("Lecture not found")).toBeTruthy();
    expect(workspaceApi.getMedia).not.toHaveBeenCalled();
  });

  it("renders the stored transcript and Phase 5 intelligence", async () => {
    await readyPlayer();
    expect(screen.getByText("Welcome to machine learning.")).toBeTruthy();
    expect(screen.getByText("The lecture introduces machine learning.")).toBeTruthy();
    expect(screen.getByText("It then covers gradient descent.")).toBeTruthy(); // paragraphs kept
    expect(screen.getByText("Labels are required.")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Lecture notes" }));
    fireEvent.click(screen.getByRole("tab", { name: "Concepts" }));
    expect(screen.getByText("Supervised learning")).toBeTruthy();
    expect(screen.getByText("The step size.")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Topics" }));
    expect(screen.getByText("Learning rate")).toBeTruthy();
    expect(screen.getByText("No worked examples were identified in this lecture.")).toBeTruthy();
  });

  it("keeps a lecture that is still processing out of the workspace", async () => {
    workspaceApi.getWorkspace.mockResolvedValue(workspaceData({ lecture: lecture({ status: "TRANSCRIBING" }), intelligence: null }));
    renderWorkspace();
    expect(await screen.findByText("This lecture is still being processed")).toBeTruthy();
    expect(workspaceApi.getMedia).not.toHaveBeenCalled();
    expect(screen.queryByPlaceholderText("Ask something about this lecture...")).toBeNull();
  });

  it("plays private media from the signed URL the API returns", async () => {
    const media = await readyPlayer();
    expect(workspaceApi.getMedia).toHaveBeenCalledWith(LECTURE_ID);
    expect(media.getAttribute("src")).toBe("https://storage.example/signed?token=t");
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
  });

  it("shows an honest state when the lecture has no playable media", async () => {
    workspaceApi.getMedia.mockRejectedValue(Object.assign(new Error("none"), { status: 404 }));
    renderWorkspace();
    expect(await screen.findByText(/Playback isn’t available for this lecture/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Play" }).disabled).toBe(true);
  });
});

describe("Transcript synchronization", () => {
  it("highlights the segment that is playing as the player moves", async () => {
    const media = await readyPlayer();
    act(() => playAt(media, 7));
    expect(within(activeRow()).getByText("Supervised learning uses labels.")).toBeTruthy();
    act(() => playAt(media, 131));
    expect(within(activeRow()).getByText("Gradient descent and the learning rate.")).toBeTruthy();
  });

  it("seeks the player when a transcript segment is clicked", async () => {
    const media = await readyPlayer();
    fireEvent.click(screen.getByRole("button", { name: "Play from 02:10" }));
    expect(media.currentTime).toBe(130);
    expect(within(activeRow()).getByText("Gradient descent and the learning rate.")).toBeTruthy();
  });

  it("moves the transcript when the player is seeked with the timeline", async () => {
    const media = await readyPlayer();
    fireEvent.change(screen.getByRole("slider", { name: "Seek" }), { target: { value: "8" } });
    expect(media.currentTime).toBe(8);
    expect(within(activeRow()).getByText("Supervised learning uses labels.")).toBeTruthy();
  });

  it("finds text in the transcript", async () => {
    await readyPlayer();
    fireEvent.change(screen.getByPlaceholderText("Find in transcript…"), { target: { value: "learning" } });
    expect(screen.getByText("1 of 3")).toBeTruthy();
    expect(document.querySelectorAll(".transcript__text mark")).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: "Next match" }));
    expect(screen.getByText("2 of 3")).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText("Find in transcript…"), { target: { value: "zebra" } });
    expect(screen.getByText("No matches")).toBeTruthy();
  });
});

describe("Chapters and intelligence timestamps", () => {
  it("lists chapters in order and seeks to a chapter", async () => {
    const media = await readyPlayer();
    fireEvent.click(screen.getByRole("tab", { name: "Lecture notes" }));
    fireEvent.click(screen.getByRole("tab", { name: "Chapters" }));
    const items = document.querySelectorAll(".chapter-list__item");
    expect([...items].map((item) => item.querySelector(".chapter-list__title").textContent)).toEqual([
      "Course overview",
      "Gradient descent",
    ]);
    expect(items[1].textContent).toContain("02:05 – 10:00");
    fireEvent.click(items[1]);
    expect(media.currentTime).toBe(125);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
    expect(document.querySelector(".chapter-list li.is-active").textContent).toContain("Gradient descent");
    expect(document.querySelector(".player__audio-label").textContent).toContain("Chapter 2 · 02:05–10:00"); // audio card shows the current chapter
  });

  it("seeks to the earliest chunk a concept or definition cites", async () => {
    const media = await readyPlayer();
    fireEvent.click(screen.getByRole("tab", { name: "Lecture notes" }));
    fireEvent.click(screen.getByRole("tab", { name: "Concepts" }));
    fireEvent.click(screen.getByRole("button", { name: "Play from 00:55" })); // concept cites chunk 1
    expect(media.currentTime).toBe(55);
    fireEvent.click(screen.getByRole("button", { name: "Play from 03:15" })); // definition cites chunk 3
    expect(media.currentTime).toBe(195);
  });
});

describe("Grounded Q&A", () => {
  it("shows an answer with its sources, and a source click seeks the player", async () => {
    workspaceApi.askQuestion.mockResolvedValue(answered);
    const media = await readyPlayer();
    const input = screen.getByPlaceholderText("Ask something about this lecture...");
    const ask = screen.getByRole("button", { name: /^Ask/ });
    expect(ask.disabled).toBe(true); // nothing to ask yet
    fireEvent.change(input, { target: { value: "What is supervised learning?" } });
    fireEvent.click(ask);
    expect(await screen.findByText(/Finding the relevant parts of the lecture/)).toBeTruthy();
    expect(await screen.findByText("It learns from labelled examples.")).toBeTruthy();
    expect(workspaceApi.askQuestion).toHaveBeenCalledWith(LECTURE_ID, "What is supervised learning?");

    const sources = screen.getAllByRole("button", { name: /Play source from/ });
    expect(sources).toHaveLength(1); // only cited passages are shown as sources
    fireEvent.click(sources[0]);
    expect(media.currentTime).toBe(55);

    fireEvent.click(screen.getByRole("button", { name: /View source passages \(1\)/ }));
    expect(screen.getByText("Supervised learning uses labels and examples.")).toBeTruthy();
  });

  it("presents insufficient evidence as an intentional answer without sources", async () => {
    workspaceApi.askQuestion.mockResolvedValue(insufficient);
    await readyPlayer();
    fireEvent.change(screen.getByPlaceholderText("Ask something about this lecture..."), { target: { value: "What is the capital of France?" } });
    fireEvent.click(screen.getByRole("button", { name: /^Ask/ }));
    expect(await screen.findByText(/couldn't find enough information in this lecture/)).toBeTruthy();
    expect(screen.getByText("Try asking about a concept covered in the lecture.")).toBeTruthy();
    expect(screen.queryByText("Lecture sources")).toBeNull();
    expect(screen.queryAllByRole("button", { name: /Play source from/ })).toHaveLength(0);
  });

  it("offers a retry when an answer can't be generated", async () => {
    workspaceApi.askQuestion
      .mockRejectedValueOnce(Object.assign(new Error("An answer couldn't be generated right now."), { status: 503 }))
      .mockResolvedValueOnce(answered);
    await readyPlayer();
    fireEvent.change(screen.getByPlaceholderText("Ask something about this lecture..."), { target: { value: "What is supervised learning?" } });
    fireEvent.click(screen.getByRole("button", { name: /^Ask/ }));
    expect(await screen.findByText("An answer couldn't be generated right now.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("It learns from labelled examples.")).toBeTruthy();
    expect(workspaceApi.askQuestion).toHaveBeenCalledTimes(2);
  });

  it("loads this lecture's question history after a refresh", async () => {
    workspaceApi.listQuestions.mockResolvedValue({ items: [insufficient, answered] });
    await readyPlayer();
    expect(workspaceApi.listQuestions).toHaveBeenCalledWith(LECTURE_ID);
    expect(await screen.findByText("Questions about this lecture (2)")).toBeTruthy();
    // The newest is open; older ones are previews that expand.
    expect(screen.getByText(/couldn't find enough information/)).toBeTruthy();
    const older = screen.getByRole("button", { name: /What is supervised learning\?/ });
    expect(older.textContent).toContain("00:55");
    fireEvent.click(older);
    expect(screen.getByText("It learns from labelled examples.")).toBeTruthy();
  });
});
