// Demonstrates the three backend patterns end to end:
//   1. presigned S3 upload (browser PUTs straight to S3)
//   2. async worker job (create → poll status → show result)
//   3. Bedrock LLM call
import { useRef, useState } from 'react'
import { api } from '../lib/api'
import type { Job } from '../lib/api'
import { useAuth } from '../contexts/AuthContext'

export function HomePage() {
  const { user, logout } = useAuth()

  return (
    <>
      <header className="topbar">
        <h1>myapp</h1>
        <div>
          <span className="muted" style={{ marginRight: '1rem' }}>
            {user?.name} ({user?.role})
          </span>
          <button className="secondary" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>
      <main className="page">
        <JobDemo />
        <AiDemo />
      </main>
    </>
  )
}

function JobDemo() {
  const fileRef = useRef<HTMLInputElement>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const run = async () => {
    const file = fileRef.current?.files?.[0]
    if (!file) return
    setBusy(true)
    setError('')
    setJob(null)
    try {
      // 1. presign + direct-to-S3 PUT
      const { upload_url, s3_key } = await api.presignUpload(
        file.name,
        file.type || 'application/octet-stream',
      )
      await api.uploadToS3(upload_url, file)

      // 2. start the async job, then poll until it settles
      const { run_id } = await api.createJob(s3_key)
      for (let i = 0; i < 120; i++) {
        const j = await api.getJob(run_id)
        setJob(j)
        if (j.status === 'done' || j.status === 'error') break
        await new Promise((r) => setTimeout(r, 1000))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Job failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card">
      <h2>Async job demo — upload a text file, worker counts its words</h2>
      <p className="muted">
        Presigned S3 upload → worker Lambda → status polling. Replace the worker body with real
        work.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          void run()
        }}
      >
        <input type="file" ref={fileRef} required />
        <button type="submit" disabled={busy}>
          {busy ? 'Working…' : 'Upload & run job'}
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      {job && (
        <div className="result">
          status: {job.status}
          {job.result && `\nwords: ${job.result.words}\nlines: ${job.result.lines}\nbytes: ${job.result.bytes}`}
          {job.error_msg && `\nerror: ${job.error_msg}`}
        </div>
      )}
    </section>
  )
}

function AiDemo() {
  const [prompt, setPrompt] = useState('')
  const [reply, setReply] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const run = async () => {
    setBusy(true)
    setError('')
    setReply('')
    try {
      const res = await api.aiEcho(prompt)
      setReply(`[${res.model}]\n${res.reply}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI call failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card">
      <h2>Bedrock demo — send a prompt to the configured model</h2>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          void run()
        }}
      >
        <textarea
          rows={3}
          placeholder="Ask the model something…"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          required
        />
        <button type="submit" disabled={busy}>
          {busy ? 'Thinking…' : 'Send'}
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      {reply && <div className="result">{reply}</div>}
    </section>
  )
}
