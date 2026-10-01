/**
 * Links into the lecture workspace that preserve where the user came from.
 * `t` positions the player and transcript (seconds); `question` reopens a Q&A answer.
 */
export function lectureLink(lectureId, { seconds, question, from } = {}) {
  const params = new URLSearchParams();
  if (seconds !== undefined && seconds !== null) params.set("t", String(Math.floor(seconds)));
  if (question) params.set("question", question);
  if (from) params.set("from", from);
  const query = params.toString();
  return `/lectures/${lectureId}${query ? `?${query}` : ""}`;
}
