import Badge from "../ui/Badge";
import { AudioIcon, LinkIcon, VideoIcon } from "../ui/icons";
import { SOURCE_TYPE_LABELS, statusInfo } from "../../lectures/lectureStatus";

const SOURCE_ICONS = { video: VideoIcon, audio: AudioIcon, url: LinkIcon };

export function StatusBadge({ status }) {
  const info = statusInfo(status);
  return (
    <Badge tone={info.tone} className="status-badge">
      <span className="status-badge__dot" aria-hidden="true" />
      {info.group === "processing" ? "Processing" : info.label}
    </Badge>
  );
}

export function SourceBadge({ sourceType }) {
  const Icon = SOURCE_ICONS[sourceType] ?? VideoIcon;
  return (
    <Badge tone="neutral" className="source-badge">
      <Icon size={13} />
      {SOURCE_TYPE_LABELS[sourceType] ?? sourceType}
    </Badge>
  );
}

export function SourceIcon({ sourceType, size }) {
  const Icon = SOURCE_ICONS[sourceType] ?? VideoIcon;
  return <Icon size={size} />;
}
