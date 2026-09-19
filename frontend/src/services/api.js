// Central API client for the LectureMind backend.
// Base URL is read from VITE_API_BASE_URL, defaulting to localhost:8000.

export const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

async function handleResponse(res) {
  if (!res.ok) {
    let detail = `Request failed with status ${res.status}`
    try {
      const body = await res.json()
      if (body.detail) detail = body.detail
    } catch (e) {
      // response wasn't JSON; keep default message
    }
    const err = new Error(detail)
    err.status = res.status
    throw err
  }
  return res.json()
}

export async function uploadLecture(file, onProgress) {
  const formData = new FormData()
  formData.append('file', file)

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE}/api/lectures/upload`)
    xhr.upload.onprogress = (e) => {
      if (onProgress && e.lengthComputable) {
        onProgress(Math.round((e.loaded / e.total) * 100))
      }
    }
    xhr.onload = () => {
      try {
        const body = JSON.parse(xhr.responseText)
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(body)
        } else {
          reject(new Error(body.detail || 'Upload failed'))
        }
      } catch (e) {
        reject(new Error('Unexpected server response during upload'))
      }
    }
    xhr.onerror = () => reject(new Error('Network error during upload'))
    xhr.send(formData)
  })
}

export async function startProcessing(lectureId) {
  const res = await fetch(`${API_BASE}/api/lectures/${lectureId}/process`, { method: 'POST' })
  return handleResponse(res)
}

export async function getStatus(lectureId) {
  const res = await fetch(`${API_BASE}/api/lectures/${lectureId}/status`)
  return handleResponse(res)
}

export async function getTranscript(lectureId) {
  const res = await fetch(`${API_BASE}/api/lectures/${lectureId}/transcript`)
  return handleResponse(res)
}

export async function getSummary(lectureId) {
  const res = await fetch(`${API_BASE}/api/lectures/${lectureId}/summary`)
  return handleResponse(res)
}

export async function getKeywords(lectureId) {
  const res = await fetch(`${API_BASE}/api/lectures/${lectureId}/keywords`)
  return handleResponse(res)
}

export async function askQuestion(lectureId, question, topK) {
  const res = await fetch(`${API_BASE}/api/lectures/${lectureId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, top_k: topK }),
  })
  return handleResponse(res)
}

export async function listLectures() {
  const res = await fetch(`${API_BASE}/api/lectures`)
  return handleResponse(res)
}

export async function getLecture(lectureId) {
  const res = await fetch(`${API_BASE}/api/lectures/${lectureId}`)
  return handleResponse(res)
}

export async function deleteLecture(lectureId) {
  const res = await fetch(`${API_BASE}/api/lectures/${lectureId}`, { method: 'DELETE' })
  return handleResponse(res)
}

export async function getStats() {
  const res = await fetch(`${API_BASE}/api/stats`)
  return handleResponse(res)
}

export async function getConfig() {
  const res = await fetch(`${API_BASE}/api/config`)
  return handleResponse(res)
}

/** Builds the streaming media URL for a lecture's <video>/<audio> element. */
export function mediaUrl(lectureId) {
  return `${API_BASE}/api/lectures/${lectureId}/media`
}
