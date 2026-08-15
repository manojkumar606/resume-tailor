import { useState } from 'react'

import { Button, Card, CardTitle, ErrorNote, Textarea } from './ui'

/**
 * Chips rather than a blank box.
 *
 * "What was wrong with it?" as an empty textarea makes people freeze, and the
 * answers you do get are vague. Fixed options are quicker to answer, give the
 * model unambiguous wording to act on, and — because they are a closed set —
 * become data worth aggregating later.
 */
const PROBLEMS = [
  'Too long',
  'Too generic',
  'Wrong emphasis',
  'Claims I can’t back up',
  'Missed relevant experience',
  'Reads unnaturally',
  'Lost my real job titles',
]

export function RefinePanel({
  onRefine,
  busy,
}: {
  onRefine: (feedback: string[], notes: string) => void
  busy: boolean
}) {
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)

  function toggle(problem: string) {
    setError(null)
    setSelected((current) =>
      current.includes(problem)
        ? current.filter((p) => p !== problem)
        : [...current, problem],
    )
  }

  function handleSubmit() {
    if (selected.length === 0 && !notes.trim()) {
      // The server refuses this too — re-running an identical prompt is exactly
      // what this loop exists to avoid.
      setError('Pick at least one problem, or describe what was wrong.')
      return
    }
    onRefine(selected, notes.trim())
  }

  if (!open) {
    return (
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle>Not quite right?</CardTitle>
            <p className="mt-1.5 text-sm text-ink-muted">
              Tell it what to fix and it will rewrite. The current version is kept.
            </p>
          </div>
          <Button variant="secondary" onClick={() => setOpen(true)}>
            Refine it
          </Button>
        </div>
      </Card>
    )
  }

  return (
    <Card>
      <div className="flex items-center justify-between gap-3">
        <CardTitle>What was wrong with it?</CardTitle>
        <Button variant="ghost" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>

      <ul className="mt-4 flex flex-wrap gap-2">
        {PROBLEMS.map((problem) => {
          const active = selected.includes(problem)
          return (
            <li key={problem}>
              <button
                type="button"
                aria-pressed={active}
                disabled={busy}
                onClick={() => toggle(problem)}
                className={`min-h-9 rounded-full px-3 py-1.5 text-xs font-medium ring-1 transition-colors ${
                  active
                    ? 'bg-brand text-white ring-brand'
                    : 'bg-raised text-ink-muted ring-edge hover:text-ink hover:ring-edge-strong'
                }`}
              >
                {problem}
              </button>
            </li>
          )
        })}
      </ul>

      <label className="mt-4 block">
        <span className="mb-1.5 block text-sm font-medium text-ink">
          Anything else? <span className="text-ink-faint">Optional</span>
        </span>
        <Textarea
          rows={3}
          value={notes}
          disabled={busy}
          placeholder="Lead with the platform work rather than the reporting tools…"
          onChange={(e) => setNotes(e.target.value)}
        />
      </label>

      <ErrorNote>{error}</ErrorNote>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button onClick={handleSubmit} loading={busy}>
          Rewrite it
        </Button>
        <p className="text-xs text-ink-faint">
          Takes another 10 to 20 seconds. Your existing version stays available.
        </p>
      </div>
    </Card>
  )
}
