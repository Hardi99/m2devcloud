import { useState, useRef, useEffect } from 'react'
import * as signalR from '@microsoft/signalr'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:80'
const FUNCTIONS_URL = import.meta.env.VITE_FUNCTIONS_URL || 'https://tabuna-function-anhkhff5h0asdph8.francecentral-01.azurewebsites.net'

type JobStatus = 'idle' | 'creating' | 'uploading' | 'connecting' | 'waiting' | 'done' | 'error'

interface JobResponse {
  jobId: string
  status: string
  createdAt: string
  uploadUrl: string
}

interface SignalREvent {
  documentId: string
  status: string
  message: string
  tags?: string[]
}

export default function App() {
  const [file, setFile] = useState<File | null>(null)
  const [jobStatus, setJobStatus] = useState<JobStatus>('idle')
  const [jobId, setJobId] = useState<string | null>(null)
  const [jobState, setJobState] = useState<string | null>(null)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [tags, setTags] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const connectionRef = useRef<signalR.HubConnection | null>(null)

  const stopConnection = () => {
    if (connectionRef.current) {
      connectionRef.current.stop()
      connectionRef.current = null
    }
  }

  useEffect(() => () => stopConnection(), [])

  const startSignalR = (id: string) => {
    const connection = new signalR.HubConnectionBuilder()
      .withUrl(`${FUNCTIONS_URL}/api/negotiate`)
      .withAutomaticReconnect()
      .build()

    connection.on('documentStatus', (event: SignalREvent) => {
      if (event.documentId !== id) return
      setJobState(event.status)
      setStatusMessage(event.message)
      if (event.tags) setTags(event.tags)
      if (event.status === 'PROCESSED' || event.status === 'ERROR') {
        setJobStatus('done')
        connection.stop()
      }
    })

    connection.start()
      .then(() => setJobStatus('waiting'))
      .catch((e) => {
        setError(`SignalR connexion échouée : ${e}`)
        setJobStatus('error')
      })

    connectionRef.current = connection
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!file) return

    setError(null)
    setJobId(null)
    setJobState(null)
    setStatusMessage(null)
    setTags([])
    stopConnection()

    try {
      setJobStatus('creating')
      const createRes = await fetch(`${API_URL}/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          fileName: file.name,
          contentType: file.type || 'application/octet-stream',
        }),
      })
      if (!createRes.ok) throw new Error(`Création du job échouée (${createRes.status})`)
      const job: JobResponse = await createRes.json()
      setJobId(job.jobId)
      setJobState(job.status)

      setJobStatus('uploading')
      const uploadRes = await fetch(job.uploadUrl, {
        method: 'PUT',
        headers: {
          'Content-Type': file.type || 'application/octet-stream',
          'x-ms-blob-type': 'BlockBlob',
        },
        body: file,
      })
      if (!uploadRes.ok) throw new Error(`Upload échoué (${uploadRes.status})`)

      setJobStatus('connecting')
      startSignalR(job.jobId)
    } catch (e) {
      stopConnection()
      setError((e as Error).message)
      setJobStatus('error')
    }
  }

  const reset = () => {
    stopConnection()
    setFile(null)
    setJobStatus('idle')
    setJobId(null)
    setJobState(null)
    setStatusMessage(null)
    setTags([])
    setError(null)
  }

  const isLoading = ['creating', 'uploading', 'connecting', 'waiting'].includes(jobStatus)

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
          <p className="file-name">{file.name} ({(file.size / 1024).toFixed(1)} Ko)</p>
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
              {jobState ?? '...'}
            </span>
          </p>
          {statusMessage && <p className="status-message">{statusMessage}</p>}
          {tags.length > 0 && (
            <div className="tags">
              <strong>Tags :</strong>
              <div className="tag-list">
                {tags.map((tag) => (
                  <span key={tag} className="tag">{tag}</span>
                ))}
              </div>
            </div>
          )}
          {jobStatus === 'done' && (
            <button onClick={reset} className="reset-btn">Nouveau fichier</button>
          )}
        </div>
      )}
    </div>
  )
}
