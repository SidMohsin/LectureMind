import { useRef, useState } from 'react'

const ACCEPTED_EXTENSIONS = ['.mp4', '.mkv', '.mov', '.avi', '.mp3', '.wav', '.m4a']
const MAX_SIZE_MB = 500

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
      setValidationError(`Unsupported format "${ext}". Accepted: ${ACCEPTED_EXTENSIONS.join(', ')}`)
      setSelectedFile(null)
      return
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      setValidationError(`File too large. Maximum is ${MAX_SIZE_MB} MB.`)
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

  const isVideo = selectedFile && (
    selectedFile.type.startsWith('video') || /\.(mp4|mkv|mov|avi)$/i.test(selectedFile.name)
  )

  return (
    <div className="upload-zone-wrapper">
      <div
        className={`upload-drop-area ${dragOver ? 'upload-zone-active' : ''} ${selectedFile ? 'upload-zone-filled' : ''}`}
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
            <div className="upload-icon" aria-hidden="true">↑</div>
            <p className="upload-title">Drop a lecture here</p>
            <p className="upload-subtitle">or click to browse your files</p>
            <p className="upload-formats">MP4 · MKV · MOV · AVI · MP3 · WAV · M4A — up to {MAX_SIZE_MB} MB</p>
          </>
        ) : (
          <div className="upload-file-selected">
            <div className="upload-file-icon" aria-hidden="true">
              {isVideo ? '▶' : '♪'}
            </div>
            <div className="upload-file-info">
              <span className="upload-file-name">{selectedFile.name}</span>
              <span className="upload-file-size">{formatFileSize(selectedFile.size)}</span>
            </div>
            {!uploading && (
              <button className="btn-secondary btn-small" onClick={handleRemove}>
                Change
              </button>
            )}
          </div>
        )}
      </div>

      {validationError && <div className="error-banner">{validationError}</div>}
      {error && <div className="error-banner">{error}</div>}

      {uploading && (
        <div>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${uploadProgress}%` }} />
          </div>
          <div className="progress-label">
            <span>Uploading…</span>
            <span>{uploadProgress}%</span>
          </div>
        </div>
      )}

      <button
        className="btn-primary"
        disabled={!selectedFile || uploading}
        onClick={() => selectedFile && onUpload(selectedFile)}
      >
        {uploading ? 'Uploading…' : 'Add to library'}
      </button>
    </div>
  )
}
