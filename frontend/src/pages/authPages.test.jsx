import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthContext } from "../auth/AuthContext";
import { AuthFailure } from "../auth/authErrors";

const authService = vi.hoisted(() => ({
  signIn: vi.fn(),
  signUp: vi.fn(),
  resendVerification: vi.fn(),
  requestPasswordReset: vi.fn(),
  updatePassword: vi.fn(),
}));
const redirect = vi.hoisted(() => ({ current: null }));

vi.mock("../services/auth", () => authService);
vi.mock("../lib/supabase", () => ({
  authRedirectFor: (pathname) => (redirect.current?.pathname === pathname ? redirect.current : null),
}));

const { default: Login } = await import("./Login");
const { default: Signup } = await import("./Signup");
const { default: Verify } = await import("./Verify");
const { default: ForgotPassword } = await import("./ForgotPassword");
const { default: ResetPassword } = await import("./ResetPassword");

function renderPage(path, { status = "unauthenticated", state } = {}) {
  return render(
    <AuthContext.Provider value={{ status }}>
      <MemoryRouter initialEntries={[{ pathname: path, state }]}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/verify" element={<Verify />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

const type = (label, value) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
const click = (name) => fireEvent.click(screen.getByRole("button", { name }));

beforeEach(() => {
  redirect.current = null;
  Object.values(authService).forEach((fn) => fn.mockReset());
});

describe("Login", () => {
  it("validates before contacting Supabase", async () => {
    renderPage("/login");
    click("Log In");
    expect(await screen.findByText("Enter your email address.")).toBeTruthy();
    expect(screen.getByText("Enter your password.")).toBeTruthy();
    expect(authService.signIn).not.toHaveBeenCalled();
  });

  it("shows a clear message for wrong credentials", async () => {
    authService.signIn.mockRejectedValue(new AuthFailure({ code: "invalid_credentials" }));
    renderPage("/login");
    type("Email", "alex@example.com");
    type("Password", "wrong-password");
    click("Log In");
    expect(await screen.findByText("Incorrect email or password.")).toBeTruthy();
    expect(authService.signIn).toHaveBeenCalledWith({ email: "alex@example.com", password: "wrong-password" });
  });

  it("offers to resend verification when the email isn't confirmed", async () => {
    authService.signIn.mockRejectedValue(new AuthFailure({ code: "email_not_confirmed" }));
    renderPage("/login");
    type("Email", "alex@example.com");
    type("Password", "password123");
    click("Log In");
    expect(await screen.findByRole("link", { name: "Resend verification email" })).toBeTruthy();
  });

  it("explains an expired session", () => {
    renderPage("/login", { state: { reason: "expired" } });
    expect(screen.getByText("Your session has expired. Please log in again.")).toBeTruthy();
  });
});

describe("Signup", () => {
  function fillValid() {
    type("Full name", "Alex Chen");
    type("Email", "alex@example.com");
    type("Password", "long-enough-pw");
    type("Confirm password", "long-enough-pw");
  }

  it("rejects short and mismatched passwords", async () => {
    renderPage("/signup");
    type("Full name", "Alex");
    type("Email", "alex@example.com");
    type("Password", "short");
    type("Confirm password", "different");
    click("Create Account");
    expect(await screen.findByText("Use at least 8 characters.")).toBeTruthy();
    expect(screen.getByText("Passwords don't match.")).toBeTruthy();
    expect(authService.signUp).not.toHaveBeenCalled();
  });

  it("moves to the check-your-inbox state when verification is required", async () => {
    authService.signUp.mockResolvedValue({ needsVerification: true });
    renderPage("/signup");
    fillValid();
    click("Create Account");
    expect(await screen.findByText("Check your inbox")).toBeTruthy();
    expect(screen.getByText(/alex@example.com/)).toBeTruthy();
  });

  it("reports an already-registered email", async () => {
    authService.signUp.mockRejectedValue(new AuthFailure({ code: "user_already_exists" }));
    renderPage("/signup");
    fillValid();
    click("Create Account");
    expect(await screen.findByText(/already exists/)).toBeTruthy();
  });
});

describe("Verify", () => {
  it("shows an expired-link state with a way to get a new link", () => {
    redirect.current = { pathname: "/verify", hasSession: false, errorCode: "otp_expired" };
    renderPage("/verify");
    expect(screen.getByText("This link has expired")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Send verification email" })).toBeTruthy();
  });

  it("confirms verification once the link produced a session", () => {
    redirect.current = { pathname: "/verify", hasSession: true, type: "signup", errorCode: null };
    renderPage("/verify", { status: "authenticated" });
    expect(screen.getByText("Email verified")).toBeTruthy();
  });

  it("only reports success for a resend that actually succeeded", async () => {
    authService.resendVerification.mockRejectedValue(new AuthFailure({ code: "over_email_send_rate_limit" }));
    renderPage("/verify", { state: { email: "alex@example.com", justSignedUp: true } });
    click("Send verification email");
    expect(await screen.findByText(/Too many emails requested/)).toBeTruthy();
    expect(screen.queryByText(/We sent a new verification link/)).toBeNull();
  });
});

describe("ForgotPassword", () => {
  it("confirms only after Supabase accepted the request", async () => {
    authService.requestPasswordReset.mockResolvedValue();
    renderPage("/forgot-password");
    type("Email", "alex@example.com");
    click("Send Reset Link");
    expect(await screen.findByText("Check your email")).toBeTruthy();
    expect(authService.requestPasswordReset).toHaveBeenCalledWith("alex@example.com");
  });
});

describe("ResetPassword", () => {
  it("refuses to show the form without a recovery link, even when signed in", () => {
    renderPage("/reset-password", { status: "authenticated" });
    expect(screen.getByText("Open your reset link")).toBeTruthy();
    expect(screen.queryByLabelText("New password")).toBeNull();
  });

  it("explains an expired recovery link", () => {
    redirect.current = { pathname: "/reset-password", hasSession: false, errorCode: "otp_expired" };
    renderPage("/reset-password");
    expect(screen.getByText("This reset link has expired")).toBeTruthy();
  });

  it("updates the password from a valid recovery link", async () => {
    redirect.current = { pathname: "/reset-password", hasSession: true, type: "recovery", errorCode: null };
    authService.updatePassword.mockResolvedValue();
    renderPage("/reset-password", { status: "authenticated" });
    type("New password", "a-new-password");
    type("Confirm new password", "a-new-password");
    click("Update Password");
    expect(await screen.findByText("Password updated")).toBeTruthy();
    expect(authService.updatePassword).toHaveBeenCalledWith("a-new-password");
  });
});
