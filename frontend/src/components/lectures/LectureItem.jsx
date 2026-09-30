import { Link } from "react-router-dom";
import Button from "../ui/Button";
import { AlertIcon, ArrowRightIcon } from "../ui/icons";
import { SourceBadge, SourceIcon, StatusBadge } from "./LectureBadges";
import LectureMenu from "./LectureMenu";
import { lecturePath, statusInfo } from "../../lectures/lectureStatus";
import { formatDate, formatDuration } from "../../utils/format";
import "./LectureItem.css";

function MediaTile({ lecture }) {
  const duration = formatDuration(lecture.duration_seconds);
  const failed = lecture.status === "FAILED";
  return (
    <div className={`lecture-tile ${failed ? "lecture-tile--failed" : ""}`}>
      <div className="lecture-tile__type">
        <SourceBadge sourceType={lecture.source_type} />
      </div>
      <span className="lecture-tile__icon">{failed ? <AlertIcon size={26} /> : <SourceIcon sourceType={lecture.source_type} size={26} />}</span>
      {duration && <span className="lecture-tile__duration">{duration}</span>}
    </div>
  );
}

function Metadata({ lecture }) {
  const parts = [lecture.instructor, lecture.subject, formatDate(lecture.lecture_date || lecture.created_at)].filter(Boolean);
  return (
    <p className="lecture-item__meta">
      {parts.map((part, index) => (
        <span key={index} className={index === parts.length - 1 ? "mono" : undefined}>
          {part}
        </span>
      ))}
    </p>
  );
}

function StatusDetail({ lecture }) {
  const info = statusInfo(lecture.status);
  if (info.group === "failed") {
    return (
      <p className="lecture-item__failure">
        <AlertIcon size={14} /> Processing couldn&apos;t be completed for this lecture.
      </p>
    );
  }
  if (info.group !== "processing") return null;
  return (
    <div className="lecture-item__progress">
      <span className="lecture-item__progress-label mono">
        {info.label}
        {info.stage && ` (Stage ${info.stage}/${info.totalStages})`}
      </span>
      {info.stage && (
        <span
          className="lecture-item__progress-bar"
          role="progressbar"
          aria-label="Processing stage"
          aria-valuemin={0}
          aria-valuemax={info.totalStages}
          aria-valuenow={info.stage}
        >
          <span style={{ width: `${(info.stage / info.totalStages) * 100}%` }} />
        </span>
      )}
    </div>
  );
}

function PrimaryAction({ lecture }) {
  const ready = statusInfo(lecture.status).group === "ready";
  return (
    <Button as={Link} to={lecturePath(lecture)} variant={ready ? "primary" : "secondary"} className="lecture-item__action">
      {ready ? "Open Workspace" : "View Processing Details"}
      <ArrowRightIcon size={15} />
    </Button>
  );
}

export default function LectureItem({ lecture, layout = "list", onDelete }) {
  const group = statusInfo(lecture.status).group;
  return (
    <article className={`lecture-item lecture-item--${layout} lecture-item--${group}`}>
      <MediaTile lecture={lecture} />
      <div className="lecture-item__body">
        <Metadata lecture={lecture} />
        <h3 className="lecture-item__title">
          <Link to={lecturePath(lecture)}>{lecture.title}</Link>
        </h3>
        {lecture.tags.length > 0 && (
          <ul className="lecture-item__tags" aria-label="Tags">
            {lecture.tags.map((tag) => (
              <li key={tag}>{tag}</li>
            ))}
          </ul>
        )}
        <StatusDetail lecture={lecture} />
      </div>
      <div className="lecture-item__side">
        <StatusBadge status={lecture.status} />
        <div className="lecture-item__actions">
          <PrimaryAction lecture={lecture} />
          <LectureMenu lecture={lecture} onDelete={onDelete} />
        </div>
      </div>
    </article>
  );
}
