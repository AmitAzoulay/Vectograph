// Thin API client for the Vectograph backend.
// In Docker the browser talks to the backend through the host-published port.
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

/**
 * Upload a .zip codebase for scanning.
 * @param {File} file
 * @param {(pct:number)=>void} [onProgress]
 * @returns {Promise<object>} scan summary
 */
export function uploadCodebase(file, onProgress) {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('file', file)

    // Use XHR (not fetch) so we can surface upload progress in the UI.
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_URL}/api/upload`)

    xhr.upload.onprogress = (e) => {
      if (onProgress && e.lengthComputable) {
        onProgress(Math.round((e.loaded / e.total) * 100))
      }
    }

    xhr.onload = () => {
      let body = {}
      try {
        body = JSON.parse(xhr.responseText)
      } catch {
        /* ignore parse errors */
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body)
      } else {
        reject(new Error(body.detail || `Upload failed (${xhr.status})`))
      }
    }
    xhr.onerror = () => reject(new Error('Network error while uploading.'))
    xhr.send(form)
  })
}

/** Fetch the full architecture graph. */
export async function fetchGraph() {
  const res = await fetch(`${API_URL}/api/graph`)
  if (!res.ok) throw new Error(`Failed to load graph (${res.status})`)
  return res.json()
}

/** Delete every node and relationship. */
export async function clearGraph() {
  const res = await fetch(`${API_URL}/api/graph`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`Failed to clear graph (${res.status})`)
  return res.json()
}
