import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";

const listeners = vi.hoisted(() => []);
const auth = vi.hoisted(() => ({
  onAuthStateChange: vi.fn((callback) => {
    listeners.push(callback);
    return { data: { subscription: { unsubscribe: vi.fn() } } };
  }),
  signOut: vi.fn(),
}));
const getMe = vi.hoisted(() => vi.fn());

vi.mock("../lib/supabase", () => ({ supabase: { auth } }));
vi.mock("../services/account", () => ({ getMe }));

const { default: AuthProvider } = await import("./AuthProvider");
const { useAuth } = await import("./AuthContext");

function Probe() {
  const { status, user, profile, signOutReason, signOut } = useAuth();
  return (
    <>
      <p>status={status}</p>
      <p>user={user?.email ?? "none"}</p>
      <p>profile={profile?.display_name ?? "none"}</p>
      <p>reason={signOutReason ?? "none"}</p>
      <button onClick={signOut}>sign out</button>
    </>
  );
}

const session = { user: { id: "user-1", email: "alex@example.com" }, access_token: "t" };
const emit = (event, value) => act(() => listeners.at(-1)(event, value));

beforeEach(() => {
  listeners.length = 0;
  getMe.mockResolvedValue({ display_name: "Alex Chen" });
  auth.signOut.mockImplementation(async () => {
    emit("SIGNED_OUT", null);
    return { error: null };
  });
  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>
  );
});

describe("AuthProvider", () => {
  it("stays loading until Supabase reports the restored session", () => {
    expect(screen.getByText("status=loading")).toBeTruthy();
  });

  it("restores a stored session and loads the profile", async () => {
    emit("INITIAL_SESSION", session);
    expect(screen.getByText("status=authenticated")).toBeTruthy();
    expect(screen.getByText("user=alex@example.com")).toBeTruthy();
    await waitFor(() => expect(screen.getByText("profile=Alex Chen")).toBeTruthy());
  });

  it("resolves to unauthenticated when there is no stored session", () => {
    emit("INITIAL_SESSION", null);
    expect(screen.getByText("status=unauthenticated")).toBeTruthy();
    expect(getMe).not.toHaveBeenCalled();
  });

  it("marks a deliberate logout as signed_out", async () => {
    emit("INITIAL_SESSION", session);
    await act(() => screen.getByText("sign out").click());
    expect(screen.getByText("status=unauthenticated")).toBeTruthy();
    expect(screen.getByText("reason=signed_out")).toBeTruthy();
    expect(screen.getByText("profile=none")).toBeTruthy();
  });

  it("marks an unrequested sign-out (failed refresh) as expired", () => {
    emit("INITIAL_SESSION", session);
    emit("SIGNED_OUT", null);
    expect(screen.getByText("reason=expired")).toBeTruthy();
  });

  it("clears the logout reason when the user signs in again", () => {
    emit("INITIAL_SESSION", session);
    emit("SIGNED_OUT", null);
    emit("SIGNED_IN", session);
    expect(screen.getByText("reason=none")).toBeTruthy();
  });

  it("falls back to local sign-out when the server can't be reached", async () => {
    auth.signOut.mockResolvedValueOnce({ error: { name: "AuthRetryableFetchError" } });
    emit("INITIAL_SESSION", session);
    await act(() => screen.getByText("sign out").click());
    expect(auth.signOut).toHaveBeenLastCalledWith({ scope: "local" });
  });
});
