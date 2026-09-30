import { api } from "./api";

export function listLectures({ q, subject, status, sourceType, sort, limit, offset } = {}, options) {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (subject) params.set("subject", subject);
  if (status) params.set("status", status);
  if (sourceType) params.set("source_type", sourceType);
  if (sort) params.set("sort", sort);
  if (limit) params.set("limit", String(limit));
  if (offset) params.set("offset", String(offset));
  const query = params.toString();
  return api.get(`/lectures${query ? `?${query}` : ""}`, options);
}

export function listSubjects(options) {
  return api.get("/lectures/subjects", options);
}

export function getLecture(id, options) {
  return api.get(`/lectures/${encodeURIComponent(id)}`, options);
}

export function deleteLecture(id) {
  return api.delete(`/lectures/${encodeURIComponent(id)}`);
}
