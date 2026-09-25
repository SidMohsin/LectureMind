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
      <div className="upload-hero">
        <span className="upload-kicker">New lecture</span>
        <h1>Bring your next lecture<br />into focus.</h1>
        <p>Upload a recording and get a timestamped transcript, clear notes, key concepts, and a grounded study chat.</p>
      </div>

      <div className="upload-layout">
        <UploadZone
          onUpload={handleUpload}
          uploading={uploading}
          uploadProgress={uploadProgress}
          error={error}
        />
        <aside className="upload-notes">
          <span>What happens next</span>
          <ol>
            <li><b>01</b> We prepare your recording.</li>
            <li><b>02</b> A searchable transcript is created.</li>
            <li><b>03</b> Notes and key concepts are ready to study.</li>
          </ol>
          <p>Your files stay in your private library.</p>
        </aside>
      </div>
    </div>
  )
}
