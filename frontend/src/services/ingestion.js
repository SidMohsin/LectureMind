import { api } from "./api";

export function getIngestionLimits(options) {
  return api.get("/ingestion/limits", options);
}

/**
 * Uploads a lecture file with its metadata. `idempotencyKey` identifies this one
 * submission, so a network retry can never create a second lecture.
 */
export function uploadLecture({ kind, file, details, idempotencyKey, onProgress, signal }) {
  const form = new FormData();
  form.append("kind", kind);
  form.append("title", details.title);
  form.append("subject", details.subject);
  if (details.topic) form.append("topic", details.topic);
  if (details.instructor) form.append("instructor", details.instructor);
  if (details.lectureDate) form.append("lecture_date", details.lectureDate);
  details.tags.forEach((tag) => form.append("tags", tag));
  form.append("file", file);
  return api.upload("/lectures/uploads", form, {
    headers: { "Idempotency-Key": idempotencyKey },
    onUploadProgress: onProgress,
    signal,
  });
}

export function submitSourceUrl({ url, details, rightsConfirmed, idempotencyKey }) {
  return api.post(
    "/lectures/sources",
    {
      url,
      title: details.title || null,
      subject: details.subject,
      topic: details.topic || null,
      instructor: details.instructor || null,
      lecture_date: details.lectureDate || null,
      tags: details.tags,
      rights_confirmed: rightsConfirmed,
    },
    { headers: { "Idempotency-Key": idempotencyKey } }
  );
}

export function retryProcessing(lectureId) {
  return api.post(`/lectures/${encodeURIComponent(lectureId)}/retry`);
}

export function getProcessingDetails(lectureId, options) {
  return api.get(`/lectures/${encodeURIComponent(lectureId)}/processing`, options);
}
