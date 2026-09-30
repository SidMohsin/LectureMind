import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { AuthContext } from "./AuthContext";
import ProtectedRoute from "./ProtectedRoute";
import PublicOnlyRoute from "./PublicOnlyRoute";

function LoginProbe() {
  const location = useLocation();
  return (
    <p>
      login page · from={location.state?.from?.pathname ?? "none"} · reason={location.state?.reason ?? "none"}
    </p>
  );
}

function renderAt(path, auth) {
  return render(
    <AuthContext.Provider value={{ signOutReason: null, ...auth }}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<PublicOnlyRoute />}>
            <Route path="/login" element={<LoginProbe />} />
          </Route>
          <Route element={<ProtectedRoute />}>
            <Route path="/dashboard" element={<p>dashboard content</p>} />
            <Route path="/library" element={<p>library content</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

describe("ProtectedRoute", () => {
  it("shows neither protected content nor login while the session is resolving", () => {
    renderAt("/library", { status: "loading" });
    expect(screen.getByRole("status")).toBeTruthy();
    expect(screen.queryByText("library content")).toBeNull();
    expect(screen.queryByText(/login page/)).toBeNull();
  });

  it("redirects signed-out visitors to login and remembers where they were going", () => {
    renderAt("/library", { status: "unauthenticated" });
    expect(screen.queryByText("library content")).toBeNull();
    expect(screen.getByText(/login page · from=\/library · reason=none/)).toBeTruthy();
  });

  it("tells the login page when a session expired", () => {
    renderAt("/library", { status: "unauthenticated", signOutReason: "expired" });
    expect(screen.getByText(/reason=expired/)).toBeTruthy();
  });

  it("does not bounce back to the old page after a deliberate logout", () => {
    renderAt("/library", { status: "unauthenticated", signOutReason: "signed_out" });
    expect(screen.getByText(/from=none · reason=signed_out/)).toBeTruthy();
  });

  it("renders protected content for a signed-in user", () => {
    renderAt("/library", { status: "authenticated" });
    expect(screen.getByText("library content")).toBeTruthy();
  });
});

describe("PublicOnlyRoute", () => {
  it("shows the login page to signed-out visitors", () => {
    renderAt("/login", { status: "unauthenticated" });
    expect(screen.getByText(/login page/)).toBeTruthy();
  });

  it("sends a signed-in user to the dashboard", () => {
    renderAt("/login", { status: "authenticated" });
    expect(screen.getByText("dashboard content")).toBeTruthy();
  });
});
