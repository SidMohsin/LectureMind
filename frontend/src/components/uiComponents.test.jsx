import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Select from "./ui/Select";
import Input from "./ui/Input";
import { AuthContext } from "../auth/AuthContext";
import Landing from "../pages/Landing";

const OPTIONS = [
  { value: "", label: "All subjects" },
  { value: "math", label: "Mathematics" },
  { value: "phys", label: "Physics" },
];

describe("Select", () => {
  it("opens a styled list and reports the chosen value like a native select", () => {
    const onChange = vi.fn();
    render(<Select id="s" label="Subject" options={OPTIONS} value="" onChange={onChange} />);
    const trigger = screen.getByRole("combobox", { name: "Subject" });
    expect(trigger.textContent).toContain("All subjects");
    expect(trigger.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(trigger);
    expect(screen.getAllByRole("option")).toHaveLength(3);
    expect(screen.getByRole("option", { name: "All subjects" }).getAttribute("aria-selected")).toBe("true");
    fireEvent.click(screen.getByRole("option", { name: "Physics" }));

    expect(onChange).toHaveBeenCalledWith({ target: { value: "phys" } });
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("supports the keyboard: arrows, Enter, Escape and type-ahead", () => {
    const onChange = vi.fn();
    render(<Select id="s" label="Subject" options={OPTIONS} value="" onChange={onChange} />);
    const trigger = screen.getByRole("combobox", { name: "Subject" });

    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    expect(screen.getByRole("listbox")).toBeTruthy();
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    expect(trigger.getAttribute("aria-activedescendant")).toBe("s-opt-1");
    fireEvent.keyDown(trigger, { key: "Enter" });
    expect(onChange).toHaveBeenLastCalledWith({ target: { value: "math" } });

    fireEvent.keyDown(trigger, { key: "Enter" });
    fireEvent.keyDown(trigger, { key: "Escape" });
    expect(screen.queryByRole("listbox")).toBeNull();

    fireEvent.keyDown(trigger, { key: "p" }); // closed: type-ahead selects directly
    expect(onChange).toHaveBeenLastCalledWith({ target: { value: "phys" } });
  });

  it("opens upwards when there isn't room below, instead of moving the page", () => {
    render(<Select id="s" label="Subject" options={OPTIONS} value="" onChange={() => {}} />);
    const trigger = screen.getByRole("combobox", { name: "Subject" });
    const bottom = window.innerHeight - 20;
    trigger.getBoundingClientRect = () => ({ top: bottom - 40, bottom, left: 0, right: 200, width: 200, height: 40 });
    fireEvent.click(trigger);
    expect(trigger.closest(".select-field").className).toContain("select-field--up");
    fireEvent.keyDown(trigger, { key: "Escape" });

    trigger.getBoundingClientRect = () => ({ top: 100, bottom: 140, left: 0, right: 200, width: 200, height: 40 });
    fireEvent.click(trigger);
    expect(trigger.closest(".select-field").className).toContain("select-field--down");
  });

  it("closes when clicking outside", () => {
    render(<Select id="s" label="Subject" options={OPTIONS} value="" onChange={() => {}} />);
    fireEvent.click(screen.getByRole("combobox", { name: "Subject" }));
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("listbox")).toBeNull();
  });
});

describe("Input (password)", () => {
  it("can show and hide the password", () => {
    render(<Input id="pw" label="Password" type="password" defaultValue="secret" />);
    const field = screen.getByLabelText("Password");
    expect(field.getAttribute("type")).toBe("password");
    fireEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(field.getAttribute("type")).toBe("text");
    fireEvent.click(screen.getByRole("button", { name: "Hide password" }));
    expect(field.getAttribute("type")).toBe("password");
  });
});

describe("Landing", () => {
  function renderLanding(status) {
    return render(
      <AuthContext.Provider value={{ status, user: null, profile: null }}>
        <MemoryRouter initialEntries={["/"]}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/dashboard" element={<p>Dashboard page</p>} />
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    );
  }

  it("shows the product page to visitors", () => {
    renderLanding("unauthenticated");
    expect(screen.getByRole("heading", { level: 1, name: /Turn lectures into knowledge/ })).toBeTruthy();
    expect(screen.getAllByRole("link", { name: /Get Started/ })[0].getAttribute("href")).toBe("/signup");
  });

  it("stays readable for signed-in users, with every call to action pointing to their dashboard", () => {
    renderLanding("authenticated");
    expect(screen.getByRole("heading", { level: 1, name: /Turn lectures into knowledge/ })).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Log In/ })).toBeNull();
    const ctas = screen.getAllByRole("link", { name: /Go to Dashboard/ });
    expect(ctas.length).toBeGreaterThanOrEqual(3);
    ctas.forEach((link) => expect(link.getAttribute("href")).toBe("/dashboard"));
    expect(screen.queryByRole("link", { name: /Get Started/ })).toBeNull();
  });
});
