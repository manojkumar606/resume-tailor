import { useState } from 'react'

import { useAuth } from '../auth/AuthContext'
import { Button, Card, CardTitle, ErrorNote, Input, Toggle } from '../components/ui'
import { api } from '../lib/api'

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : 'Something went wrong.'
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
        <RemindersCard />
        <ExportCard />
        <DangerCard />
      </div>
    </div>
  )
}
