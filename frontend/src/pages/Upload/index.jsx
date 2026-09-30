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
import { INPUT_KINDS, parseTags, validateMediaFile, validateSourceUrl } from "../../lectures/lectureInput";
import { formatFileSize } from "../../utils/format";
import "./Upload.css";

const TABS = [
  { id: "video", label: INPUT_KINDS.video.label, summary: INPUT_KINDS.video.summary, Icon: VideoIcon },
  { id: "audio", label: INPUT_KINDS.audio.label, summary: INPUT_KINDS.audio.summary, Icon: AudioIcon },
  { id: "url", label: "YouTube / Source URL", Icon: LinkIcon },
];

const EMPTY_DETAILS = { title: "", subject: "", topic: "", instructor: "", lectureDate: "", tags: "" };

// Mirrors the column constraints on public.lectures.
const LIMITS = { title: 300, subject: 120, topic: 200, instructor: 120 };
const MAX_TAGS = 20;
const MAX_TAG_LENGTH = 40;

function validateDetails(details) {
  const errors = {};
  if (!details.title.trim()) errors.title = "Enter a lecture title.";
  if (!details.subject.trim()) errors.subject = "Enter the subject or discipline.";
  Object.entries(LIMITS).forEach(([field, max]) => {
    if (details[field].trim().length > max) errors[field] = `Keep this under ${max} characters.`;
  });
  const tags = parseTags(details.tags);
  if (tags.length > MAX_TAGS) errors.tags = `Use at most ${MAX_TAGS} tags.`;
  else if (tags.some((tag) => tag.length > MAX_TAG_LENGTH)) errors.tags = `Keep each tag under ${MAX_TAG_LENGTH} characters.`;
  return errors;
}

export default function Upload() {
  const [tab, setTab] = useState("video");
  const [files, setFiles] = useState({ video: null, audio: null });
  const [fileErrors, setFileErrors] = useState({});
  const [sourceUrl, setSourceUrl] = useState("");
  const [urlError, setUrlError] = useState(null);
  const [details, setDetails] = useState(EMPTY_DETAILS);
  const [detailErrors, setDetailErrors] = useState({});
  const [outcome, setOutcome] = useState(null);
  const subjects = useAsyncData((options) => listSubjects(options), []);
  const subjectListId = useId();

  const updateDetail = (field) => (event) => {
    setDetails((current) => ({ ...current, [field]: event.target.value }));
    setOutcome(null);
  };

  function selectFile(kind, file) {
    setOutcome(null);
    const error = validateMediaFile(file, kind);
    setFileErrors((current) => ({ ...current, [kind]: error }));
    setFiles((current) => ({ ...current, [kind]: error ? null : file }));
    if (!error && !details.title.trim()) {
      setDetails((current) => ({ ...current, title: file.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim() }));
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    const errors = validateDetails(details);
    let sourceOk;
    if (tab === "url") {
      const error = validateSourceUrl(sourceUrl);
      setUrlError(error);
      sourceOk = !error;
    } else {
      if (!files[tab]) setFileErrors((current) => ({ ...current, [tab]: current[tab] ?? `Choose a ${tab} file to ingest.` }));
      sourceOk = Boolean(files[tab]);
    }
    setDetailErrors(errors);
    setOutcome(sourceOk && Object.keys(errors).length === 0 ? "valid" : "invalid");
  }

  return (
    <PageContainer className="ingest">
      <PageHeader
        title="Ingest Lecture"
        description="Upload a lecture recording or provide a supported video URL to build your lecture knowledge base."
      />

      <form className="ingest-card" onSubmit={handleSubmit} noValidate>
        <div className="ingest-tabs" role="tablist" aria-label="Lecture source">
          {TABS.map(({ id, label, summary, Icon }) => (
            <button
              key={id}
              type="button"
              role="tab"
              id={`tab-${id}`}
              aria-selected={tab === id}
              aria-controls="ingest-source"
              className="ingest-tabs__tab"
              onClick={() => {
                setTab(id);
                setOutcome(null);
              }}
            >
              <Icon size={17} />
              <span className="ingest-tabs__label">{label}</span>
              {summary && <span className="ingest-tabs__summary mono">{summary}</span>}
            </button>
          ))}
        </div>

        <div className="ingest-card__body">
          <div id="ingest-source" role="tabpanel" aria-labelledby={`tab-${tab}`}>
            {tab === "url" ? (
              <UrlSource
                value={sourceUrl}
                error={urlError}
                onChange={(value) => {
                  setSourceUrl(value);
                  setUrlError(null);
                  setOutcome(null);
                }}
              />
            ) : (
              <FileDropZone
                key={tab}
                kind={tab}
                file={files[tab]}
                error={fileErrors[tab]}
                onSelect={(file) => selectFile(tab, file)}
                onRemove={() => {
                  setFiles((current) => ({ ...current, [tab]: null }));
                  setFileErrors((current) => ({ ...current, [tab]: null }));
                  setOutcome(null);
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
              label={<RequiredLabel>Lecture Title</RequiredLabel>}
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

          {outcome === "valid" && (
            <Alert tone="info" title="Your lecture details look good.">
              Lecture ingestion isn&apos;t available yet, so nothing has been uploaded or saved. Uploading and processing
              lectures is the next part of LectureMind being built.
            </Alert>
          )}
          {outcome === "invalid" && <Alert tone="error">Fix the highlighted fields to continue.</Alert>}

          <div className="ingest-actions">
            <Link to="/library" className="ingest-actions__cancel">
              ← Cancel and return to library
            </Link>
            <div className="ingest-actions__submit">
              <Button type="submit">
                Start Ingestion &amp; Processing <ArrowRightIcon size={16} />
              </Button>
              <span className="ingest-actions__note">Ingestion is not available yet. Your details are checked only.</span>
            </div>
          </div>
        </div>

        <p className="ingest-card__footer">
          <LockIcon size={14} /> Lecture media is stored privately and is only accessible to your account.
        </p>
      </form>
    </PageContainer>
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

function FileDropZone({ kind, file, error, onSelect, onRemove }) {
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
        Supported {kind} formats: {rules.formats} (up to {formatFileSize(rules.maxBytes)}).
      </p>
    </div>
  );
}

function UrlSource({ value, error, onChange }) {
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
      <p className="url-source__note">
        Only submit videos you have the right to use. Some videos can&apos;t be processed because of the
        platform&apos;s access or usage restrictions.
      </p>
    </div>
  );
}
