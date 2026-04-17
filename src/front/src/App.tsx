import { useState, useRef } from 'react'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:80'

type JobStatus = 'idle' | 'creating' | 'uploading' | 'polling' | 'done' | 'error'

interface JobResponse {
  jobId: string
  status: string
  createdAt: string
  uploadUrl: string
}

export default function App() {
  const [file, setFile] = useState<File | null>(null)
  const [jobStatus, setJobStatus] = useState<JobStatus>('idle')
  const [jobId, setJobId] = useState<string | null>(null)
  const [jobState, setJobState] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  const pollJob = (id: string) => {
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API_URL}/jobs/${id}`)
        if (!res.ok) throw new Error(`Erreur ${res.status}`)
        const data = await res.json()
        setJobState(data.status)
        if (data.status !== 'CREATED') {
          stopPolling()
          setJobStatus('done')
        }
      } catch (e) {
        stopPolling()
        setError((e as Error).message)
        setJobStatus('error')
      }
    }, 3000)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!file) return

    setError(null)
    setJobId(null)
    setJobState(null)

    try {
      // 1. Créer le job
      setJobStatus('creating')
      const createRes = await fetch(`${API_URL}/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          fileName: file.name,
          contentType: file.type || 'application/octet-stream',
        }),
      })
      if (!createRes.ok) {
        const msg = await createRes.text()
        throw new Error(`Création du job échouée (${createRes.status}): ${msg}`)
      }
      const job: JobResponse = await createRes.json()
      setJobId(job.jobId)
      setJobState(job.status)

      // 2. Upload direct vers Azure Blob via SAS URL
      setJobStatus('uploading')
      const uploadRes = await fetch(job.uploadUrl, {
        method: 'PUT',
        headers: {
          'Content-Type': file.type || 'application/octet-stream',
          'x-ms-blob-type': 'BlockBlob',
        },
        body: file,
      })
      if (!uploadRes.ok) {
        throw new Error(`Upload échoué (${uploadRes.status})`)
      }

      // 3. Polling du statut
      setJobStatus('polling')
      pollJob(job.jobId)
    } catch (e) {
      stopPolling()
      setError((e as Error).message)
      setJobStatus('error')
    }
  }

  const reset = () => {
    stopPolling()
    setFile(null)
    setJobStatus('idle')
    setJobId(null)
    setJobState(null)
    setError(null)
  }

  const isLoading = ['creating', 'uploading', 'polling'].includes(jobStatus)

  return (
    <div className="container">
      <h1>Document Upload</h1>

      <form onSubmit={handleSubmit} className="form">
        <label className="file-label">
          <span>Sélectionner un fichier</span>
          <input
            type="file"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            disabled={isLoading}
          />
        </label>

        {file && (
          <p className="file-name">
            {file.name} ({(file.size / 1024).toFixed(1)} Ko)
          </p>
        )}

        <button type="submit" disabled={!file || isLoading}>
          {isLoading ? 'Traitement...' : 'Créer & Uploader'}
        </button>
      </form>

      {error && (
        <div className="status error">
          <strong>Erreur :</strong> {error}
          <button onClick={reset} className="reset-btn">Réessayer</button>
        </div>
      )}

      {jobId && (
        <div className="status info">
          <p><strong>Job ID :</strong> {jobId}</p>
          <p>
            <strong>Statut :</strong>{' '}
            <span className={`badge badge-${jobState?.toLowerCase()}`}>
              {stepLabel(jobStatus, jobState)}
            </span>
          </p>
          {jobStatus === 'done' && (
            <button onClick={reset} className="reset-btn">Nouveau fichier</button>
          )}
        </div>
      )}
    </div>
  )
}

function stepLabel(jobStatus: JobStatus, jobState: string | null): string {
  switch (jobStatus) {
    case 'creating': return 'Creation du job...'
    case 'uploading': return 'Upload en cours...'
    case 'polling': return `En attente de traitement (${jobState ?? '...'})`
    case 'done': return `Termine: ${jobState}`
    default: return jobState ?? ''
  }
}
