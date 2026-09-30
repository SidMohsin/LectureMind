/**
 * Converts Supabase Auth errors into messages suitable for users. Raw provider
 * messages are never shown directly.
 */

const MESSAGES = {
  invalid_credentials: "Incorrect email or password.",
  email_not_confirmed: "Please verify your email address before logging in.",
  user_already_exists: "An account with this email already exists. Try logging in instead.",
  email_exists: "An account with this email already exists. Try logging in instead.",
  weak_password: "That password is too weak. Use at least 8 characters.",
  same_password: "Choose a password that's different from your current one.",
  email_address_invalid: "Enter a valid email address.",
  email_address_not_authorized: "We can't send email to this address right now. Please contact support.",
  over_email_send_rate_limit: "Too many emails requested. Please wait a few minutes and try again.",
  over_request_rate_limit: "Too many attempts. Please wait a moment and try again.",
  signup_disabled: "New sign-ups are currently disabled.",
  otp_expired: "This link is invalid or has expired.",
  access_denied: "This link is invalid or has expired.",
  session_not_found: "Your session has expired. Please start again.",
  session_expired: "Your session has expired. Please start again.",
  refresh_token_not_found: "Your session has expired. Please start again.",
  validation_failed: "Please check the details you entered.",
};

const NETWORK_MESSAGE = "We couldn't reach the server. Check your connection and try again.";
const FALLBACK_MESSAGE = "Something went wrong. Please try again.";

export function authErrorMessage(error) {
  if (error?.code && MESSAGES[error.code]) return MESSAGES[error.code];
  if (error?.name === "AuthRetryableFetchError" || error?.status === 0) return NETWORK_MESSAGE;
  return FALLBACK_MESSAGE;
}

export class AuthFailure extends Error {
  constructor(error) {
    super(authErrorMessage(error));
    this.name = "AuthFailure";
    this.code = error?.code ?? null;
  }
}
