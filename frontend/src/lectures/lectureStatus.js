/**
 * The processing lifecycle from the architecture document. Stage numbers are
 * derived from the real `status` column, never estimated.
 */
export const PROCESSING_STAGES = [
  { status: "QUEUED", label: "Queued" },
  { status: "EXTRACTING_AUDIO", label: "Extracting audio" },
  { status: "TRANSCRIBING", label: "Transcribing" },
  { status: "CLEANING", label: "Cleaning transcript" },
  { status: "CHUNKING", label: "Semantic chunking" },
  { status: "EMBEDDING", label: "Embedding" },
  { status: "INDEXING", label: "Indexing" },
  { status: "GENERATING_INTELLIGENCE", label: "Generating intelligence" },
];

export function statusInfo(status) {
  if (status === "READY") return { group: "ready", tone: "success", label: "Ready" };
  if (status === "FAILED") return { group: "failed", tone: "error", label: "Failed" };
  if (status === "UPLOADED") return { group: "processing", tone: "info", label: "Uploaded · waiting to process" };

  const index = PROCESSING_STAGES.findIndex((stage) => stage.status === status);
  if (index === -1) return { group: "processing", tone: "info", label: "Processing" };
  return {
    group: "processing",
    tone: "info",
    label: `Processing: ${PROCESSING_STAGES[index].label}`,
    stage: index + 1,
    totalStages: PROCESSING_STAGES.length,
  };
}

export const SOURCE_TYPE_LABELS = {
  video: "Video",
  audio: "Audio",
  url: "YouTube URL",
};

/** Where "open" should take the user for a lecture in this state. */
export function lecturePath(lecture) {
  return statusInfo(lecture.status).group === "ready"
    ? `/lectures/${lecture.id}`
    : `/lectures/${lecture.id}/processing`;
}
