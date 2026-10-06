import { useState } from "react";
import { AlertIcon } from "../ui/icons";
import { SourceIcon } from "./LectureBadges";
import { coverInitials, coverStyle, thumbnailUrl } from "../../lectures/thumbnails";
import "./LectureThumb.css";

/**
 * Lecture artwork: the YouTube thumbnail when there is one, otherwise (or if the
 * image fails to load) a generated cover with the subject's initials.
 */
export default function LectureThumb({ lecture, className = "", children }) {
  const [broken, setBroken] = useState(false);
  const failed = lecture.status === "FAILED";
  const src = !broken && !failed ? thumbnailUrl(lecture) : null;
  const initials = coverInitials(lecture);

  return (
    <div className={`lecture-thumb ${failed ? "lecture-thumb--failed" : ""} ${className}`.trim()}>
      {src ? (
        <img src={src} alt="" loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={() => setBroken(true)} />
      ) : failed ? (
        <span className="lecture-thumb__cover lecture-thumb__cover--failed">
          <AlertIcon size={24} />
        </span>
      ) : (
        <span className="lecture-thumb__cover" style={coverStyle(lecture.subject || lecture.title)}>
          {initials && <span className="lecture-thumb__initials">{initials}</span>}
          <span className="lecture-thumb__source">
            <SourceIcon sourceType={lecture.source_type} size={14} />
          </span>
        </span>
      )}
      {children}
    </div>
  );
}
