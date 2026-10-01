import { api } from "./api";

const base = (id) => `/lectures/${encodeURIComponent(id)}`;

export function getWorkspace(id, options) {
  return api.get(`${base(id)}/workspace`, options);
}

/** A short-lived signed URL for the lecture's private media (never a public URL). */
export function getMedia(id, options) {
  return api.get(`${base(id)}/media`, options);
}

export function listQuestions(id, options) {
  return api.get(`${base(id)}/questions`, options);
}

export function askQuestion(id, question, options) {
  return api.post(`${base(id)}/questions`, { question }, options);
}
