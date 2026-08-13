import { useCallback, useEffect, useState } from 'react'

import {
  Button,
  Card,
  CardTitle,
  ErrorNote,
  Field,
  Input,
  Pill,
  Select,
  Spinner,
  Textarea,
} from '../components/ui'
import { api } from '../lib/api'
import type { Application, ApplicationStatus, QuickAddInput } from '../lib/types'

const COLUMNS: { status: ApplicationStatus; label: string }[] = [
  { status: 'saved', label: 'Saved' },
  { status: 'applied', label: 'Applied' },
  { status: 'interviewing', label: 'Interviewing' },
  { status: 'offer', label: 'Offer' },
  { status: 'rejected', label: 'Rejected' },
]

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : 'Something went wrong.'
}

// ── Card badges ──────────────────────────────────────────────────────────────

function DeadlineBadge({ days }: { days: number | null }) {
  if (days === null) return null

  if (days < 0) return <Pill tone="brand">Closed</Pill>
  if (days === 0) return <Pill tone="brand">Closes today</Pill>
  if (days <= 3) return <Pill tone="brand">{days}d to apply</Pill>
  return <Pill tone="quiet">{days}d to apply</Pill>
}

function ScoreBadge({ score }: { score: number | null | undefined }) {
  if (score === null || score === undefined) return null
  return <Pill tone="neutral">{Math.round(score)}/100</Pill>
}

// ── One card ─────────────────────────────────────────────────────────────────

function ApplicationCard({
  application,
  busy,
  dragging,
  onMove,
  onSaveNotes,
  onDelete,
  onDragStart,
  onDragEnd,
}: {
  application: Application
  busy: boolean
  dragging: boolean
  onMove: (status: ApplicationStatus) => void
  onSaveNotes: (notes: string | null) => void
  onDelete: () => void
  onDragStart: (event: React.DragEvent) => void
  onDragEnd: () => void
}) {
  const [open, setOpen] = useState(false)
  const [notes, setNotes] = useState(application.notes ?? '')

  const { job, tailoring } = application
  const gaps = tailoring?.missing_keywords ?? []

  return (
    <li
      // Desktop affordance only — HTML5 drag does not fire on touch, which is
      // why every card also carries the status selector below.
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      // Lifting and tilting the card while it is held makes the drag feel
      // physical, and makes it obvious which one is moving.
      className={`cursor-grab rounded-lg bg-raised p-3 ring-1 transition-all active:cursor-grabbing ${
        dragging
          ? 'rotate-[1.5deg] scale-[1.03] opacity-90 shadow-lg shadow-black/50 ring-brand'
          : 'ring-edge hover:ring-edge-strong'
      } ${busy ? 'opacity-50' : ''}`}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        className="block w-full text-left"
        aria-expanded={open}
      >
        <p className="text-sm font-medium text-ink">{job.title}</p>
        <p className="mt-0.5 text-xs text-ink-muted">
          {job.company}
          {job.location ? ` · ${job.location}` : ''}
        </p>
      </button>

      {(application.is_stale ||
        application.days_until_deadline !== null ||
        tailoring) && (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {application.is_stale && (
            <Pill tone="brand">No reply in {application.days_since_update}d</Pill>
          )}
          <DeadlineBadge days={application.days_until_deadline} />
          <ScoreBadge score={tailoring?.match_score} />
        </div>
      )}

      {open && (
        <div className="mt-3 space-y-3 border-t border-edge pt-3">
          {job.source_url && (
            <a
              href={job.source_url}
              target="_blank"
              rel="noreferrer"
              className="block text-xs font-medium text-brand hover:underline"
            >
              Open the original posting ↗
            </a>
          )}

          {gaps.length > 0 && (
            <div>
              <p className="mb-1.5 text-xs text-ink-faint">
                Likely interview questions — gaps in your resume for this role:
              </p>
              <ul className="flex flex-wrap gap-1.5">
                {gaps.slice(0, 6).map((gap) => (
                  <li key={gap}>
                    <Pill tone="brand">{gap}</Pill>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <label className="block">
            <span className="mb-1 block text-xs text-ink-faint">Notes</span>
            <Textarea
              rows={3}
              value={notes}
              placeholder="Referred by Priya, recruiter calling Tuesday…"
              onChange={(e) => setNotes(e.target.value)}
              className="text-sm"
            />
          </label>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              disabled={busy || notes === (application.notes ?? '')}
              onClick={() => onSaveNotes(notes.trim() || null)}
            >
              Save notes
            </Button>
            <Button
              variant="ghost"
              disabled={busy}
              onClick={onDelete}
              className="ml-auto text-brand hover:text-brand-hover"
            >
              Remove
            </Button>
          </div>

          {application.applied_at && (
            <p className="text-xs text-ink-faint">
              Applied {new Date(application.applied_at).toLocaleDateString()}
            </p>
          )}
        </div>
      )}

      {/* The move control that works everywhere, including touch. */}
      <Select
        aria-label={`Move ${job.title}`}
        value={application.status}
        disabled={busy}
        onChange={(e) => onMove(e.target.value as ApplicationStatus)}
        className="mt-2.5 min-h-9 py-1.5 text-xs"
      >
        {COLUMNS.map((column) => (
          <option key={column.status} value={column.status}>
            {column.label}
          </option>
        ))}
      </Select>
    </li>
  )
}

// ── Quick add ────────────────────────────────────────────────────────────────

const EMPTY: QuickAddInput = { title: '', company: '' }

function QuickAddForm({ onAdded }: { onAdded: () => void }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<QuickAddInput>(EMPTY)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await api.applications.quickAdd({
        title: form.title.trim(),
        company: form.company.trim(),
        location: form.location?.trim() || null,
        source_url: form.source_url?.trim() || null,
        apply_by: form.apply_by || null,
        status: form.status ?? 'saved',
      })
      setForm(EMPTY)
      setOpen(false)
      onAdded()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <Button variant="secondary" onClick={() => setOpen(true)}>
        Log an application
      </Button>
    )
  }

  return (
    <Card className="w-full">
      <div className="mb-4 flex items-center justify-between gap-3">
        <CardTitle>Log an application</CardTitle>
        <Button variant="ghost" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>

      <form onSubmit={handleSubmit} className="space-y-3.5">
        <div className="grid gap-3.5 sm:grid-cols-2">
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
              value={form.location ?? ''}
              onChange={(e) => setForm({ ...form, location: e.target.value })}
            />
          </Field>
          <Field label="Link to the posting" hint="Optional">
            <Input
              type="url"
              inputMode="url"
              placeholder="https://…"
              value={form.source_url ?? ''}
              onChange={(e) => setForm({ ...form, source_url: e.target.value })}
            />
          </Field>
          <Field label="Last date to apply" hint="Optional">
            <Input
              type="date"
              value={form.apply_by ?? ''}
              onChange={(e) => setForm({ ...form, apply_by: e.target.value })}
            />
          </Field>
          <Field label="Where does it start?">
            <Select
              value={form.status ?? 'saved'}
              onChange={(e) =>
                setForm({ ...form, status: e.target.value as ApplicationStatus })
              }
            >
              {COLUMNS.map((column) => (
                <option key={column.status} value={column.status}>
                  {column.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <p className="text-xs text-ink-faint">
          No job description needed — that is only for tailoring a resume. Add
          jobs you want tailored from the dashboard instead.
        </p>

        <ErrorNote>{error}</ErrorNote>

        <Button type="submit" loading={busy}>
          Add to board
        </Button>
      </form>
    </Card>
  )
}

// ── Stats ────────────────────────────────────────────────────────────────────

const SUBMITTED: ApplicationStatus[] = [
  'applied',
  'interviewing',
  'offer',
  'rejected',
]

/**
 * Turns the board into a diagnosis rather than a list.
 *
 * The response rate is the useful one: 20 applications and no replies is a
 * resume problem, 3 and no replies is a volume problem, and those call for
 * completely different responses. The most common gap answers "what should I
 * learn next" from data the app already has.
 */
function StatStrip({ applications }: { applications: Application[] }) {
  const submitted = applications.filter((a) => SUBMITTED.includes(a.status))
  const heard = applications.filter(
    (a) => a.status === 'interviewing' || a.status === 'offer',
  )
  const responseRate = submitted.length
    ? Math.round((heard.length / submitted.length) * 100)
    : null

  const counts = new Map<string, number>()
  for (const a of applications) {
    for (const gap of a.tailoring?.missing_keywords ?? []) {
      counts.set(gap, (counts.get(gap) ?? 0) + 1)
    }
  }
  const topGap = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]

  const stats: { label: string; value: string; hint?: string }[] = [
    { label: 'Applied', value: String(submitted.length) },
    {
      label: 'Heard back',
      value: responseRate === null ? '—' : `${responseRate}%`,
      hint: responseRate === null ? 'Nothing submitted yet' : undefined,
    },
    {
      label: 'Awaiting a reply',
      value: String(applications.filter((a) => a.is_stale).length),
      hint: 'No movement in 14 days',
    },
    {
      label: 'Most common gap',
      value: topGap ? topGap[0] : '—',
      hint: topGap
        ? `Blocking ${topGap[1]} ${topGap[1] === 1 ? 'role' : 'roles'} — worth learning next`
        : 'Tailor a resume to see this',
    },
  ]

  return (
    <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {stats.map((stat) => (
        <div
          key={stat.label}
          className="rounded-xl bg-panel p-4 ring-1 ring-edge"
        >
          <dt className="text-xs text-ink-faint">{stat.label}</dt>
          <dd className="mt-1.5 truncate text-xl font-semibold text-ink" title={stat.value}>
            {stat.value}
          </dd>
          {stat.hint && (
            <p className="mt-1 text-[11px] leading-snug text-ink-faint">{stat.hint}</p>
          )}
        </div>
      ))}
    </dl>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export function BoardPage() {
  const [applications, setApplications] = useState<Application[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState<ApplicationStatus | null>(null)
  const [draggingId, setDraggingId] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      setApplications(await api.applications.list())
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function move(application: Application, status: ApplicationStatus) {
    if (status === application.status) return

    // Optimistic: a card that lags behind the drop feels broken. Reverted below
    // if the request fails.
    const previous = applications
    setApplications((current) =>
      current.map((a) => (a.id === application.id ? { ...a, status } : a)),
    )
    setBusyId(application.id)
    setError(null)
    try {
      const updated = await api.applications.update(application.id, { status })
      // Take the server's copy: it recalculates applied_at and the badges.
      setApplications((current) =>
        current.map((a) => (a.id === updated.id ? updated : a)),
      )
    } catch (err) {
      setApplications(previous)
      setError(errorMessage(err))
    } finally {
      setBusyId(null)
    }
  }

  async function saveNotes(application: Application, notes: string | null) {
    setBusyId(application.id)
    setError(null)
    try {
      const updated = await api.applications.update(application.id, { notes })
      setApplications((current) =>
        current.map((a) => (a.id === updated.id ? updated : a)),
      )
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusyId(null)
    }
  }

  async function remove(application: Application) {
    setBusyId(application.id)
    setError(null)
    try {
      await api.applications.remove(application.id)
      setApplications((current) => current.filter((a) => a.id !== application.id))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusyId(null)
    }
  }

  function handleDrop(event: React.DragEvent, status: ApplicationStatus) {
    event.preventDefault()
    setDragOver(null)
    setDraggingId(null)
    const id = event.dataTransfer.getData('text/plain')
    const application = applications.find((a) => a.id === id)
    if (application) void move(application, status)
  }

  if (loading) return <Spinner label="Loading your board…" />

  const stale = applications.filter((a) => a.is_stale).length
  const closingSoon = applications.filter(
    (a) => a.days_until_deadline !== null && a.days_until_deadline >= 0 && a.days_until_deadline <= 3,
  ).length

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">Board</h1>
          <p className="mt-1 text-sm text-ink-muted">
            {applications.length === 0
              ? 'Every job you apply to, in one place.'
              : `${applications.length} tracked` +
                (stale ? ` · ${stale} awaiting a reply` : '') +
                (closingSoon ? ` · ${closingSoon} closing soon` : '')}
          </p>
        </div>
        <QuickAddForm onAdded={load} />
      </header>

      <ErrorNote>{error}</ErrorNote>

      {applications.length > 0 && <StatStrip applications={applications} />}

      {applications.length === 0 ? (
        <Card>
          <p className="py-6 text-center text-sm text-ink-muted">
            Nothing tracked yet. Use <strong className="text-ink">Log an
            application</strong> for jobs you have already applied to — no resume
            or job description required.
          </p>
        </Card>
      ) : (
        // Horizontal scroll with snap: five columns never fit a phone, and
        // stacking them loses the sense of a pipeline.
        <div className="-mx-4 flex snap-x snap-mandatory gap-4 overflow-x-auto px-4 pb-4">
          {COLUMNS.map((column) => {
            const cards = applications.filter((a) => a.status === column.status)
            return (
              <section
                key={column.status}
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragOver(column.status)
                }}
                onDragLeave={() => setDragOver(null)}
                onDrop={(e) => handleDrop(e, column.status)}
                className={`w-[85vw] shrink-0 snap-start rounded-xl bg-panel p-3 ring-1 transition-colors sm:w-72 ${
                  dragOver === column.status ? 'ring-brand' : 'ring-edge'
                }`}
              >
                <div className="mb-3 flex items-center justify-between gap-2 px-1">
                  <CardTitle>{column.label}</CardTitle>
                  <span className="text-xs tabular-nums text-ink-faint">
                    {cards.length}
                  </span>
                </div>

                <ul className="space-y-2.5">
                  {cards.map((application) => (
                    <ApplicationCard
                      key={application.id}
                      application={application}
                      busy={busyId === application.id}
                      dragging={draggingId === application.id}
                      onMove={(status) => void move(application, status)}
                      onSaveNotes={(notes) => void saveNotes(application, notes)}
                      onDelete={() => void remove(application)}
                      onDragStart={(e) => {
                        e.dataTransfer.setData('text/plain', application.id)
                        setDraggingId(application.id)
                      }}
                      onDragEnd={() => setDraggingId(null)}
                    />
                  ))}
                </ul>

                {cards.length === 0 && (
                  <p className="px-1 py-4 text-xs text-ink-faint">Nothing here.</p>
                )}
              </section>
            )
          })}
        </div>
      )}
    </div>
  )
}
