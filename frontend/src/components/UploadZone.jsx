import { useRef, useState } from 'react'

const ACCEPTED_EXTENSIONS = ['.mp4', '.mkv', '.mov', '.avi', '.mp3', '.wav', '.m4a']
const MAX_SIZE_MB = 500 // mirrors backend default MAX_UPLOAD_SIZE_MB; backend is the source of truth

function formatFileSize(bytes) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function UploadZone({ onUpload, uploading, uploadProgress, error }) {
  const inputRef = useRef(null)
  const [dragOver, setDragOver] = useState(false)
  const [selectedFile, setSelectedFile] = useState(null)
  const [validationError, setValidationError] = useState(null)

  function handleFiles(files) {
    if (!files || files.length === 0) return
    const file = files[0]
    const ext = '.' + file.name.split('.').pop().toLowerCase()

    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      setValidationError(`Unsupported file type "${ext}". Accepted formats: ${ACCEPTED_EXTENSIONS.join(', ')}`)
      setSelectedFile(null)
      return
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      setValidationError(`File is too large. Maximum allowed size is ${MAX_SIZE_MB} MB.`)
      setSelectedFile(null)
      return
    }
    setValidationError(null)
    setSelectedFile(file)
  }

  function handleDrop(e) {
    e.preventDefault()
    setDragOver(false)
    handleFiles(e.dataTransfer.files)
  }

  function handleRemove(e) {
    e.stopPropagation()
    setSelectedFile(null)
    setValidationError(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  return (
    <div className="upload-zone-wrapper">
      <div
        className={`upload-zone ${dragOver ? 'upload-zone-active' : ''} ${selectedFile ? 'upload-zone-filled' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => !selectedFile && inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_EXTENSIONS.join(',')}
          style={{ display: 'none' }}
          onChange={(e) => handleFiles(e.target.files)}
        />

        {!selectedFile ? (
          <>
            <div className="upload-zone-icon" aria-hidden="true">↑</div>
            <p className="upload-zone-title">Drop your lecture here</p>
            <p className="hint">or click to browse your files</p>
            <p className="upload-zone-formats">MP4 · MKV · MOV · AVI · MP3 · WAV · M4A — up to {MAX_SIZE_MB} MB</p>
          </>
        ) : (
          <div className="upload-zone-file">
            <div className="upload-zone-file-icon" aria-hidden="true">
              {selectedFile.type.startsWith('video') || /\.(mp4|mkv|mov|avi)$/i.test(selectedFile.name) ? '▶' : '♪'}
            </div>
            <div className="upload-zone-file-info">
              <span className="upload-zone-file-name">{selectedFile.name}</span>
              <span className="upload-zone-file-meta">{formatFileSize(selectedFile.size)}</span>
            </div>
            {!uploading && (
              <button className="btn-secondary btn-small" onClick={handleRemove}>Change file</button>
            )}
          </div>
        )}
      </div>

      {validationError && <div className="error-banner">{validationError}</div>}
      {error && <div className="error-banner">{error}</div>}

      {uploading && (
        <div className="progress-bar-outer">
          <div className="progress-bar-inner" style={{ width: `${uploadProgress}%` }} />
          <span className="progress-label">{uploadProgress}%</span>
        </div>
      )}

      <button
        className="btn-primary"
        disabled={!selectedFile || uploading}
        onClick={() => selectedFile && onUpload(selectedFile)}
      >
        {uploading ? 'Uploading…' : 'Upload Lecture'}
      </button>
    </div>
  )
}
