/**
 * All Supabase Auth operations used by the auth screens. Pages call these
 * instead of the Supabase client directly; failures surface as AuthFailure
 * with a user-facing message.
 */
import { supabase } from "../lib/supabase";
import { AuthFailure } from "../auth/authErrors";

const appUrl = (path) => `${window.location.origin}${path}`;

function unwrap({ data, error }) {
  if (error) throw new AuthFailure(error);
  return data;
}

export async function signUp({ fullName, email, password }) {
  const data = unwrap(
    await supabase.auth.signUp({
      email: email.trim(),
      password,
      options: { emailRedirectTo: appUrl("/verify"), data: { full_name: fullName.trim() } },
    })
  );

  // With email confirmation on, Supabase answers a sign-up for an existing
  // address with a placeholder user that has no identities.
  if (data.user && data.user.identities?.length === 0) {
    throw new AuthFailure({ code: "user_already_exists" });
  }

  return { needsVerification: !data.session };
}

export async function signIn({ email, password }) {
  unwrap(await supabase.auth.signInWithPassword({ email: email.trim(), password }));
}

export async function resendVerification(email) {
  unwrap(
    await supabase.auth.resend({
      type: "signup",
      email: email.trim(),
      options: { emailRedirectTo: appUrl("/verify") },
    })
  );
}

export async function requestPasswordReset(email) {
  unwrap(await supabase.auth.resetPasswordForEmail(email.trim(), { redirectTo: appUrl("/reset-password") }));
}

export async function updatePassword(password) {
  unwrap(await supabase.auth.updateUser({ password }));
}
