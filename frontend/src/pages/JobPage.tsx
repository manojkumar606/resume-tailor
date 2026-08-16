import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import {
  Button,
  Card,
  CardTitle,
  EmptyState,
  ErrorNote,
  Pill,
  Select,
  Spinner,
  Textarea,
} from '../components/ui'
import { RefinePanel } from '../components/RefinePanel'
import { ScoreDial } from '../components/ScoreDial'
import { TailoringProgress } from '../components/TailoringProgress'
import { api } from '../lib/api'
import type { JobDetail, Resume, Tailoring, TailoringDetail } from '../lib/types'

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : 'Something went wrong.'
}

function TailoringResult({
  tailoring,
  onDownload,
  downloading,
}: {
  tailoring: TailoringDetail
  onDownload: () => void
  downloading: boolean
}) {
  if (tailoring.status === 'failed') {
    return (
      <Card>
        <CardTitle>Tailoring failed</CardTitle>
        <ErrorNote>{tailoring.error ?? 'Unknown error.'}</ErrorNote>
      </Card>
    )
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-5 sm:grid-cols-2 sm:items-start">
        <Card>
          <CardTitle>Match score</CardTitle>
          <div className="mt-4">
            <ScoreDial score={tailoring.match_score} />
          </div>
        </Card>

        <Card>
          <CardTitle>Gaps</CardTitle>
          <div className="mt-4">
            {tailoring.missing_keywords?.length ? (
              <>
                <ul className="flex flex-wrap gap-2">
                  {tailoring.missing_keywords.map((keyword) => (
                    <li key={keyword}>
                      <Pill tone="brand">{keyword}</Pill>
                    </li>
                  ))}
                </ul>
                <p className="mt-3 text-xs text-ink-faint">
                  Requirements your resume genuinely does not cover. These were
                  deliberately not invented.
                </p>
              </>
            ) : (
              <p className="text-sm text-ink-muted">No significant gaps identified.</p>
            )}
          </div>
        </Card>
      </div>

      {tailoring.changes?.length ? (
        <Card>
          <CardTitle>What changed</CardTitle>
          <ul className="mt-4 space-y-2.5">
            {tailoring.changes.map((change) => (
              <li key={change} className="flex gap-2.5 text-sm text-ink-muted">
                <span aria-hidden className="text-brand">
                  —
                </span>
                <span>{change}</span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle>Tailored resume</CardTitle>
          <Button onClick={onDownload} loading={downloading}>
            Download .docx
          </Button>
        </div>
        <pre className="mt-4 max-h-96 overflow-auto rounded-lg bg-canvas p-4 font-sans text-xs leading-relaxed whitespace-pre-wrap text-ink-muted ring-1 ring-edge">
          {tailoring.tailored_text}
        </pre>
      </Card>
    </div>
  )
}

export function JobPage() {
  const { jobId = '' } = useParams()

  const [job, setJob] = useState<JobDetail | null>(null)
  const [resumes, setResumes] = useState<Resume[]>([])
  const [history, setHistory] = useState<Tailoring[]>([])
  const [selected, setSelected] = useState<TailoringDetail | null>(null)
  const [resumeId, setResumeId] = useState('')

  const [loading, setLoading] = useState(true)
  const [tailoring, setTailoring] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showDescription, setShowDescription] = useState(false)
  const [editingDescription, setEditingDescription] = useState<string | null>(null)
  const [savingDescription, setSavingDescription] = useState(false)

  const load = useCallback(async () => {
    setError(null)
    try {
      const [jobDetail, resumeList, tailoringList] = await Promise.all([
        api.jobs.get(jobId),
        api.resumes.list(),
        api.tailorings.listForJob(jobId),
      ])
      setJob(jobDetail)
      setResumes(resumeList)
      setHistory(tailoringList)
      setResumeId(resumeList.find((r) => r.is_default)?.id ?? resumeList[0]?.id ?? '')

      // Show the most recent successful run so a refresh doesn't lose results.
      const latest = tailoringList.find((t) => t.status === 'succeeded')
      if (latest) setSelected(await api.tailorings.get(latest.id))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [jobId])

  useEffect(() => {
    void load()
  }, [load])

  async function handleTailor() {
    setError(null)
    setTailoring(true)
    try {
      setSelected(await api.tailorings.create(jobId, resumeId || undefined))
      setHistory(await api.tailorings.listForJob(jobId))
    } catch (err) {
      setError(errorMessage(err))
      // A failed run is still recorded server-side — reflect that in history.
      try {
        setHistory(await api.tailorings.listForJob(jobId))
      } catch {
        // Ignore: the primary error is already shown.
      }
    } finally {
      setTailoring(false)
    }
  }

  /** Same endpoint as a fresh run, with the previous version and a critique. */
  async function handleRefine(feedback: string[], notes: string) {
    if (!selected) return
    setError(null)
    setTailoring(true)
    try {
      setSelected(
        await api.tailorings.create(jobId, resumeId || undefined, {
          refine_of: selected.id,
          feedback,
          feedback_notes: notes || null,
        }),
      )
      setHistory(await api.tailorings.listForJob(jobId))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setTailoring(false)
    }
  }

  async function saveDescription() {
    if (editingDescription === null) return
    setError(null)
    setSavingDescription(true)
    try {
      const updated = await api.jobs.update(jobId, {
        description: editingDescription.trim() || null,
      })
      setJob(updated)
      setEditingDescription(null)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSavingDescription(false)
    }
  }

  async function handleDownload() {
    if (!selected) return
    setDownloading(true)
    try {
      await api.tailorings.download(selected.id)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setDownloading(false)
    }
  }

  if (loading) return <Spinner label="Loading job…" />

  if (!job) {
    return (
      <div className="space-y-4">
        <ErrorNote>{error ?? 'Job not found.'}</ErrorNote>
        <Link to="/app" className="text-sm text-brand hover:underline">
          ← Back to dashboard
        </Link>
      </div>
    )
  }

  const noResumes = resumes.length === 0

  return (
    <div className="space-y-5">
      <header>
        <Link to="/app" className="text-sm text-ink-muted hover:text-ink">
          ← Dashboard
        </Link>
        <h1 className="mt-3 text-2xl font-semibold tracking-tight text-ink">
          {job.title}
        </h1>
        <p className="mt-1 text-sm text-ink-muted">
          {job.company}
          {job.location ? ` · ${job.location}` : ''}
        </p>
      </header>

      <Card>
        {/* Stacks on phones; the select and button sit side by side from sm up. */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="flex-1">
            <span className="mb-1.5 block text-sm font-medium text-ink">
              Resume to tailor
            </span>
            <Select
              value={resumeId}
              onChange={(e) => setResumeId(e.target.value)}
              disabled={noResumes}
            >
              {noResumes && <option value="">No resumes uploaded</option>}
              {resumes.map((resume) => (
                <option key={resume.id} value={resume.id}>
                  {resume.name}
                  {resume.is_default ? ' (default)' : ''}
                </option>
              ))}
            </Select>
          </label>

          <Button
            onClick={handleTailor}
            loading={tailoring}
            disabled={noResumes}
            className="sm:w-auto"
          >
            {selected ? 'Tailor again' : 'Tailor my resume'}
          </Button>
        </div>

        {tailoring && <TailoringProgress />}

        {noResumes && (
          <p className="mt-3 text-sm text-ink-muted">
            Upload a resume on the{' '}
            <Link to="/app" className="text-brand hover:underline">
              dashboard
            </Link>{' '}
            first.
          </p>
        )}

        <ErrorNote>{error}</ErrorNote>
      </Card>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <button
            onClick={() => setShowDescription((v) => !v)}
            className="flex min-h-11 flex-1 items-center justify-between gap-3 text-left"
          >
            <CardTitle>Job description</CardTitle>
            <span aria-hidden className="text-sm font-normal text-ink-faint">
              {showDescription ? 'Hide' : 'Show'}
            </span>
          </button>
          {showDescription && editingDescription === null && (
            <Button
              variant="ghost"
              onClick={() => setEditingDescription(job.description ?? '')}
            >
              Edit
            </Button>
          )}
        </div>

        {showDescription &&
          (editingDescription !== null ? (
            <div className="mt-4 space-y-3">
              {/* Screenshot parsing can truncate a long posting, and tailoring
                  works from exactly this text — so it has to be fixable. */}
              <Textarea
                rows={14}
                value={editingDescription}
                disabled={savingDescription}
                onChange={(e) => setEditingDescription(e.target.value)}
                placeholder="Paste the full posting here…"
              />
              <div className="flex flex-wrap items-center gap-3">
                <Button loading={savingDescription} onClick={saveDescription}>
                  Save description
                </Button>
                <Button
                  variant="ghost"
                  disabled={savingDescription}
                  onClick={() => setEditingDescription(null)}
                >
                  Cancel
                </Button>
                <p className="text-xs text-ink-faint">
                  Tailoring reads this, so a truncated posting gives a weaker
                  rewrite.
                </p>
              </div>
            </div>
          ) : job.description ? (
            <p className="mt-4 text-sm leading-relaxed whitespace-pre-wrap text-ink-muted">
              {job.description}
            </p>
          ) : (
            <p className="mt-4 text-sm text-ink-muted">
              No description saved. Add the posting text to tailor a resume for
              this role.
            </p>
          ))}
      </Card>

      {selected ? (
        <>
          <TailoringResult
            tailoring={selected}
            onDownload={handleDownload}
            downloading={downloading}
          />
          {/* Only a successful version can be revised — a failed run has no
              text to hand back to the model. */}
          {selected.status === 'succeeded' && (
            <RefinePanel onRefine={handleRefine} busy={tailoring} />
          )}
        </>
      ) : (
        <Card>
          <EmptyState>
            No tailored version yet. Pick a resume and tailor it for this role.
          </EmptyState>
        </Card>
      )}

      {history.length > 1 && (
        <Card>
          <CardTitle>Versions</CardTitle>
          <p className="mt-1.5 text-sm text-ink-muted">
            Refining never overwrites — every version stays here.
          </p>

          <ul className="mt-4 divide-y divide-edge">
            {history.map((run, index) => (
              <li key={run.id} className="py-3">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                  {/* History is newest first, so the number counts down. */}
                  <span className="text-sm font-medium text-ink">
                    v{history.length - index}
                  </span>
                  <span className="text-xs text-ink-faint">
                    {new Date(run.created_at).toLocaleString()}
                  </span>
                  {run.status !== 'succeeded' && (
                    <Pill tone="brand">{run.status}</Pill>
                  )}
                  {run.match_score !== null && (
                    <span className="text-xs tabular-nums text-ink-faint">
                      {Math.round(run.match_score)}/100
                    </span>
                  )}

                  {run.id === selected?.id ? (
                    <span className="ml-auto">
                      <Pill tone="neutral">Showing</Pill>
                    </span>
                  ) : (
                    run.status === 'succeeded' && (
                      <Button
                        variant="ghost"
                        className="ml-auto"
                        onClick={async () =>
                          setSelected(await api.tailorings.get(run.id))
                        }
                      >
                        View
                      </Button>
                    )
                  )}
                </div>

                {/* Why this version exists, in the words that produced it. */}
                {(run.feedback?.length || run.feedback_notes) && (
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    <span className="text-xs text-ink-faint">Asked to fix:</span>
                    {run.feedback?.map((item) => (
                      <Pill key={item} tone="quiet">
                        {item}
                      </Pill>
                    ))}
                    {run.feedback_notes && (
                      <span className="text-xs text-ink-muted italic">
                        “{run.feedback_notes}”
                      </span>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
