import { useCallback, useEffect, useState } from 'react'

import { useAuth } from '../auth/AuthContext'
import {
  Button,
  Card,
  CardTitle,
  ErrorNote,
  Input,
  Spinner,
  Toggle,
} from '../components/ui'
import { api } from '../lib/api'
import type { DeviceSession, UUID } from '../lib/types'

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : 'Something went wrong.'
}

/** "3 minutes ago", "yesterday". Absolute timestamps make the reader do
 *  arithmetic to answer the only question that matters: is this recent? */
function relativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return 'unknown'

  const seconds = Math.round((Date.now() - then) / 1000)
  if (seconds < 90) return 'just now'

  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`

  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} ${hours === 1 ? 'hour' : 'hours'} ago`

  const days = Math.round(hours / 24)
  if (days === 1) return 'yesterday'
  return `${days} days ago`
}

// ── Signed-in devices ────────────────────────────────────────────────────────

function SessionsCard() {
  const [rows, setRows] = useState<DeviceSession[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<UUID | 'all' | null>(null)

  const load = useCallback(async () => {
    try {
      setRows(await api.account.sessions())
    } catch (err) {
      setError(errorMessage(err))
      setRows([])
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function revokeOne(id: UUID) {
    setError(null)
    setBusyId(id)
    try {
      await api.account.revokeSession(id)
      await load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusyId(null)
    }
  }

  async function revokeOthers() {
    setError(null)
    setBusyId('all')
    try {
      await api.account.revokeOtherSessions()
      await load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusyId(null)
    }
  }

  const others = (rows ?? []).filter((row) => !row.is_current).length

  return (
    <Card>
      <CardTitle>Signed-in devices</CardTitle>
      <p className="mt-2 text-sm leading-relaxed text-ink-muted">
        Anything signed in to this account. Sessions end on their own after two
        hours of inactivity — but if you spot something you don't recognise, or
        left yourself signed in somewhere, end it here.
      </p>

      {rows === null ? (
        <div className="mt-4">
          <Spinner label="Loading devices" />
        </div>
      ) : (
        <ul className="mt-4 divide-y divide-edge">
          {rows.map((row) => (
            <li
              key={row.id}
              className="flex flex-wrap items-center justify-between gap-3 py-3"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-ink">
                  {row.device}
                  {row.is_current && (
                    <span className="ml-2 rounded-full bg-raised px-2 py-0.5 text-xs font-normal text-ink-muted ring-1 ring-edge">
                      This device
                    </span>
                  )}
                </p>
                <p className="mt-0.5 text-xs text-ink-faint">
                  Last active {relativeTime(row.last_used_at)} · signed in{' '}
                  {relativeTime(row.created_at)}
                </p>
              </div>

              {/* No sign-out button on the current row: that is what the header
                  button does, and offering it twice invites confusion about
                  whether it means "here" or "everywhere". */}
              {!row.is_current && (
                <Button
                  variant="secondary"
                  loading={busyId === row.id}
                  onClick={() => revokeOne(row.id)}
                >
                  Sign out
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      {others > 0 && (
        <div className="mt-4 border-t border-edge pt-4">
          <Button
            variant="secondary"
            loading={busyId === 'all'}
            onClick={revokeOthers}
          >
            Sign out {others === 1 ? 'the other device' : `all ${others} others`}
          </Button>
        </div>
      )}

      {error && (
        <div className="mt-4">
          <ErrorNote>{error}</ErrorNote>
        </div>
      )}
    </Card>
  )
}

// ── Reminders ────────────────────────────────────────────────────────────────

function RemindersCard() {
  const { user, refresh } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const enabled = user?.reminders_enabled ?? true

  async function toggle(next: boolean) {
    setError(null)
    setBusy(true)
    try {
      await api.account.update({ reminders_enabled: next })
      await refresh()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <div className="flex items-start justify-between gap-4">
        <div>
          <CardTitle>Reminder emails</CardTitle>
          <p className="mt-2 text-sm leading-relaxed text-ink-muted">
            One digest when a deadline is close on something you haven't applied
            to, or when an application has gone quiet for two weeks. Never more
            than one email at a time, and never about the same role twice in a
            week.
          </p>
          <p className="mt-2 text-xs text-ink-faint">
            Sign-in codes are separate and always sent — turning this off cannot
            lock you out.
          </p>
        </div>

        <Toggle
          checked={enabled}
          disabled={busy}
          onChange={toggle}
          label="Reminder emails"
        />
      </div>

      <ErrorNote>{error}</ErrorNote>
    </Card>
  )
}

// ── Export ───────────────────────────────────────────────────────────────────

function ExportCard() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function download() {
    setError(null)
    setBusy(true)
    try {
      await api.account.exportCsv()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardTitle>Your data</CardTitle>
      <p className="mt-2 text-sm leading-relaxed text-ink-muted">
        Every tracked application as a spreadsheet — status, dates, match scores,
        gaps and your notes.
      </p>
      <div className="mt-4">
        <Button variant="secondary" loading={busy} onClick={download}>
          Download CSV
        </Button>
      </div>
      <ErrorNote>{error}</ErrorNote>
    </Card>
  )
}

// ── Deletion ─────────────────────────────────────────────────────────────────

function DangerCard() {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Typing the address back is the confirmation. An irreversible action needs
  // more friction than a dialog you can dismiss by reflex.
  const matches = typed.trim().toLowerCase() === (user?.email ?? '').toLowerCase()

  async function remove() {
    setError(null)
    setBusy(true)
    try {
      await api.account.remove(typed.trim())
      logout()
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  return (
    <Card className="ring-brand/30">
      <CardTitle>Delete your account</CardTitle>
      <p className="mt-2 text-sm leading-relaxed text-ink-muted">
        Removes your resumes, jobs, tailored versions and board. Immediate and
        permanent — there is no recovery.
      </p>

      {!open ? (
        <div className="mt-4">
          <Button variant="danger" onClick={() => setOpen(true)}>
            Delete my account
          </Button>
        </div>
      ) : (
        <div className="mt-4 space-y-3">
          <label className="block">
            <span className="mb-1.5 block text-sm text-ink">
              Type <span className="font-medium">{user?.email}</span> to confirm
            </span>
            <Input
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoComplete="off"
              autoCapitalize="none"
              placeholder={user?.email}
            />
          </label>

          <div className="flex flex-wrap gap-3">
            <Button
              variant="danger"
              loading={busy}
              disabled={!matches}
              onClick={remove}
            >
              Delete permanently
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setOpen(false)
                setTyped('')
                setError(null)
              }}
            >
              Cancel
            </Button>
          </div>

          <p className="text-xs text-ink-faint">
            Consider downloading your CSV first.
          </p>
        </div>
      )}

      <ErrorNote>{error}</ErrorNote>
    </Card>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export function SettingsPage() {
  const { user } = useAuth()

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Settings</h1>
        <p className="mt-1 text-sm text-ink-muted">{user?.email}</p>
      </header>

      <div className="space-y-5">
        <SessionsCard />
        <RemindersCard />
        <ExportCard />
        <DangerCard />
      </div>
    </div>
  )
}
