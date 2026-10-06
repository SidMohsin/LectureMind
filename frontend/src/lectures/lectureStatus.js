/**
 * The processing lifecycle from the architecture document. Everything shown is
 * derived from persisted state (lecture.status + its processing job), never
 * estimated: no percentages or time remaining.
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

// Stage names used on processing_jobs.current_stage (the pipeline itself).
export const PIPELINE_STAGES = [
  { stage: "EXTRACTING_AUDIO", label: "Audio extraction", activity: "Extracting and normalizing the lecture audio" },
  { stage: "TRANSCRIBING", label: "Transcription", activity: "Transcribing speech with timestamps" },
  { stage: "CLEANING", label: "Transcript cleaning", activity: "Cleaning the transcript" },
  { stage: "CHUNKING", label: "Semantic chunking", activity: "Splitting the transcript into sections" },
  { stage: "EMBEDDING", label: "Embedding", activity: "Creating search embeddings" },
  { stage: "INDEXING", label: "Indexing", activity: "Indexing the lecture for search" },
  { stage: "GENERATING_INTELLIGENCE", label: "Lecture intelligence", activity: "Generating summary, chapters and concepts" },
];

export function stageLabel(stage) {
  return PIPELINE_STAGES.find((item) => item.stage === stage)?.label ?? stage;
}

/** Whether the lecture is still moving on its own (worth polling for updates). */
export function isActive(lecture) {
  const job = lecture?.job;
  return job ? job.status === "queued" || job.status === "running" : lecture?.status === "UPLOADED";
}

export function statusInfo(status, job) {
  if (status === "READY") return { group: "ready", tone: "success", label: "Ready" };
  if (status === "FAILED") {
    return { group: "failed", tone: "error", label: "Failed", message: job?.error_message, retryable: job?.retryable === true };
  }

  const index = PROCESSING_STAGES.findIndex((stage) => stage.status === status);
  const position = index === -1 ? {} : { stage: index + 1, totalStages: PROCESSING_STAGES.length };

  if (job?.status === "waiting") {
    return {
      group: "processing",
      tone: "neutral",
      waiting: true,
      label: `Waiting: ${stageLabel(job.current_stage)} isn't available yet`,
      badge: "Waiting",
      ...position,
    };
  }
  if (job?.status === "queued" && job.error_code) {
    return {
      group: "processing",
      tone: "warning",
      label: "Retrying after a temporary problem",
      badge: "Retrying",
      ...position,
    };
  }
  if (status === "UPLOADED") return { group: "processing", tone: "info", label: "Uploaded · waiting to process" };
  if (index === -1) return { group: "processing", tone: "info", label: "Processing" };
  return { group: "processing", tone: "info", label: `Processing: ${PROCESSING_STAGES[index].label}`, ...position };
}

export const SOURCE_TYPE_LABELS = {
  video: "Video",
  audio: "Audio",
  url: "YouTube",
};

/** Where "open" should take the user for a lecture in this state. */
export function lecturePath(lecture) {
  return statusInfo(lecture.status).group === "ready"
    ? `/lectures/${lecture.id}`
    : `/lectures/${lecture.id}/processing`;
}
