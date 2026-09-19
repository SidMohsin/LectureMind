import { useState } from 'react'
import { useApp } from '../context/AppContext'
import { uploadLecture, startProcessing } from '../services/api'
import UploadZone from '../components/UploadZone'

export default function UploadPage() {
  const { navigate, triggerRefresh } = useApp()
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [error, setError] = useState(null)

  async function handleUpload(file) {
    setUploading(true)
    setError(null)
    setUploadProgress(0)
    try {
      const res = await uploadLecture(file, setUploadProgress)
      await startProcessing(res.lecture_id)
      triggerRefresh()
      navigate('lecture', res.lecture_id)
    } catch (e) {
      setError(e.message || 'Upload failed. Please try again.')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="page-upload">
      <div className="page-header-row">
        <h1>Upload Lecture</h1>
      </div>
      <p className="page-subtitle">
        Upload a lecture recording and LectureMind will automatically extract the audio,
        transcribe it with timestamps, generate a summary, extract keywords, and make it
        ready for question answering.
      </p>

      <div className="card upload-page-card">
        <UploadZone
          onUpload={handleUpload}
          uploading={uploading}
          uploadProgress={uploadProgress}
          error={error}
        />
      </div>
    </div>
  )
}
