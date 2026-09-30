import { describe, expect, it } from "vitest";
import { AuthFailure, authErrorMessage } from "./authErrors";

describe("authErrorMessage", () => {
  it("maps known Supabase error codes to user-facing text", () => {
    expect(authErrorMessage({ code: "invalid_credentials", message: "Invalid login credentials" })).toBe(
      "Incorrect email or password."
    );
    expect(authErrorMessage({ code: "email_not_confirmed" })).toMatch(/verify your email/);
    expect(authErrorMessage({ code: "over_email_send_rate_limit" })).toMatch(/wait a few minutes/);
  });

  it("never leaks unknown provider messages", () => {
    expect(authErrorMessage({ code: "unexpected_failure", message: "pq: relation does not exist" })).toBe(
      "Something went wrong. Please try again."
    );
  });

  it("reports network failures distinctly", () => {
    expect(authErrorMessage({ name: "AuthRetryableFetchError", status: 0 })).toMatch(/couldn't reach the server/);
  });

  it("AuthFailure carries the mapped message and code", () => {
    const failure = new AuthFailure({ code: "user_already_exists" });
    expect(failure.code).toBe("user_already_exists");
    expect(failure.message).toMatch(/already exists/);
  });
});
