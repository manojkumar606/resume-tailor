import { useEffect, useState } from 'react'

import { usePrefersReducedMotion } from './Reveal'

/**
 * Fills the 10-20 seconds a tailoring run takes.
 *
 * There is no honest percentage to show: it is a single model call, so the
 * server has no intermediate milestones to report. Rather than invent a fake
 * progress bar, this shows two things that are true — an elapsed counter, and a
 * description of what the model was actually asked to produce (a rewrite, and a
 * list of gaps). The bar is an indeterminate shimmer, which signals "working"
 * without claiming to know how far along it is.
 *
 * Left as a bare spinner, this wait is the worst moment in the app: long enough
 * to look broken, with nothing to confirm anything is happening.
 */
const STAGES = [
  { at: 0, label: 'Reading the posting and your resume…' },
  { at: 4, label: 'Rewriting your experience for this role…' },
  { at: 9, label: 'Working out what the posting asks for that you lack…' },
  { at: 15, label: 'Nearly there — long postings take a little longer…' },
]

export function TailoringProgress() {
  const reduced = usePrefersReducedMotion()
  const [seconds, setSeconds] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => clearInterval(timer)
  }, [])

  // The last stage whose threshold has passed.
  const stage = STAGES.reduce((current, candidate) =>
    seconds >= candidate.at ? candidate : current,
  )

  return (
    <div
      role="status"
      aria-live="polite"
      className="mt-4 rounded-xl bg-raised p-4 ring-1 ring-edge"
    >
      <div className="flex items-center gap-3">
        <span
          aria-hidden
          className="size-4 shrink-0 animate-spin rounded-full border-2 border-brand border-t-transparent"
        />
        <p className="min-w-0 flex-1 text-sm text-ink">{stage.label}</p>
        <span className="shrink-0 text-xs tabular-nums text-ink-faint">{seconds}s</span>
      </div>

      <div className="mt-3.5 h-1 overflow-hidden rounded-full bg-edge">
        {reduced ? (
          <div className="h-full w-1/3 rounded-full bg-brand" />
        ) : (
          <div className="shimmer h-full w-1/3 rounded-full bg-brand" />
        )}
      </div>

      <p className="mt-3 text-xs text-ink-faint">
        Usually 10 to 20 seconds. Keep this page open.
      </p>
    </div>
  )
}
