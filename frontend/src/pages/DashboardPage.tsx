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
import type { Job, Resume, UUID } from '../lib/types'

// Only enforced when a description is actually supplied — it is optional now,
// and only needed for tailoring.
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

const EMPTY_JOB = {
  title: '',
  company: '',
  location: '',
  description: '',
  apply_by: '',
}

function JobsPanel({
  jobs,
  trackedJobIds,
  loading,
  error,
  onChanged,
}: {
  jobs: Job[]
  trackedJobIds: Set<UUID>
  loading: boolean
  error: string | null
  onChanged: () => void
}) {
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY_JOB)
  const [busy, setBusy] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)

  const description = form.description.trim()
  // Empty is fine; a couple of words is a mistake worth catching before submit.
  const tooShort =
    description.length > 0 && description.length < MIN_DESCRIPTION_LENGTH

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setLocalError(null)
    setBusy(true)
    try {
      await api.jobs.create({
        title: form.title.trim(),
        company: form.company.trim(),
        location: form.location.trim() || null,
        description: description || null,
        apply_by: form.apply_by || null,
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

  async function track(jobId: UUID) {
    setLocalError(null)
    setBusy(true)
    try {
      await api.applications.track(jobId)
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
          <div className="grid gap-3.5 sm:grid-cols-2">
            <Field label="Location" hint="Optional">
              <Input
                value={form.location}
                onChange={(e) => setForm({ ...form, location: e.target.value })}
              />
            </Field>
            <Field label="Last date to apply" hint="Optional">
              <Input
                type="date"
                value={form.apply_by}
                onChange={(e) => setForm({ ...form, apply_by: e.target.value })}
              />
            </Field>
          </div>
          <Field
            label="Job description"
            hint={
              tooShort
                ? `Needs ${MIN_DESCRIPTION_LENGTH - description.length} more characters, or leave it empty`
                : 'Only needed to tailor a resume — leave empty to just track it'
            }
          >
            <Textarea
              rows={8}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </Field>
          <Button type="submit" loading={busy} disabled={tooShort}>
            Save job
          </Button>
        </form>
      )}

      {loading ? (
        <Spinner label="Loading jobs…" />
      ) : jobs.length === 0 ? (
        <EmptyState>
          Paste a job description to tailor against, or{' '}
          <Link to="/board" className="text-brand hover:underline">
            log an application
          </Link>{' '}
          on the board.
        </EmptyState>
      ) : (
        <ul className="divide-y divide-edge">
          {jobs.map((job) => (
            <li key={job.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 py-3">
              <Link
                to={`/jobs/${job.id}`}
                className="group min-w-0 flex-1 rounded-lg py-1 transition-colors"
              >
                <p className="truncate text-sm font-medium text-ink group-hover:text-brand">
                  {job.title}
                </p>
                <p className="mt-0.5 truncate text-xs text-ink-muted">
                  {job.company}
                  {job.location ? ` · ${job.location}` : ''}
                </p>
              </Link>

              {!job.has_description && <Pill tone="quiet">No description</Pill>}

              {trackedJobIds.has(job.id) ? (
                <Pill tone="neutral">On board</Pill>
              ) : (
                <Button variant="ghost" disabled={busy} onClick={() => track(job.id)}>
                  Track
                </Button>
              )}
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
  const [trackedJobIds, setTrackedJobIds] = useState<Set<UUID>>(new Set())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      const [nextResumes, nextJobs, applications] = await Promise.all([
        api.resumes.list(),
        api.jobs.list(),
        api.applications.list(),
      ])
      setResumes(nextResumes)
      setJobs(nextJobs)
      // So a job already on the board offers no misleading "Track" button.
      setTrackedJobIds(new Set(applications.map((a) => a.job.id)))
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
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Tailor</h1>
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
        <JobsPanel
          jobs={jobs}
          trackedJobIds={trackedJobIds}
          loading={loading}
          error={error}
          onChanged={load}
        />
      </div>
    </div>
  )
}
