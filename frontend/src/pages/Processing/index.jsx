import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import PageContainer from "../../components/layout/PageContainer";
import Button from "../../components/ui/Button";
import EmptyState from "../../components/ui/EmptyState";
import ErrorState from "../../components/ui/ErrorState";
import Skeleton from "../../components/ui/Skeleton";
import { AlertIcon, CheckIcon } from "../../components/ui/icons";
import { SourceBadge, StatusBadge } from "../../components/lectures/LectureBadges";
import RetryButton from "../../components/lectures/RetryButton";
import { useAsyncData } from "../../hooks/useAsyncData";
import { getProcessingDetails } from "../../services/ingestion";
import { PIPELINE_STAGES, isActive, statusInfo } from "../../lectures/lectureStatus";
import { formatDate, formatDuration, formatFileSize } from "../../utils/format";
import "./Processing.css";

const POLL = { intervalMs: 3000, while: (data) => isActive({ ...data?.lecture, job: data?.job }) };

function formatMs(ms) {
  if (ms === null || ms === undefined) return null;
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

/** Derives each pipeline stage's state from the persisted job and its stage runs. */
function stageStates(job, runs, implemented) {
  const current = PIPELINE_STAGES.findIndex((item) => item.stage === job?.current_stage);
  return PIPELINE_STAGES.map((item, index) => {
    const lastRun = [...runs].reverse().find((run) => run.stage === item.stage);
    let state = "pending";
    if (job?.status === "succeeded" || index < current) state = "done";
    else if (index === current) {
      state = { running: "active", queued: "queued", waiting: "unavailable", failed: "failed" }[job.status] ?? "pending";
    }
    return {
      ...item,
      state,
      implemented: implemented.includes(item.stage),
      duration: lastRun?.status === "succeeded" ? formatMs(lastRun.duration_ms) : null,
    };
  });
}

function ProcessingSkeleton() {
  return (
    <PageContainer>
      <span className="visually-hidden" role="status">
        Loading processing status…
      </span>
      <div className="processing-skeleton" aria-hidden="true">
        <Skeleton width={120} height={12} />
        <Skeleton width="min(560px, 90%)" height={30} />
        <Skeleton width={240} height={14} />
        <div className="processing-skeleton__card">
          {[0, 1, 2, 3, 4, 5, 6].map((key) => (
            <div key={key} className="processing-skeleton__row">
              <Skeleton width={28} height={28} radius={999} />
              <Skeleton width={`${40 + ((key * 11) % 30)}%`} height={14} />
            </div>
          ))}
        </div>
      </div>
    </PageContainer>
  );
}

export default function Processing() {
  const { id } = useParams();
  const [showDetails, setShowDetails] = useState(false);
  const details = useAsyncData((options) => getProcessingDetails(id, options), [id], { poll: POLL });

  if (details.status === "loading" && !details.data) return <ProcessingSkeleton />;

  if (details.status === "error") {
    const missing = details.error.status === 404 || details.error.status === 422;
    return (
      <PageContainer>
        {missing ? (
          <EmptyState
            title="Lecture not found"
            description="This lecture doesn't exist, was deleted, or isn't in your library."
            action={
              <Button as={Link} to="/library">
                Back to Library
              </Button>
            }
          />
        ) : (
          <ErrorState title="We couldn't load the processing status." error={details.error} onRetry={details.reload} />
        )}
      </PageContainer>
    );
  }

  const { lecture, job, stage_runs: runs, media, implemented_stages: implemented } = details.data;
  const info = statusInfo(lecture.status, job);
  const stages = stageStates(job, runs, implemented);
  const currentStage = stages.find((stage) => ["active", "queued", "unavailable", "failed"].includes(stage.state));
  const original = media.find((item) => item.kind === "original");

  return (
    <PageContainer className="processing">
      <nav className="processing__crumbs" aria-label="Breadcrumb">
        <Link to="/library">Lecture Library</Link> <span aria-hidden="true">/</span> <span>Processing</span>
      </nav>

      <header className="processing-header">
        <div className="processing-header__badges">
          <StatusBadge status={lecture.status} job={job} />
          <SourceBadge sourceType={lecture.source_type} />
        </div>
        <h1 className="processing-header__title">{lecture.title}</h1>
        {lecture.source_url && (
          <p className="processing-header__source mono">
            Source:{" "}
            <a href={lecture.source_url} target="_blank" rel="noreferrer noopener">
              {lecture.source_url}
            </a>
          </p>
        )}
      </header>

      {job?.status === "failed" && (
        <section className="processing-failure" role="alert">
          <AlertIcon size={20} />
          <div className="processing-failure__body">
            <h2>{currentStage ? `${currentStage.label} couldn't be completed` : "Processing couldn't be completed"}</h2>
            <p>{job.error_message}</p>
            {!job.retryable && (
              <p className="processing-failure__hint">
                Retrying won&apos;t fix this. Delete the lecture and add a working file or link.
              </p>
            )}
            <div className="processing-failure__actions">
              {job.retryable && <RetryButton lecture={lecture} onRetried={details.reload} />}
              <Button variant="tertiary" onClick={() => setShowDetails((value) => !value)} aria-expanded={showDetails}>
                {showDetails ? "Hide details" : "Details"}
              </Button>
            </div>
            {showDetails && (
              <dl className="processing-failure__details mono">
                <dt>Error code</dt>
                <dd>{job.error_code}</dd>
                <dt>Attempts</dt>
                <dd>{job.attempt_count}</dd>
                <dt>Failed at</dt>
                <dd>{new Date(job.failed_at).toLocaleString()}</dd>
              </dl>
            )}
          </div>
        </section>
      )}

      {job && job.status !== "failed" && (
        <p className={`processing-activity ${info.waiting ? "processing-activity--waiting" : ""}`} role="status">
          {job.status === "running" && currentStage
            ? job.status_detail || `${currentStage.activity}…`
            : job.status_detail || info.label}
        </p>
      )}

      <section className="processing-stages" aria-labelledby="stages-heading">
        <h2 id="stages-heading" className="visually-hidden">
          Processing stages
        </h2>
        <ol>
          <li className="processing-stage processing-stage--done">
            <StageMarker state="done" />
            <span className="processing-stage__label">{lecture.source_type === "url" ? "Source added" : "Upload complete"}</span>
          </li>
          {stages.map((stage) => (
            <li key={stage.stage} className={`processing-stage processing-stage--${stage.state}`}>
              <StageMarker state={stage.state} />
              <span className="processing-stage__label">{stage.label}</span>
              <span className="processing-stage__meta mono">
                {stage.duration ??
                  (stage.state === "active"
                    ? "In progress"
                    : stage.state === "queued"
                      ? "Queued"
                      : stage.state === "failed"
                        ? "Failed"
                        : !stage.implemented
                          ? "Not available yet"
                          : "")}
              </span>
            </li>
          ))}
          <li className={`processing-stage processing-stage--${lecture.status === "READY" ? "done" : "pending"}`}>
            <StageMarker state={lecture.status === "READY" ? "done" : "pending"} />
            <span className="processing-stage__label">Ready</span>
          </li>
        </ol>
      </section>

      {(original || job) && (
        <section className="processing-facts" aria-labelledby="facts-heading">
          <h2 id="facts-heading" className="processing-facts__title">
            Media
          </h2>
          <dl>
            {original && (
              <>
                <dt>Uploaded file</dt>
                <dd>
                  {original.mime_type} · {formatFileSize(original.file_size)}
                  {original.duration_seconds ? ` · ${formatDuration(original.duration_seconds)}` : ""}
                </dd>
              </>
            )}
            {lecture.duration_seconds ? (
              <>
                <dt>Duration</dt>
                <dd>{formatDuration(lecture.duration_seconds)}</dd>
              </>
            ) : null}
            {job?.queued_at && (
              <>
                <dt>Submitted</dt>
                <dd>{formatDate(job.queued_at)}</dd>
              </>
            )}
          </dl>
        </section>
      )}

      <div className="processing-actions">
        <Button as={Link} to="/library" variant="secondary">
          Back to Library
        </Button>
        {lecture.status === "READY" && (
          <Button as={Link} to={`/lectures/${lecture.id}`}>
            Open Workspace
          </Button>
        )}
      </div>
    </PageContainer>
  );
}

function StageMarker({ state }) {
  if (state === "done") {
    return (
      <span className="processing-stage__marker" aria-label="Completed">
        <CheckIcon size={14} />
      </span>
    );
  }
  if (state === "failed") {
    return (
      <span className="processing-stage__marker" aria-label="Failed">
        <AlertIcon size={14} />
      </span>
    );
  }
  const labels = { active: "In progress", queued: "Queued", unavailable: "Waiting", pending: "Not started" };
  return <span className="processing-stage__marker" aria-label={labels[state]} />;
}
