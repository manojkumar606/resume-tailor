import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import {
  Button,
  Card,
  CardTitle,
  EmptyState,
  ErrorNote,
  Field,
  Input,
  Pill,
  Spinner,
  Textarea,
} from '../components/ui'
import { api } from '../lib/api'
import type { Job, Resume } from '../lib/types'

const MIN_DESCRIPTION_LENGTH = 50

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : 'Something went wrong.'
}

// ── Resumes ──────────────────────────────────────────────────────────────────

function ResumesPanel({
  resumes,
  loading,
  error,
  onChanged,
}: {
  resumes: Resume[]
  loading: boolean
  error: string | null
  onChanged: () => void
}) {
  const fileInput = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)

  async function run(action: () => Promise<unknown>) {
    setLocalError(null)
    setBusy(true)
    try {
      await action()
      onChanged()
    } catch (err) {
      setLocalError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function handleFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    await run(() => api.resumes.upload(file))
    // Reset so re-picking the same file still fires a change event.
    if (fileInput.current) fileInput.current.value = ''
  }

  return (
    <Card>
      <div className="mb-4 flex items-center justify-between gap-3">
        <CardTitle>Resumes</CardTitle>
        <Button
          variant="secondary"
          loading={busy}
          onClick={() => fileInput.current?.click()}
        >
          Upload
        </Button>
        <input
          ref={fileInput}
          type="file"
          accept=".docx,.pdf,.txt,.md"
          onChange={handleFile}
          className="hidden"
        />
      </div>

      <ErrorNote>{error ?? localError}</ErrorNote>

      {loading ? (
        <Spinner label="Loading resumes…" />
      ) : resumes.length === 0 ? (
        <EmptyState>Upload a .docx or .pdf to get started.</EmptyState>
      ) : (
        <ul className="divide-y divide-edge">
          {resumes.map((resume) => (
            <li
              key={resume.id}
              className="flex flex-wrap items-center gap-x-3 gap-y-2 py-3"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-ink">{resume.name}</p>
                <p className="mt-0.5 text-xs text-ink-faint">
                  {new Date(resume.created_at).toLocaleDateString()}
                </p>
              </div>

              {resume.is_default ? (
                <Pill tone="brand">Default</Pill>
              ) : (
                <Button
                  variant="ghost"
                  disabled={busy}
                  onClick={() => run(() => api.resumes.setDefault(resume.id))}
                >
                  Set default
                </Button>
              )}

              <Button
                variant="ghost"
                disabled={busy}
                aria-label={`Delete ${resume.name}`}
                onClick={() => run(() => api.resumes.remove(resume.id))}
                className="text-brand hover:text-brand-hover"
              >
                Delete
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

// ── Jobs ─────────────────────────────────────────────────────────────────────

const EMPTY_JOB = { title: '', company: '', location: '', description: '' }

function JobsPanel({
  jobs,
  loading,
  error,
  onChanged,
}: {
  jobs: Job[]
  loading: boolean
  error: string | null
  onChanged: () => void
}) {
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_JOB)
  const [busy, setBusy] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)

  const remaining = MIN_DESCRIPTION_LENGTH - form.description.trim().length

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setLocalError(null)
    setBusy(true)
    try {
      await api.jobs.create({
        title: form.title.trim(),
        company: form.company.trim(),
        location: form.location.trim() || null,
        description: form.description.trim(),
      })
      setForm(EMPTY_JOB)
      setShowForm(false)
      onChanged()
    } catch (err) {
      setLocalError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <div className="mb-4 flex items-center justify-between gap-3">
        <CardTitle>Jobs</CardTitle>
        <Button variant="secondary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? 'Cancel' : 'Add job'}
        </Button>
      </div>

      <ErrorNote>{error ?? localError}</ErrorNote>

      {showForm && (
        <form onSubmit={handleSubmit} className="mb-5 space-y-3.5">
          <Field label="Job title">
            <Input
              required
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />
          </Field>
          <Field label="Company">
            <Input
              required
              value={form.company}
              onChange={(e) => setForm({ ...form, company: e.target.value })}
            />
          </Field>
          <Field label="Location" hint="Optional">
            <Input
              value={form.location}
              onChange={(e) => setForm({ ...form, location: e.target.value })}
            />
          </Field>
          <Field
            label="Job description"
            hint={
              remaining > 0
                ? `${remaining} more characters needed`
                : 'Paste the whole posting — more detail gives a better rewrite'
            }
          >
            <Textarea
              required
              rows={8}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </Field>
          <Button type="submit" loading={busy} disabled={remaining > 0}>
            Save job
          </Button>
        </form>
      )}

      {loading ? (
        <Spinner label="Loading jobs…" />
      ) : jobs.length === 0 ? (
        <EmptyState>Paste a job description to begin.</EmptyState>
      ) : (
        <ul className="divide-y divide-edge">
          {jobs.map((job) => (
            <li key={job.id}>
              <Link
                to={`/jobs/${job.id}`}
                className="group -mx-2 flex min-h-11 items-center gap-3 rounded-lg px-2 py-3 transition-colors hover:bg-raised"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-ink group-hover:text-brand">
                    {job.title}
                  </p>
                  <p className="mt-0.5 truncate text-xs text-ink-muted">
                    {job.company}
                    {job.location ? ` · ${job.location}` : ''}
                  </p>
                </div>
                <span aria-hidden className="text-ink-faint group-hover:text-brand">
                  →
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export function DashboardPage() {
  const [resumes, setResumes] = useState<Resume[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      const [nextResumes, nextJobs] = await Promise.all([
        api.resumes.list(),
        api.jobs.list(),
      ])
      setResumes(nextResumes)
      setJobs(nextJobs)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Dashboard</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Upload a resume, add a job, then open the job to tailor.
        </p>
      </header>

      <div className="grid gap-5 lg:grid-cols-2 lg:items-start">
        <ResumesPanel
          resumes={resumes}
          loading={loading}
          error={error}
          onChanged={load}
        />
        <JobsPanel jobs={jobs} loading={loading} error={error} onChanged={load} />
      </div>
    </div>
  )
}
