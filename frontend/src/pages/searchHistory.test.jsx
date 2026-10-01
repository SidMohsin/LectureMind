import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { ToastProvider } from "../components/ui/Toast";

const lectures = vi.hoisted(() => ({ listLectures: vi.fn(), listSubjects: vi.fn(), getLecture: vi.fn(), deleteLecture: vi.fn() }));
vi.mock("../services/lectures", () => lectures);
const search = vi.hoisted(() => ({ searchContent: vi.fn() }));
vi.mock("../services/search", () => search);
const history = vi.hoisted(() => ({ listHistory: vi.fn(), deleteQuestion: vi.fn(), clearLectureQuestions: vi.fn() }));
vi.mock("../services/history", () => history);
const workspaceApi = vi.hoisted(() => ({ getWorkspace: vi.fn(), getMedia: vi.fn(), listQuestions: vi.fn(), askQuestion: vi.fn() }));
vi.mock("../services/workspace", () => workspaceApi);

const { default: Search } = await import("./Search");
const { default: History } = await import("./History");
const { default: Workspace } = await import("./Workspace");

const LECTURE_ID = "5b3d0c3e-0000-4000-8000-000000000002";
const lectureRef = { id: LECTURE_ID, title: "Linear Regression and Gradient Descent", subject: "ML", topic: "Lecture 2", instructor: null, lecture_date: null };

const passage = (overrides = {}) => ({
  chunk_id: crypto.randomUUID(),
  lecture: lectureRef,
  sequence: 30,
  start_seconds: 2102,
  end_seconds: 2174,
  text: "And so if you run gradient descent on this algorithm, the step size is set by the learning rate.",
  similarity: 0.78,
  ...overrides,
});

const entry = (overrides = {}) => ({
  id: crypto.randomUUID(),
  lecture: lectureRef,
  question: "How is the learning rate chosen?",
  outcome: "answered",
  answer: "The lecture says the learning rate is usually chosen by trying a few values.",
  sources: [
    { number: 1, chunk_id: "c1", sequence: 30, start_seconds: 2102, end_seconds: 2174, similarity: 0.8, text: "The step size is set by the learning rate.", cited: true },
    { number: 2, chunk_id: "c2", sequence: 31, start_seconds: 2170, end_seconds: 2240, similarity: 0.7, text: "Uncited passage.", cited: false },
  ],
  latency_ms: 1400,
  created_at: "2026-10-01T10:05:00Z",
  ...overrides,
});

function LocationProbe() {
  const location = useLocation();
  return <p data-testid="location">{location.pathname + location.search}</p>;
}

function renderAt(path) {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/search" element={<Search />} />
          <Route path="/history" element={<History />} />
          <Route path="/lectures/:id" element={<Workspace />} />
          <Route path="/library" element={<p>Library page</p>} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </ToastProvider>
  );
}

const location = () => screen.getByTestId("location").textContent;

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
  Object.defineProperty(HTMLMediaElement.prototype, "readyState", { configurable: true, get: () => 4 });
  Object.defineProperty(HTMLMediaElement.prototype, "duration", { configurable: true, get: () => 4697 });
  HTMLMediaElement.prototype.play = vi.fn(() => Promise.resolve());
  HTMLMediaElement.prototype.pause = vi.fn();
});

beforeEach(() => {
  vi.clearAllMocks();
  lectures.listLectures.mockResolvedValue({ items: [], total: 0, limit: 5, offset: 0 });
  search.searchContent.mockResolvedValue({ query: "", results: [], min_similarity: 0.6, embedding_model: "m", latency_ms: 50 });
  history.listHistory.mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
});

describe("Search", () => {
  it("starts with guidance and validates short queries without searching", async () => {
    renderAt("/search");
    expect(screen.getByText(/Search works two ways at once/)).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText("Search lectures, topics, concepts..."), { target: { value: "ab" } });
    fireEvent.submit(screen.getByRole("search"));
    expect(screen.getByRole("alert").textContent).toContain("at least 3 characters");
    expect(search.searchContent).not.toHaveBeenCalled();
    expect(lectures.listLectures).not.toHaveBeenCalled();
  });

  it("searches lecture details and content together, then shows both result kinds", async () => {
    let resolveContent;
    search.searchContent.mockReturnValue(new Promise((resolve) => (resolveContent = resolve)));
    lectures.listLectures.mockResolvedValue({
      items: [{ id: LECTURE_ID, title: "Linear Regression and Gradient Descent", subject: "ML", topic: "Lecture 2", instructor: null, lecture_date: null, status: "READY", tags: [] }],
      total: 8,
      limit: 5,
      offset: 0,
    });
    renderAt("/search");
    fireEvent.change(screen.getByPlaceholderText("Search lectures, topics, concepts..."), { target: { value: "gradient descent" } });
    fireEvent.submit(screen.getByRole("search"));
    expect(location()).toBe("/search?q=gradient+descent");
    expect(await screen.findByText("Finding passages that discuss this…")).toBeTruthy();
    expect(search.searchContent).toHaveBeenCalledWith("gradient descent", {}, expect.anything());
    expect(lectures.listLectures).toHaveBeenCalledWith({ q: "gradient descent", limit: 5 }, expect.anything());

    resolveContent({ query: "gradient descent", results: [passage()], min_similarity: 0.6, embedding_model: "m", latency_ms: 90 });
    const result = (await screen.findByText("35:02 – 36:14", { exact: false })).closest(".passage");
    expect(within(result).getByText("35:02 – 36:14", { exact: false })).toBeTruthy();
    expect([...result.querySelectorAll("mark")].map((mark) => mark.textContent.toLowerCase())).toContain("gradient");
    expect(screen.getByRole("link", { name: /View all 8 in Library/ }).getAttribute("href")).toBe("/library?q=gradient%20descent");
  });

  it("opens a passage in the lecture at its timestamp", async () => {
    search.searchContent.mockResolvedValue({ query: "x", results: [passage()], min_similarity: 0.6, embedding_model: "m", latency_ms: 90 });
    workspaceApi.getWorkspace.mockResolvedValue({
      lecture: { ...lectureRef, tags: [], source_type: "url", source_url: null, status: "READY", duration_seconds: 4697, created_at: "2026-10-01T10:00:00Z", updated_at: "2026-10-01T10:00:00Z" },
      transcript: { language: "en", model: "m", segments: [
        { sequence: 0, start: 0, end: 5, text: "Welcome back." },
        { sequence: 1, start: 2100, end: 2110, text: "If you run gradient descent on this algorithm." },
      ] },
      chapters: [],
      intelligence: null,
      chunks: [],
    });
    workspaceApi.getMedia.mockResolvedValue({ kind: "audio", mime_type: "audio/mp4", url: "https://storage.example/signed", expires_in: 3600, duration_seconds: 4697 });
    workspaceApi.listQuestions.mockResolvedValue({ items: [] });
    renderAt("/search?q=gradient%20descent");
    fireEvent.click(await screen.findByRole("link", { name: /Open at 35:02/ }));
    await screen.findByRole("heading", { name: lectureRef.title });
    expect(location()).toBe(`/lectures/${LECTURE_ID}?t=2102&from=search`);
    expect(screen.getByText(/Opened from search/)).toBeTruthy();
    const media = document.querySelector("audio");
    fireEvent.loadedMetadata(media);
    await waitFor(() => expect(media.currentTime).toBe(2102)); // positioned, not autoplayed
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
    expect(document.querySelector(".transcript__segment.is-active").textContent).toContain("If you run gradient descent");
  });

  it("shows empty and error states, and retries", async () => {
    search.searchContent
      .mockRejectedValueOnce(Object.assign(new Error("Unable to reach the server."), { status: 0 }))
      .mockResolvedValueOnce({ query: "x", results: [], min_similarity: 0.6, embedding_model: "m", latency_ms: 50 });
    renderAt("/search?q=sourdough%20bread");
    expect(await screen.findByText("Unable to reach the server.")).toBeTruthy();
    expect(await screen.findByText("No lecture titles or details match.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText(/No passage in your lectures is a close enough match/)).toBeTruthy();
    expect(search.searchContent).toHaveBeenCalledTimes(2);
  });
});

describe("Question History", () => {
  it("lists questions with their lecture, date and source timestamps", async () => {
    history.listHistory.mockResolvedValue({ items: [entry(), entry({ id: "q-2", question: "What is the capital of France?", outcome: "insufficient_evidence", answer: "I couldn't find enough information in this lecture to answer that reliably.", sources: [] })], total: 2, limit: 20, offset: 0 });
    renderAt("/history");
    expect(await screen.findByText("2 questions")).toBeTruthy();
    expect(history.listHistory).toHaveBeenCalledWith({ q: "", lectureId: "", order: "newest", limit: 20, offset: 0 }, expect.anything());
    expect(screen.getAllByRole("link", { name: lectureRef.title })).toHaveLength(2);
    expect(screen.getByText("Not enough evidence in this lecture")).toBeTruthy();
    const timestamps = screen.getAllByRole("link", { name: /Open lecture at/ });
    expect(timestamps).toHaveLength(1); // only cited sources
    expect(timestamps[0].getAttribute("href")).toMatch(new RegExp(`/lectures/${LECTURE_ID}\\?t=2102&question=.+&from=history`));
  });

  it("filters by text, lecture and order through the URL", async () => {
    history.listHistory.mockResolvedValue({ items: [entry()], total: 1, limit: 20, offset: 0 });
    lectures.listLectures.mockResolvedValue({ items: [{ id: LECTURE_ID, title: lectureRef.title }], total: 1, limit: 100, offset: 0 });
    renderAt("/history");
    await screen.findByText("1 question");
    fireEvent.change(screen.getByPlaceholderText("Search questions and answers…"), { target: { value: "learning rate" } });
    await waitFor(() => expect(location()).toContain("q=learning+rate"));
    await waitFor(() => expect(screen.getByLabelText("Lecture", { selector: "select" }).querySelectorAll("option")).toHaveLength(2));
    fireEvent.change(screen.getByLabelText("Lecture", { selector: "select" }), { target: { value: LECTURE_ID } });
    fireEvent.change(screen.getByLabelText("Order", { selector: "select" }), { target: { value: "oldest" } });
    await waitFor(() =>
      expect(history.listHistory).toHaveBeenLastCalledWith({ q: "learning rate", lectureId: LECTURE_ID, order: "oldest", limit: 20, offset: 0 }, expect.anything())
    );
    expect(await screen.findByRole("button", { name: /Delete all questions about this lecture/ })).toBeTruthy();
  });

  it("expands an entry and opens it in the lecture with its source", async () => {
    const item = entry({ id: "q-open" });
    history.listHistory.mockResolvedValue({ items: [item], total: 1, limit: 20, offset: 0 });
    renderAt("/history");
    fireEvent.click(await screen.findByRole("button", { name: /How is the learning rate chosen\?/ }));
    expect(screen.getByText(item.answer)).toBeTruthy();
    expect(screen.getByText("The step size is set by the learning rate.")).toBeTruthy();
    expect(screen.queryByText("Uncited passage.")).toBeNull();
    expect(screen.getByRole("link", { name: /Open in lecture/ }).getAttribute("href")).toBe(`/lectures/${LECTURE_ID}?t=2102&question=q-open&from=history`);
  });

  it("deletes a question after confirmation", async () => {
    const item = entry({ id: "q-del" });
    history.listHistory.mockResolvedValueOnce({ items: [item], total: 1, limit: 20, offset: 0 }).mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
    history.deleteQuestion.mockResolvedValue(null);
    renderAt("/history");
    fireEvent.click(await screen.findByRole("button", { name: /How is the learning rate chosen\?/ }));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/will be removed from your history/)).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(history.deleteQuestion).toHaveBeenCalledWith("q-del"));
    expect(await screen.findByText("No questions yet")).toBeTruthy();
  });

  it("shows empty, no-match and error states", async () => {
    history.listHistory.mockRejectedValueOnce(Object.assign(new Error("Server error"), { status: 500 }));
    const { unmount } = renderAt("/history");
    expect(await screen.findByText("We couldn't load your question history.")).toBeTruthy();
    unmount();
    renderAt("/history?q=zebra");
    expect(await screen.findByText("No questions match")).toBeTruthy();
  });
});

describe("Workspace opened from history", () => {
  it("expands the chosen answer instead of the latest one", async () => {
    workspaceApi.getWorkspace.mockResolvedValue({
      lecture: { ...lectureRef, tags: [], source_type: "url", source_url: null, status: "READY", duration_seconds: 4697, created_at: "2026-10-01T10:00:00Z", updated_at: "2026-10-01T10:00:00Z" },
      transcript: { language: "en", model: "m", segments: [{ sequence: 0, start: 0, end: 5, text: "Welcome back." }] },
      chapters: [],
      intelligence: null,
      chunks: [],
    });
    workspaceApi.getMedia.mockResolvedValue({ kind: "audio", mime_type: "audio/mp4", url: "https://storage.example/signed", expires_in: 3600, duration_seconds: 4697 });
    const latest = entry({ id: "q-latest", question: "Latest question?", answer: "Latest answer." });
    const older = entry({ id: "q-older", question: "Older question?", answer: "Older answer." });
    workspaceApi.listQuestions.mockResolvedValue({ items: [latest, older] });
    renderAt(`/lectures/${LECTURE_ID}?question=q-older&t=2102&from=history`);
    await screen.findByText("Older answer.");
    const expanded = document.querySelectorAll(".qa-entry");
    expect(expanded).toHaveLength(1);
    expect(expanded[0].textContent).toContain("Older question?");
    expect(screen.getByText(/Opened from your question history/)).toBeTruthy();
  });
});
