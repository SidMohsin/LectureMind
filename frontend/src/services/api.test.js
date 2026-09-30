import { beforeEach, describe, expect, it, vi } from "vitest";

const auth = vi.hoisted(() => ({
  getSession: vi.fn(),
  refreshSession: vi.fn(),
  signOut: vi.fn(),
}));

vi.mock("../lib/supabase", () => ({ supabase: { auth } }));

const { api, ApiError } = await import("./api");

const session = (token) => ({ data: { session: token ? { access_token: token } : null } });
const json = (status, body) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

let fetchMock;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  auth.getSession.mockResolvedValue(session("token-1"));
  auth.refreshSession.mockResolvedValue(session("token-2"));
  auth.signOut.mockResolvedValue({ error: null });
});

describe("api client", () => {
  it("sends the current access token on authenticated requests", async () => {
    fetchMock.mockResolvedValue(json(200, { id: "u1" }));

    await expect(api.get("/me")).resolves.toEqual({ id: "u1" });
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer token-1");
  });

  it("omits the token for public requests", async () => {
    fetchMock.mockResolvedValue(json(200, { status: "ok" }));

    await api.get("/health", { auth: false });
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBeUndefined();
    expect(auth.getSession).not.toHaveBeenCalled();
  });

  it("refreshes the session and retries once when the token was rejected", async () => {
    fetchMock.mockResolvedValueOnce(json(401, { message: "expired" })).mockResolvedValueOnce(json(200, { ok: true }));

    await expect(api.get("/me")).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][1].headers.Authorization).toBe("Bearer token-2");
    expect(auth.signOut).not.toHaveBeenCalled();
  });

  it("ends the local session when the refreshed token is also rejected", async () => {
    fetchMock.mockResolvedValue(json(401, { message: "expired" }));

    const error = await api.get("/me").catch((caught) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(401);
    expect(error.message).toMatch(/session has expired/);
    expect(auth.signOut).toHaveBeenCalledWith({ scope: "local" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("reports authorization failures without signing the user out", async () => {
    fetchMock.mockResolvedValue(json(403, { message: "forbidden" }));

    const error = await api.get("/lectures/x").catch((caught) => caught);
    expect(error.status).toBe(403);
    expect(error.message).toBe("You don't have permission to do that.");
    expect(auth.signOut).not.toHaveBeenCalled();
  });

  it("surfaces the backend's safe error message", async () => {
    fetchMock.mockResolvedValue(json(404, { message: "Profile not found.", code: "http_error" }));

    const error = await api.get("/me").catch((caught) => caught);
    expect(error.status).toBe(404);
    expect(error.message).toBe("Profile not found.");
  });

  it("turns network failures into a readable error", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    const error = await api.get("/me").catch((caught) => caught);
    expect(error.status).toBe(0);
    expect(error.message).toMatch(/Unable to reach the server/);
  });
});
