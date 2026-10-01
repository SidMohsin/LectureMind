import { api } from "./api";

/** Passages from the user's own lectures that match a query by meaning (pgvector). */
export function searchContent(query, { limit } = {}, options) {
  const params = new URLSearchParams({ q: query });
  if (limit) params.set("limit", String(limit));
  return api.get(`/search/content?${params}`, options);
}
