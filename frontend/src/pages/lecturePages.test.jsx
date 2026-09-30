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

const { default: Library } = await import("./Library");
const { default: Dashboard } = await import("./Dashboard");
const { default: Upload } = await import("./Upload");
const { default: Workspace } = await import("./Workspace");

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
    <ToastProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/library" element={<Library />} />
          <Route path="/lectures/new" element={<Upload />} />
          <Route path="/lectures/:id" element={<Workspace />} />
          <Route path="*" element={null} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </ToastProvider>
  );
}

beforeEach(() => {
  Object.values(lectures).forEach((fn) => fn.mockReset());
  lectures.listSubjects.mockResolvedValue({ subjects: ["Computer Science", "Physics"] });
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
    expect(screen.getByRole("link", { name: "Upload Lecture" }).getAttribute("href")).toBe("/lectures/new");
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

  it("shows an empty state when the library is empty", async () => {
    lectures.listLectures.mockResolvedValue(page([]));
    renderAt("/dashboard");
    expect(await screen.findByText("Your lecture library is empty")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("quick search opens the library with the query", async () => {
    lectures.listLectures.mockResolvedValue(page([]));
    renderAt("/dashboard");
    fireEvent.change(screen.getByLabelText("Search your library"), { target: { value: "duality" } });
    fireEvent.submit(screen.getByRole("search"));
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/library?q=duality"));
  });
});

describe("Ingest Lecture", () => {
  const chooseFile = (file) =>
    act(() => fireEvent.change(screen.getByLabelText(/Choose a (video|audio) file/), { target: { files: [file] } }));

  it("rejects unsupported files and accepts valid ones", async () => {
    renderAt("/lectures/new");
    await chooseFile(new File(["x"], "notes.pdf", { type: "application/pdf" }));
    expect(screen.getByText(/This file type isn't supported/)).toBeTruthy();

    await chooseFile(new File(["x"], "cs229_lecture04.mp4", { type: "video/mp4" }));
    expect(screen.getByText("cs229_lecture04.mp4")).toBeTruthy();
    expect(screen.getByLabelText(/Lecture Title/).value).toBe("cs229 lecture04");
  });

  it("validates required details and the source URL", async () => {
    renderAt("/lectures/new");
    fireEvent.click(screen.getByRole("tab", { name: /YouTube/ }));
    fireEvent.change(screen.getByLabelText("Video URL"), { target: { value: "https://vimeo.com/1" } });
    fireEvent.click(screen.getByRole("button", { name: /Start Ingestion/ }));

    expect(screen.getByText("Only YouTube links are supported right now.")).toBeTruthy();
    expect(screen.getByText("Enter a lecture title.")).toBeTruthy();
    expect(screen.getByText("Enter the subject or discipline.")).toBeTruthy();
  });

  it("never pretends ingestion happened", async () => {
    renderAt("/lectures/new");
    await chooseFile(new File(["x"], "lecture.mp4", { type: "video/mp4" }));
    fireEvent.change(screen.getByLabelText(/Subject \/ Discipline/), { target: { value: "Computer Science" } });
    fireEvent.click(screen.getByRole("button", { name: /Start Ingestion/ }));

    expect(screen.getByText(/nothing has been uploaded or saved/)).toBeTruthy();
    expect(lectures.listLectures).not.toHaveBeenCalled();
    expect(lectures.deleteLecture).not.toHaveBeenCalled();
    expect(screen.getByTestId("location").textContent).toBe("/lectures/new");
  });
});

describe("Lecture route", () => {
  it("shows not-found for a lecture that isn't the user's", async () => {
    lectures.getLecture.mockRejectedValue(Object.assign(new Error("Lecture not found."), { status: 404 }));
    renderAt("/lectures/5b3d0c3e-0000-4000-8000-000000000000");
    expect(await screen.findByText("Lecture not found")).toBeTruthy();
  });

  it("shows the real lecture header and an honest workspace state", async () => {
    lectures.getLecture.mockResolvedValue(lecture());
    renderAt("/lectures/abc");
    expect(await screen.findByRole("heading", { name: "Convex Optimization & Duality" })).toBeTruthy();
    expect(screen.getByText("The lecture workspace is coming next")).toBeTruthy();
    expect(screen.queryByText(/transcript/i, { selector: "button" })).toBeNull();
  });
});
