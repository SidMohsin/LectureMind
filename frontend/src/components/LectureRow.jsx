import StatusBadge from './StatusBadge'
import { formatDuration, formatDate } from '../services/format'

const FILE_TYPE_LABEL = { video: 'Video', audio: 'Audio' }

export default function LectureRow({ lecture, onOpen, onDelete }) {
  return (
    <div className="lecture-row">
      <div className="lecture-row-main" onClick={() => onOpen(lecture.lecture_id)} role="button" tabIndex={0}
           onKeyDown={(e) => { if (e.key === 'Enter') onOpen(lecture.lecture_id) }}>
        <div className="lecture-row-icon" aria-hidden="true">
          {lecture.file_type === 'video' ? '▶' : '♪'}
        </div>
        <div className="lecture-row-text">
          <span className="lecture-row-title">{lecture.original_filename}</span>
          <span className="lecture-row-meta">
            {FILE_TYPE_LABEL[lecture.file_type] || lecture.file_type} · {formatDuration(lecture.duration_seconds)} · {formatDate(lecture.upload_time)}
          </span>
        </div>
      </div>
      <div className="lecture-row-side">
        <StatusBadge status={lecture.status} />
        <button className="btn-secondary btn-small" onClick={() => onOpen(lecture.lecture_id)}>Open</button>
        {onDelete && (
          <button className="btn-icon-danger" title="Delete lecture" aria-label="Delete lecture"
                  onClick={() => onDelete(lecture)}>
            ×
          </button>
        )}
      </div>
    </div>
  )
}
