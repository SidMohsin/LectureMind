import { useId, useRef, useState } from "react";
import { Link } from "react-router-dom";
import PageContainer from "../../components/layout/PageContainer";
import PageHeader from "../../components/layout/PageHeader";
import Button from "../../components/ui/Button";
import Input from "../../components/ui/Input";
import Alert from "../../components/ui/Alert";
import { ArrowRightIcon, AudioIcon, CheckIcon, LinkIcon, LockIcon, UploadIcon, VideoIcon } from "../../components/ui/icons";
import { useAsyncData } from "../../hooks/useAsyncData";
import { listSubjects } from "../../services/lectures";
import { getIngestionLimits, submitSourceUrl, uploadLecture } from "../../services/ingestion";
import { INPUT_KINDS, parseTags, validateMediaFile, validateSourceUrl } from "../../lectures/lectureInput";
import { formatFileSize } from "../../utils/format";
import "./Upload.css";

const EMPTY_DETAILS = { title: "", subject: "", topic: "", instructor: "", lectureDate: "", tags: "" };

// Mirrors the column constraints on public.lectures (the server enforces them too).
const LIMITS = { title: 300, subject: 120, topic: 200, instructor: 120 };
const MAX_TAGS = 20;
const MAX_TAG_LENGTH = 40;

function validateDetails(details, { titleRequired }) {
  const errors = {};
  if (titleRequired && !details.title.trim()) errors.title = "Enter a lecture title.";
  if (!details.subject.trim()) errors.subject = "Enter the subject or discipline.";
  Object.entries(LIMITS).forEach(([field, max]) => {
    if (details[field].trim().length > max) errors[field] = `Keep this under ${max} characters.`;
  });
  const tags = parseTags(details.tags);
  if (tags.length > MAX_TAGS) errors.tags = `Use at most ${MAX_TAGS} tags.`;
  else if (tags.some((tag) => tag.length > MAX_TAG_LENGTH)) errors.tags = `Keep each tag under ${MAX_TAG_LENGTH} characters.`;
  return errors;
}

function shortSize(bytes) {
  return formatFileSize(bytes).replace(".0 ", " ").replace(" ", "");
}

export default function Upload() {
  const [tab, setTab] = useState("video");
  const [files, setFiles] = useState({ video: null, audio: null });
  const [fileErrors, setFileErrors] = useState({});
  const [sourceUrl, setSourceUrl] = useState("");
  const [urlError, setUrlError] = useState(null);
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [rightsError, setRightsError] = useState(null);
  const [details, setDetails] = useState(EMPTY_DETAILS);
  const [detailErrors, setDetailErrors] = useState({});
  // idle | uploading | checking | done
  const [phase, setPhase] = useState("idle");
  const [progress, setProgress] = useState(null);
  const [submitError, setSubmitError] = useState(null);
  const [result, setResult] = useState(null);
  const abortRef = useRef(null);
  // One key per distinct submission: resubmitting the same thing after a network
  // error can't create a second lecture; changing the input starts a new key.
  const requestKey = useRef(crypto.randomUUID());

  const subjects = useAsyncData((options) => listSubjects(options), []);
  const limits = useAsyncData((options) => getIngestionLimits(options), []);
  const subjectListId = useId();

  const maxBytes = (kind) => limits.data?.[kind]?.max_bytes ?? INPUT_KINDS[kind].maxBytes;
  const busy = phase === "uploading" || phase === "checking";

  function inputChanged() {
    requestKey.current = crypto.randomUUID();
    setSubmitError(null);
  }

  const updateDetail = (field) => (event) => {
    setDetails((current) => ({ ...current, [field]: event.target.value }));
    inputChanged();
  };

  function selectFile(kind, file) {
    inputChanged();
    const error = validateMediaFile(file, kind, maxBytes(kind));
    setFileErrors((current) => ({ ...current, [kind]: error }));
    setFiles((current) => ({ ...current, [kind]: error ? null : file }));
    if (!error && !details.title.trim()) {
      setDetails((current) => ({ ...current, title: file.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim() }));
    }
  }

  function validate() {
    const errors = validateDetails(details, { titleRequired: tab !== "url" });
    let sourceOk = true;
    if (tab === "url") {
      const error = validateSourceUrl(sourceUrl);
      setUrlError(error);
      setRightsError(rightsConfirmed ? null : "Confirm that you have the right to use this video.");
      sourceOk = !error && rightsConfirmed;
    } else if (!files[tab]) {
      setFileErrors((current) => ({ ...current, [tab]: current[tab] ?? `Choose a ${tab} file to ingest.` }));
      sourceOk = false;
    }
    setDetailErrors(errors);
    return sourceOk && Object.keys(errors).length === 0;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitError(null);
    if (!validate()) {
      setSubmitError({ message: "Fix the highlighted fields to continue." });
      return;
    }
    const payload = {
      title: details.title.trim(),
      subject: details.subject.trim(),
      topic: details.topic.trim(),
      instructor: details.instructor.trim(),
      lectureDate: details.lectureDate,
      tags: parseTags(details.tags),
    };

    try {
      let response;
      if (tab === "url") {
        setPhase("checking");
        response = await submitSourceUrl({
          url: sourceUrl.trim(),
          details: payload,
          rightsConfirmed,
          idempotencyKey: requestKey.current,
        });
      } else {
        const controller = new AbortController();
        abortRef.current = controller;
        setPhase("uploading");
        setProgress({ loaded: 0, total: files[tab].size });
        response = await uploadLecture({
          kind: tab,
          file: files[tab],
          details: payload,
          idempotencyKey: requestKey.current,
          onProgress: setProgress,
          signal: controller.signal,
        });
      }
      setResult(response);
      setPhase("done");
    } catch (error) {
      setPhase("idle");
      if (error.name === "AbortError") {
        setSubmitError({ message: "Upload cancelled. Nothing was saved." });
        return;
      }
      if (error.data?.code === "invalid_metadata" && Array.isArray(error.data.details)) {
        const fieldMap = { lecture_date: "lectureDate" };
        setDetailErrors(
          Object.fromEntries(error.data.details.map((item) => [fieldMap[item.field] ?? item.field, item.message]))
        );
      }
      setSubmitError({ message: error.message, code: error.data?.code, lectureId: error.data?.details?.lecture_id });
    } finally {
      abortRef.current = null;
    }
  }

  function startOver() {
    setFiles({ video: null, audio: null });
    setFileErrors({});
    setSourceUrl("");
    setRightsConfirmed(false);
    setDetails(EMPTY_DETAILS);
    setDetailErrors({});
    setResult(null);
    setProgress(null);
    setPhase("idle");
    requestKey.current = crypto.randomUUID();
  }

  if (phase === "done" && result) {
    return (
      <PageContainer className="ingest">
        <PageHeader title="Ingest Lecture" />
        <section className="ingest-card ingest-success" aria-labelledby="success-heading">
          <span className="ingest-success__icon" aria-hidden="true">
            <CheckIcon size={26} />
          </span>
          <h2 id="success-heading">{result.replayed ? "This lecture was already submitted" : "Lecture added"}</h2>
          <p>
            <strong>{result.lecture.title}</strong> is queued for processing. You can leave this page; its progress is
            saved and shown in your library.
          </p>
          <div className="ingest-success__actions">
            <Button as={Link} to={`/lectures/${result.lecture.id}/processing`}>
              View Processing Details <ArrowRightIcon size={16} />
            </Button>
            <Button variant="secondary" onClick={startOver}>
              Add Another Lecture
            </Button>
          </div>
          <Link to="/library" className="ingest-success__library">
            Go to Library
          </Link>
        </section>
      </PageContainer>
    );
  }

  const tabs = [
    { id: "video", label: INPUT_KINDS.video.label, summary: `MP4, MOV <${shortSize(maxBytes("video"))}`, Icon: VideoIcon },
    { id: "audio", label: INPUT_KINDS.audio.label, summary: `MP3, WAV <${shortSize(maxBytes("audio"))}`, Icon: AudioIcon },
    { id: "url", label: "YouTube / Source URL", Icon: LinkIcon },
  ];

  return (
    <PageContainer className="ingest">
      <PageHeader
        title="Ingest Lecture"
        description="Upload a lecture recording or provide a supported video URL to build your lecture knowledge base."
      />

      <form className="ingest-card" onSubmit={handleSubmit} noValidate aria-busy={busy}>
        <div className="ingest-tabs" role="tablist" aria-label="Lecture source">
          {tabs.map(({ id, label, summary, Icon }) => (
            <button
              key={id}
              type="button"
              role="tab"
              id={`tab-${id}`}
              aria-selected={tab === id}
              aria-controls="ingest-source"
              className="ingest-tabs__tab"
              disabled={busy}
              onClick={() => {
                setTab(id);
                inputChanged();
              }}
            >
              <Icon size={17} />
              <span className="ingest-tabs__label">{label}</span>
              {summary && <span className="ingest-tabs__summary mono">{summary}</span>}
            </button>
          ))}
        </div>

        <fieldset className="ingest-card__body" disabled={busy}>
          <div id="ingest-source" role="tabpanel" aria-labelledby={`tab-${tab}`}>
            {tab === "url" ? (
              <UrlSource
                value={sourceUrl}
                error={urlError}
                rightsConfirmed={rightsConfirmed}
                rightsError={rightsError}
                onChange={(value) => {
                  setSourceUrl(value);
                  setUrlError(null);
                  inputChanged();
                }}
                onRightsChange={(value) => {
                  setRightsConfirmed(value);
                  setRightsError(null);
                  inputChanged();
                }}
              />
            ) : (
              <FileDropZone
                key={tab}
                kind={tab}
                maxBytes={maxBytes(tab)}
                file={files[tab]}
                error={fileErrors[tab]}
                onSelect={(file) => selectFile(tab, file)}
                onRemove={() => {
                  setFiles((current) => ({ ...current, [tab]: null }));
                  setFileErrors((current) => ({ ...current, [tab]: null }));
                  inputChanged();
                }}
              />
            )}
          </div>

          <section className="ingest-details" aria-labelledby="details-heading">
            <div className="ingest-details__head">
              <h2 id="details-heading">Lecture Details</h2>
              <span className="mono ingest-details__required">* Required fields</span>
            </div>

            <Input
              id="title"
              label={tab === "url" ? <OptionalLabel>Lecture Title</OptionalLabel> : <RequiredLabel>Lecture Title</RequiredLabel>}
              hint={tab === "url" ? "Leave empty to use the video's own title." : undefined}
              value={details.title}
              onChange={updateDetail("title")}
              error={detailErrors.title}
              maxLength={LIMITS.title}
            />
            <div className="ingest-details__grid">
              <Input
                id="subject"
                label={<RequiredLabel>Subject / Discipline</RequiredLabel>}
                value={details.subject}
                onChange={updateDetail("subject")}
                error={detailErrors.subject}
                maxLength={LIMITS.subject}
                list={subjectListId}
                autoComplete="off"
              />
              <datalist id={subjectListId}>
                {(subjects.data?.subjects ?? []).map((name) => (
                  <option key={name} value={name} />
                ))}
              </datalist>
              <Input
                id="topic"
                label={<OptionalLabel>Specific Topic</OptionalLabel>}
                value={details.topic}
                onChange={updateDetail("topic")}
                error={detailErrors.topic}
                maxLength={LIMITS.topic}
              />
              <Input
                id="instructor"
                label={<OptionalLabel>Instructor / Lecturer</OptionalLabel>}
                value={details.instructor}
                onChange={updateDetail("instructor")}
                error={detailErrors.instructor}
                maxLength={LIMITS.instructor}
              />
              <Input
                id="lectureDate"
                type="date"
                label={<OptionalLabel>Lecture Date</OptionalLabel>}
                value={details.lectureDate}
                onChange={updateDetail("lectureDate")}
                error={detailErrors.lectureDate}
              />
            </div>
            <Input
              id="tags"
              label={<OptionalLabel>Tags</OptionalLabel>}
              hint="Comma-separated, e.g. Machine Learning, Optimization"
              value={details.tags}
              onChange={updateDetail("tags")}
              error={detailErrors.tags}
            />
          </section>

          <section className="ingest-next" aria-labelledby="next-heading">
            <h2 id="next-heading" className="ingest-next__title">
              After ingestion, LectureMind will:
            </h2>
            <ol className="ingest-next__steps">
              <li>Process media</li>
              <li>Build lecture intelligence</li>
              <li>Make the lecture searchable and ready for grounded Q&amp;A</li>
            </ol>
          </section>

          {submitError && (
            <Alert tone="error">
              {submitError.message}
              {submitError.code === "duplicate_lecture" && submitError.lectureId && (
                <>
                  {" "}
                  <Link to={`/lectures/${submitError.lectureId}/processing`}>Open the existing lecture</Link>
                </>
              )}
            </Alert>
          )}

          {phase === "uploading" && progress && (
            <UploadProgress progress={progress} onCancel={() => abortRef.current?.abort()} />
          )}
          {phase === "checking" && (
            <p className="ingest-checking" role="status">
              Checking that this video is available…
            </p>
          )}

          <div className="ingest-actions">
            <Link to="/library" className="ingest-actions__cancel">
              ← Cancel and return to library
            </Link>
            <Button type="submit" disabled={busy} aria-busy={busy} className="ingest-actions__primary">
              {phase === "uploading" ? "Uploading…" : phase === "checking" ? "Checking video…" : "Start Ingestion & Processing"}
              {!busy && <ArrowRightIcon size={16} />}
            </Button>
          </div>
        </fieldset>

        <p className="ingest-card__footer">
          <LockIcon size={14} /> Lecture media is stored privately and is only accessible to your account.
        </p>
      </form>
    </PageContainer>
  );
}

function UploadProgress({ progress, onCancel }) {
  const percent = progress.total ? Math.min(100, Math.round((progress.loaded / progress.total) * 100)) : 0;
  const sending = percent < 100;
  return (
    <div className="upload-progress" role="status" aria-live="polite">
      <div className="upload-progress__text">
        <span>{sending ? "Uploading" : "Upload complete. Securing the file and starting processing…"}</span>
        {sending && (
          <span className="mono">
            {formatFileSize(progress.loaded)} of {formatFileSize(progress.total)} ({percent}%)
          </span>
        )}
      </div>
      <span
        className="upload-progress__bar"
        role="progressbar"
        aria-label="Upload progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
      >
        <span style={{ width: `${percent}%` }} />
      </span>
      {sending && (
        <Button type="button" variant="tertiary" onClick={onCancel} className="upload-progress__cancel">
          Cancel upload
        </Button>
      )}
    </div>
  );
}

function RequiredLabel({ children }) {
  return (
    <>
      {children} <span className="ingest-required" aria-hidden="true">*</span>
      <span className="visually-hidden">(required)</span>
    </>
  );
}

function OptionalLabel({ children }) {
  return (
    <>
      {children} <span className="ingest-optional mono">(optional)</span>
    </>
  );
}

function FileDropZone({ kind, maxBytes, file, error, onSelect, onRemove }) {
  const rules = INPUT_KINDS[kind];
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const Icon = kind === "video" ? VideoIcon : AudioIcon;

  function handleDrop(event) {
    event.preventDefault();
    setDragging(false);
    const dropped = event.dataTransfer.files?.[0];
    if (dropped) onSelect(dropped);
  }

  return (
    <div
      className={`dropzone ${dragging ? "dropzone--dragging" : ""} ${error ? "dropzone--error" : ""}`}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
    >
      <span className="dropzone__icon" aria-hidden="true">
        {dragging ? <UploadIcon size={26} /> : <Icon size={26} />}
      </span>
      <p className="dropzone__title">{dragging ? "Drop to select this file" : `Drag and drop your lecture ${kind} here`}</p>
      <p className="dropzone__hint">
        or{" "}
        <button type="button" className="dropzone__browse" onClick={() => inputRef.current?.click()}>
          browse files
        </button>{" "}
        from your computer
      </p>
      <input
        ref={inputRef}
        type="file"
        className="visually-hidden"
        accept={[...rules.mimeTypes, ...rules.extensions].join(",")}
        aria-label={`Choose a ${kind} file`}
        onChange={(event) => {
          const chosen = event.target.files?.[0];
          if (chosen) onSelect(chosen);
          event.target.value = "";
        }}
      />

      {file && (
        <div className="dropzone__file">
          <CheckIcon size={16} />
          <span className="mono dropzone__file-name">{file.name}</span>
          <span className="mono dropzone__file-size">({formatFileSize(file.size)})</span>
          <button type="button" onClick={() => inputRef.current?.click()}>
            Change file
          </button>
          <button type="button" className="dropzone__remove" onClick={onRemove}>
            Remove
          </button>
        </div>
      )}
      {error && (
        <p className="dropzone__error" role="alert">
          {error}
        </p>
      )}

      <p className="dropzone__formats">
        Supported {kind} formats: {rules.formats} (up to {formatFileSize(maxBytes)}).
      </p>
    </div>
  );
}

function UrlSource({ value, error, rightsConfirmed, rightsError, onChange, onRightsChange }) {
  return (
    <div className="url-source">
      <Input
        id="source-url"
        type="url"
        inputMode="url"
        label="Video URL"
        placeholder="https://www.youtube.com/watch?v=…"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        error={error}
        hint="Paste a link to a single YouTube lecture video."
      />
      <label className={`url-source__rights ${rightsError ? "url-source__rights--error" : ""}`}>
        <input type="checkbox" checked={rightsConfirmed} onChange={(event) => onRightsChange(event.target.checked)} />
        <span>
          I have the right to use this video for my own study (for example, it&apos;s my own recording or its license
          allows it).
        </span>
      </label>
      {rightsError && (
        <p className="url-source__error" role="alert">
          {rightsError}
        </p>
      )}
      <p className="url-source__note">
        Private, age-restricted or region-restricted videos can&apos;t be processed.
      </p>
    </div>
  );
}
