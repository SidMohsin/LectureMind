import { describe, expect, it } from "vitest";
import { readAuthRedirect } from "./authRedirect";

const at = (href) => new URL(href, "http://localhost:5173");

describe("readAuthRedirect", () => {
  it("returns null for ordinary page loads", () => {
    expect(readAuthRedirect(at("/verify"))).toBeNull();
    expect(readAuthRedirect(at("/login?next=/library"))).toBeNull();
  });

  it("recognises a successful verification link", () => {
    const result = readAuthRedirect(at("/verify#access_token=abc&refresh_token=def&type=signup"));
    expect(result).toEqual({ pathname: "/verify", type: "signup", hasSession: true, errorCode: null });
  });

  it("recognises a recovery link", () => {
    const result = readAuthRedirect(at("/reset-password#access_token=abc&type=recovery"));
    expect(result.type).toBe("recovery");
    expect(result.hasSession).toBe(true);
  });

  it("reads expired-link errors from the fragment or the query string", () => {
    const fragment = readAuthRedirect(
      at("/verify#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid")
    );
    expect(fragment).toMatchObject({ hasSession: false, errorCode: "otp_expired" });

    const query = readAuthRedirect(at("/reset-password?error=access_denied"));
    expect(query).toMatchObject({ pathname: "/reset-password", errorCode: "access_denied" });
  });
});
