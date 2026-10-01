import { api } from "./api";

/** The user's questions across lectures, newest first by default. */
export function listHistory({ q, lectureId, order, limit, offset } = {}, options) {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (lectureId) params.set("lecture_id", lectureId);
  if (order) params.set("order", order);
  if (limit) params.set("limit", String(limit));
  if (offset) params.set("offset", String(offset));
  const query = params.toString();
  return api.get(`/questions${query ? `?${query}` : ""}`, options);
}

export function deleteQuestion(id) {
  return api.delete(`/questions/${encodeURIComponent(id)}`);
}

export function clearLectureQuestions(lectureId) {
  return api.delete(`/lectures/${encodeURIComponent(lectureId)}/questions`);
}
