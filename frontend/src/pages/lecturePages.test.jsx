import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { ToastProvider } from "../components/ui/Toast";

const lectures = vi.hoisted(() => ({
  listLectures: vi.fn(),
  listSubjects: vi.fn(),
  getLecture: vi.fn(),
  deleteLecture: vi.fn(),
}));
vi.mock("../services/lectures", () => lectures);

const ingestion = vi.hoisted(() => ({
  getIngestionLimits: vi.fn(),
  uploadLecture: vi.fn(),
  submitSourceUrl: vi.fn(),
  retryProcessing: vi.fn(),
  getProcessingDetails: vi.fn(),
}));
vi.mock("../services/ingestion", () => ingestion);

const history = vi.hoisted(() => ({ listHistory: vi.fn() }));
vi.mock("../services/history", () => history);

const { AuthContext } = await import("../auth/AuthContext");
const AUTH = { status: "authenticated", user: { email: "ada@example.com" }, profile: { display_name: "Ada Lovelace" } };

const { default: Library } = await import("./Library");
const { default: Dashboard } = await import("./Dashboard");
const { default: Upload } = await import("./Upload");
const { default: Processing } = await import("./Processing");

const lecture = (overrides = {}) => ({
  id: crypto.randomUUID(),
  title: "Convex Optimization & Duality",
  subject: "Computer Science",
  topic: null,
  instructor: "Prof. Andrew Ng",
  lecture_date: "2026-09-14",
  tags: ["Machine Learning", "Optimization"],
  source_type: "video",
  source_url: null,
  status: "READY",
  duration_seconds: 3522,
  created_at: "2026-09-29T10:00:00Z",
  updated_at: "2026-09-29T10:00:00Z",
  ...overrides,
});

const page = (items, total = items.length) => ({ items, total, limit: 25, offset: 0 });

function LocationProbe() {
  const location = useLocation();
  return <p data-testid="location">{location.pathname + location.search}</p>;
}

function renderAt(path) {
  return render(
    <AuthContext.Provider value={AUTH}>
    <ToastProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/library" element={<Library />} />
          <Route path="/search" element={<p>Search page</p>} />
          <Route path="/lectures/new" element={<Upload />} />
          <Route path="/lectures/:id/processing" element={<Processing />} />
          <Route path="*" element={null} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </ToastProvider>
    </AuthContext.Provider>
  );
}

beforeEach(() => {
  Object.values(lectures).forEach((fn) => fn.mockReset());
  Object.values(ingestion).forEach((fn) => fn.mockReset());
  ingestion.getIngestionLimits.mockResolvedValue({
    video: { max_bytes: 2 * 1024 ** 3, formats: [] },
    audio: { max_bytes: 500 * 1024 ** 2, formats: [] },
    max_duration_seconds: 14400,
    source_urls_enabled: true,
    source_providers: ["youtube"],
  });
  lectures.listSubjects.mockResolvedValue({ subjects: ["Computer Science", "Physics"] });
  history.listHistory.mockReset();
  history.listHistory.mockResolvedValue({ items: [], total: 0, limit: 3, offset: 0 });
  localStorage.clear();
});

describe("Lecture Library", () => {
  it("renders the user's real lectures with metadata and status", async () => {
    lectures.listLectures.mockResolvedValue(
      page([lecture(), lecture({ title: "Quantum Mechanics", status: "CHUNKING", source_type: "audio", tags: [] })])
    );
    renderAt("/library");

    const first = (await screen.findByText("Convex Optimization & Duality")).closest("article");
    expect(within(first).getByText("Prof. Andrew Ng")).toBeTruthy();
    expect(within(first).getByText("58:42")).toBeTruthy();
    expect(within(first).getByText("Ready")).toBeTruthy();
    expect(within(first).getByRole("link", { name: /Open Workspace/ })).toBeTruthy();

    const second = screen.getByText("Quantum Mechanics").closest("article");
    expect(within(second).getByText(/Semantic chunking \(Stage 5\/8\)/)).toBeTruthy();
    expect(within(second).getByRole("link", { name: /View Processing Details/ })).toBeTruthy();
    expect(screen.getByText("Showing 1 – 2 of 2 lectures")).toBeTruthy();
  });

  it("shows the empty-library state with a way to add a lecture", async () => {
    lectures.listLectures.mockResolvedValue(page([]));
    renderAt("/library");
    expect(await screen.findByText("Your lecture library is empty")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Add Your First Lecture" }).getAttribute("href")).toBe("/lectures/new");
  });

  it("distinguishes 'no matches' from an empty library", async () => {
    lectures.listLectures.mockResolvedValue(page([]));
    renderAt("/library?status=failed");
    expect(await screen.findByText("No lectures match these filters")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/library"));
  });

  it("passes URL filters to the API and shows errors with retry", async () => {
    lectures.listLectures.mockRejectedValueOnce(new Error("Server unavailable")).mockResolvedValue(page([lecture()]));
    renderAt("/library?q=duality&subject=Physics&status=ready&source=url&sort=title&page=2");

    expect(await screen.findByText("We couldn't load your lectures.")).toBeTruthy();
    expect(lectures.listLectures.mock.calls[0][0]).toEqual({
      q: "duality",
      subject: "Physics",
      status: "ready",
      sourceType: "url",
      sort: "title",
      limit: 25,
      offset: 25,
    });

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Convex Optimization & Duality")).toBeTruthy();
  });

  it("debounces search into the URL", async () => {
    lectures.listLectures.mockResolvedValue(page([]));
    renderAt("/library");
    await screen.findByText("Your lecture library is empty");
    fireEvent.change(screen.getByLabelText("Search lectures"), { target: { value: "kkt" } });
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/library?q=kkt"), { timeout: 2000 });
    expect(lectures.listLectures).toHaveBeenLastCalledWith(expect.objectContaining({ q: "kkt" }), expect.anything());
  });

  it("deletes only after confirmation, then refreshes", async () => {
    const target = lecture();
    lectures.listLectures.mockResolvedValueOnce(page([target])).mockResolvedValue(page([]));
    lectures.deleteLecture.mockResolvedValue("");
    renderAt("/library");

    fireEvent.click(await screen.findByRole("button", { name: `More actions for ${target.title}` }));
    fireEvent.click(screen.getByRole("menuitem", { name: /Delete lecture/ }));

    const dialog = screen.getByRole("dialog", { name: "Delete this lecture?" });
    expect(lectures.deleteLecture).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete Lecture" }));

    await waitFor(() => expect(lectures.deleteLecture).toHaveBeenCalledWith(target.id));
    expect(await screen.findByText(`"${target.title}" was deleted.`)).toBeTruthy();
    expect(await screen.findByText("Your lecture library is empty")).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("cancelling the dialog deletes nothing", async () => {
    const target = lecture();
    lectures.listLectures.mockResolvedValue(page([target]));
    renderAt("/library");

    fireEvent.click(await screen.findByRole("button", { name: `More actions for ${target.title}` }));
    fireEvent.click(screen.getByRole("menuitem", { name: /Delete lecture/ }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(lectures.deleteLecture).not.toHaveBeenCalled();
  });

  it("keeps the dialog open with an error when deletion fails", async () => {
    const target = lecture();
    lectures.listLectures.mockResolvedValue(page([target]));
    lectures.deleteLecture.mockRejectedValue(Object.assign(new Error("A required service is temporarily unavailable."), { status: 502 }));
    renderAt("/library");

    fireEvent.click(await screen.findByRole("button", { name: `More actions for ${target.title}` }));
    fireEvent.click(screen.getByRole("menuitem", { name: /Delete lecture/ }));
    fireEvent.click(screen.getByRole("button", { name: "Delete Lecture" }));

    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/temporarily unavailable/)).toBeTruthy();
    expect(screen.getByText(target.title, { selector: "a" })).toBeTruthy();
  });
});

describe("Dashboard", () => {
  it("shows real processing stages, failures and recent lectures", async () => {
    lectures.listLectures.mockImplementation(async ({ status }) => {
      if (status === "processing") return page([lecture({ title: "Bio 101", status: "GENERATING_INTELLIGENCE" })]);
      if (status === "failed") return page([lecture({ title: "Math 115", status: "FAILED" })]);
      return page([lecture(), lecture({ title: "Phil 101", source_type: "audio" })], 28);
    });
    renderAt("/dashboard");

    const card = await screen.findByRole("region", { name: "Processing Bio 101" });
    expect(within(card).getByText("Stage 8 of 8")).toBeTruthy();
    expect(within(card).queryByText(/%/)).toBeNull();
    expect(await screen.findByText("Math 115")).toBeTruthy();
    expect(screen.getByText("Showing 2 of 28 lectures")).toBeTruthy();
    expect(screen.queryByText(/Continue Studying/)).toBeNull();
  });

  it("greets the user and shows real overview counts and recent questions", async () => {
    lectures.listLectures.mockImplementation(async ({ status, limit }) => {
      if (status === "processing") return page([]);
      if (status === "failed") return page([]);
      if (status === "ready") return page([lecture({ duration_seconds: 3600 }), lecture({ duration_seconds: 1800 })], 2);
      return page([lecture()], limit === 1 ? 7 : 1);
    });
    history.listHistory.mockResolvedValue({
      items: [
        {
          id: "q1",
          question: "What is a convex set?",
          outcome: "answered",
          created_at: "2026-10-01T10:00:00Z",
          lecture: { id: "lec-9", title: "Convex Optimization & Duality" },
        },
      ],
      total: 12,
      limit: 3,
      offset: 0,
    });
    renderAt("/dashboard");

    expect(await screen.findByRole("heading", { level: 1, name: "Welcome back, Ada" })).toBeTruthy();
    const overview = screen.getByRole("region", { name: "Overview" });
    expect(await within(overview).findByText("7")).toBeTruthy(); // all lectures
    expect(within(overview).getByText("1.5 h")).toBeTruthy(); // ready lecture hours
    expect(within(overview).getByText("12")).toBeTruthy(); // questions asked
    const question = await screen.findByRole("link", { name: /What is a convex set\?/ });
    expect(question.getAttribute("href")).toBe("/lectures/lec-9?question=q1&from=history");
  });

  it("shows an empty state when the library is empty", async () => {
    lectures.listLectures.mockResolvedValue(page([]));
    renderAt("/dashboard");
    expect(await screen.findByText("Your lecture library is empty")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("quick search opens Search with the query", async () => {
    lectures.listLectures.mockResolvedValue(page([]));
    renderAt("/dashboard");
    fireEvent.change(screen.getByLabelText("Search your lectures"), { target: { value: "duality" } });
    fireEvent.submit(screen.getByRole("search"));
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/search?q=duality"));
  });
});

describe("Add a Lecture", () => {
  const chooseFile = (file) =>
    act(() => fireEvent.change(screen.getByLabelText(/Choose a (video|audio) file/), { target: { files: [file] } }));
  const accepted = (overrides = {}) => ({
    lecture: { id: "lec-1", title: "cs229 lecture04", status: "QUEUED", source_type: "video", source_url: null },
    job: { id: "job-1", status: "queued", current_stage: "EXTRACTING_AUDIO" },
    replayed: false,
    ...overrides,
  });

  async function fillValidVideo() {
    await chooseFile(new File(["x"], "cs229_lecture04.mp4", { type: "video/mp4" }));
    fireEvent.change(screen.getByLabelText(/Subject \/ Discipline/), { target: { value: "Computer Science" } });
    fireEvent.change(screen.getByLabelText(/Tags/), { target: { value: "ML, Optimization, ml" } });
  }

  it("rejects unsupported files and accepts valid ones", async () => {
    renderAt("/lectures/new");
    await chooseFile(new File(["x"], "notes.pdf", { type: "application/pdf" }));
    expect(screen.getByText(/This file type isn't supported/)).toBeTruthy();

    await chooseFile(new File(["x"], "cs229_lecture04.mp4", { type: "video/mp4" }));
    expect(screen.getByText("cs229_lecture04.mp4")).toBeTruthy();
    expect(screen.getByLabelText(/Lecture Title/).value).toBe("cs229 lecture04");
  });

  it("uses the server's size limits", async () => {
    ingestion.getIngestionLimits.mockResolvedValue({
      video: { max_bytes: 1000, formats: [] },
      audio: { max_bytes: 1000, formats: [] },
      max_duration_seconds: 60,
      source_urls_enabled: true,
      source_providers: ["youtube"],
    });
    renderAt("/lectures/new");
    await waitFor(() => expect(screen.getByText(/up to 1 KB/)).toBeTruthy());
    await chooseFile(new File([new Uint8Array(2000)], "big.mp4", { type: "video/mp4" }));
    expect(screen.getByText(/larger than the 1 KB limit/)).toBeTruthy();
  });

  it("validates required details, the URL and rights confirmation", async () => {
    renderAt("/lectures/new");
    fireEvent.click(screen.getByRole("tab", { name: /YouTube/ }));
    fireEvent.change(screen.getByLabelText("Video URL"), { target: { value: "https://vimeo.com/1" } });
    fireEvent.click(screen.getByRole("button", { name: /Add Lecture & Start Processing/ }));

    expect(screen.getByText("Only YouTube links are supported right now.")).toBeTruthy();
    expect(screen.getByText("Enter the subject or discipline.")).toBeTruthy();
    expect(screen.getByText("Confirm that you have the right to use this video.")).toBeTruthy();
    expect(screen.queryByText("Enter a lecture title.")).toBeNull(); // the video's own title is used
    expect(ingestion.submitSourceUrl).not.toHaveBeenCalled();
  });

  it("uploads the file with its details and shows real progress, then the result", async () => {
    let resolveUpload;
    ingestion.uploadLecture.mockImplementation(({ onProgress }) => {
      onProgress({ loaded: 512 * 1024, total: 1024 * 1024 });
      return new Promise((resolve) => (resolveUpload = resolve));
    });
    renderAt("/lectures/new");
    await fillValidVideo();
    fireEvent.click(screen.getByRole("button", { name: /Add Lecture & Start Processing/ }));

    expect(await screen.findByText("512 KB of 1.0 MB (50%)")).toBeTruthy();
    const call = ingestion.uploadLecture.mock.calls[0][0];
    expect(call.kind).toBe("video");
    expect(call.file.name).toBe("cs229_lecture04.mp4");
    expect(call.details).toMatchObject({ title: "cs229 lecture04", subject: "Computer Science", tags: ["ML", "Optimization"] });
    expect(call.idempotencyKey).toMatch(/^[0-9a-f-]{36}$/);

    await act(async () => resolveUpload(accepted()));
    expect(await screen.findByText("Lecture added")).toBeTruthy();
    expect(screen.getByRole("link", { name: /View Processing Details/ }).getAttribute("href")).toBe(
      "/lectures/lec-1/processing"
    );
  });

  it("resubmitting the same input reuses its request key; changed input gets a new one", async () => {
    ingestion.uploadLecture.mockRejectedValue(Object.assign(new Error("Unable to reach the server."), { status: 0 }));
    renderAt("/lectures/new");
    await fillValidVideo();
    fireEvent.click(screen.getByRole("button", { name: /Add Lecture & Start Processing/ }));
    await screen.findByText("Unable to reach the server.");
    fireEvent.click(screen.getByRole("button", { name: /Add Lecture & Start Processing/ }));
    await waitFor(() => expect(ingestion.uploadLecture).toHaveBeenCalledTimes(2));
    const [first, second] = ingestion.uploadLecture.mock.calls.map(([args]) => args.idempotencyKey);
    expect(second).toBe(first);

    fireEvent.change(screen.getByLabelText(/Specific Topic/), { target: { value: "Duality" } });
    fireEvent.click(screen.getByRole("button", { name: /Add Lecture & Start Processing/ }));
    await waitFor(() => expect(ingestion.uploadLecture).toHaveBeenCalledTimes(3));
    expect(ingestion.uploadLecture.mock.calls[2][0].idempotencyKey).not.toBe(first);
  });

  it("links to the existing lecture when the content is a duplicate", async () => {
    ingestion.uploadLecture.mockRejectedValue(
      Object.assign(new Error("This lecture is already in your library."), {
        status: 409,
        data: { code: "duplicate_lecture", details: { lecture_id: "existing-1" } },
      })
    );
    renderAt("/lectures/new");
    await fillValidVideo();
    fireEvent.click(screen.getByRole("button", { name: /Add Lecture & Start Processing/ }));
    expect(await screen.findByText(/already in your library/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open the existing lecture" }).getAttribute("href")).toBe(
      "/lectures/existing-1/processing"
    );
  });

  it("shows the server's rejection and keeps the form", async () => {
    ingestion.uploadLecture.mockRejectedValue(
      Object.assign(new Error("This file isn't a supported video format (MP4, MOV, WebM, MKV)."), {
        status: 415,
        data: { code: "unsupported_media" },
      })
    );
    renderAt("/lectures/new");
    await fillValidVideo();
    fireEvent.click(screen.getByRole("button", { name: /Add Lecture & Start Processing/ }));
    expect(await screen.findByText(/isn't a supported video format/)).toBeTruthy();
    expect(screen.getByLabelText(/Lecture Title/).value).toBe("cs229 lecture04");
    expect(screen.queryByText("Lecture added")).toBeNull();
  });

  it("can cancel an upload in progress", async () => {
    ingestion.uploadLecture.mockImplementation(
      ({ signal, onProgress }) =>
        new Promise((_, reject) => {
          onProgress({ loaded: 10, total: 100 });
          signal.addEventListener("abort", () => reject(new DOMException("Upload cancelled", "AbortError")));
        })
    );
    renderAt("/lectures/new");
    await fillValidVideo();
    fireEvent.click(screen.getByRole("button", { name: /Add Lecture & Start Processing/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Cancel upload" }));
    expect(await screen.findByText("Upload cancelled. Nothing was saved.")).toBeTruthy();
  });

  it("submits a YouTube URL with rights confirmation", async () => {
    ingestion.submitSourceUrl.mockResolvedValue(
      accepted({ lecture: { id: "lec-2", title: "MIT 6.006", status: "QUEUED", source_type: "url", source_url: "x" } })
    );
    renderAt("/lectures/new");
    fireEvent.click(screen.getByRole("tab", { name: /YouTube/ }));
    fireEvent.change(screen.getByLabelText("Video URL"), { target: { value: "https://youtu.be/ZA-tUyM_y7s" } });
    fireEvent.click(screen.getByLabelText(/I have the right to use this video/));
    fireEvent.change(screen.getByLabelText(/Subject \/ Discipline/), { target: { value: "Algorithms" } });
    fireEvent.click(screen.getByRole("button", { name: /Add Lecture & Start Processing/ }));

    expect(await screen.findByText("Lecture added")).toBeTruthy();
    expect(ingestion.submitSourceUrl).toHaveBeenCalledWith(
      expect.objectContaining({ url: "https://youtu.be/ZA-tUyM_y7s", rightsConfirmed: true })
    );
  });
});

describe("Processing details", () => {
  const details = (job, extra = {}) => ({
    lecture: {
      id: "lec-1",
      title: "Real Analysis",
      status: extra.status ?? "TRANSCRIBING",
      source_type: "audio",
      source_url: null,
    },
    job: {
      id: "job-1",
      current_stage: "TRANSCRIBING",
      attempt_count: 1,
      max_attempts: 3,
      error_code: null,
      error_message: null,
      retryable: null,
      status_detail: null,
      queued_at: "2026-10-01T10:00:00Z",
      started_at: null,
      finished_at: null,
      failed_at: null,
      next_attempt_at: null,
      updated_at: "2026-10-01T10:00:00Z",
      ...job,
    },
    stage_runs: [
      {
        stage: "EXTRACTING_AUDIO",
        attempt: 1,
        status: "succeeded",
        started_at: "2026-10-01T10:00:01Z",
        finished_at: "2026-10-01T10:00:03Z",
        duration_ms: 2400,
        error_code: null,
      },
    ],
    media: [{ kind: "original", mime_type: "audio/mpeg", file_size: 96000, duration_seconds: 3, probe: {} }],
    implemented_stages: ["EXTRACTING_AUDIO"],
  });

  it("shows completed stages, measured timings and the honest waiting state", async () => {
    ingestion.getProcessingDetails.mockResolvedValue(
      details({
        status: "waiting",
        status_detail: "Transcription isn't available yet. Processing will continue from here once it is.",
      })
    );
    renderAt("/lectures/lec-1/processing");
    expect(await screen.findByText(/Transcription isn't available yet/)).toBeTruthy();
    const extraction = screen.getByText("Audio extraction").closest("li");
    expect(within(extraction).getByLabelText("Completed")).toBeTruthy();
    expect(within(extraction).getByText("2.4 s")).toBeTruthy();
    expect(within(screen.getByText("Transcription").closest("li")).getByLabelText("Waiting")).toBeTruthy();
    expect(screen.getAllByText("Not available yet").length).toBeGreaterThan(0);
    expect(screen.queryByText(/FLAC/)).toBeNull(); // derived audio is temporary worker data, never listed as stored media
    expect(screen.queryByText(/%/)).toBeNull();
  });

  it("shows the failure reason and retries a retryable failure", async () => {
    ingestion.getProcessingDetails.mockResolvedValue(
      details(
        {
          status: "failed",
          current_stage: "EXTRACTING_AUDIO",
          error_code: "service_unavailable",
          error_message: "A storage service was temporarily unavailable.",
          retryable: true,
          failed_at: "2026-10-01T10:05:00Z",
        },
        { status: "FAILED" }
      )
    );
    ingestion.retryProcessing.mockResolvedValue({});
    renderAt("/lectures/lec-1/processing");
    expect(await screen.findByText("Audio extraction couldn't be completed")).toBeTruthy();
    expect(screen.getByText("A storage service was temporarily unavailable.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Retry Processing/ }));
    await waitFor(() => expect(ingestion.retryProcessing).toHaveBeenCalledWith("lec-1"));
    expect(await screen.findByText(/Processing restarted/)).toBeTruthy();
  });

  it("doesn't offer retry when it can't help", async () => {
    ingestion.getProcessingDetails.mockResolvedValue(
      details(
        {
          status: "failed",
          current_stage: "EXTRACTING_AUDIO",
          error_code: "no_audio_stream",
          error_message: "This file has no audio track.",
          retryable: false,
          failed_at: "2026-10-01T10:05:00Z",
        },
        { status: "FAILED" }
      )
    );
    renderAt("/lectures/lec-1/processing");
    expect(await screen.findByText("This file has no audio track.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Retry Processing/ })).toBeNull();
    expect(screen.getByText(/Retrying won't fix this/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Details" }));
    expect(screen.getByText("no_audio_stream")).toBeTruthy();
  });

  it("shows not found for another user's lecture", async () => {
    ingestion.getProcessingDetails.mockRejectedValue(Object.assign(new Error("Lecture not found."), { status: 404 }));
    renderAt("/lectures/lec-9/processing");
    expect(await screen.findByText("Lecture not found")).toBeTruthy();
  });
});

describe("Library processing states", () => {
  it("shows the failure reason and a working retry for retryable failures", async () => {
    const failedLecture = lecture({
      title: "Metric Spaces",
      status: "FAILED",
      job: {
        status: "failed",
        current_stage: "EXTRACTING_AUDIO",
        error_code: "service_unavailable",
        error_message: "Storage was temporarily unavailable.",
        retryable: true,
      },
    });
    lectures.listLectures.mockResolvedValue(page([failedLecture]));
    ingestion.retryProcessing.mockResolvedValue({});
    renderAt("/library");
    const card = (await screen.findByText("Metric Spaces", { selector: "a" })).closest("article");
    expect(within(card).getByText("Storage was temporarily unavailable.")).toBeTruthy();
    fireEvent.click(within(card).getByRole("button", { name: /Retry Processing/ }));
    await waitFor(() => expect(ingestion.retryProcessing).toHaveBeenCalledWith(failedLecture.id));
    await waitFor(() => expect(lectures.listLectures).toHaveBeenCalledTimes(2));
  });

  it("labels a job waiting at the phase boundary honestly", async () => {
    lectures.listLectures.mockResolvedValue(
      page([
        lecture({
          title: "Waiting Lecture",
          status: "TRANSCRIBING",
          job: { status: "waiting", current_stage: "TRANSCRIBING", error_code: null },
        }),
      ])
    );
    renderAt("/library");
    const card = (await screen.findByText("Waiting Lecture", { selector: "a" })).closest("article");
    expect(within(card).getByText(/Waiting: Transcription isn't available yet/)).toBeTruthy();
    expect(within(card).getByText("Waiting")).toBeTruthy();
  });
});

