import { useCountUp } from '../hooks/useCountUp'
import { usePrefersReducedMotion } from './Reveal'

const RADIUS = 46
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

/* Only white, grey and red exist in this palette, so the score reads as
   strong / middling / weak rather than the usual green-amber-red. */
function tone(score: number): { text: string; stroke: string } {
  if (score >= 75) return { text: 'text-ink', stroke: 'stroke-ink' }
  if (score >= 50) return { text: 'text-ink-muted', stroke: 'stroke-ink-muted' }
  return { text: 'text-brand', stroke: 'stroke-brand' }
}

export function ScoreDial({ score }: { score: number | null }) {
  const reduced = usePrefersReducedMotion()
  const target = score === null ? 0 : Math.round(score)
  const value = useCountUp(target, !reduced)

  if (score === null) {
    return <p className="text-sm text-ink-muted">No match score returned.</p>
  }

  const { text, stroke } = tone(target)
  // The arc is drawn by hiding part of the stroke, so the dash offset is what
  // animates rather than any layout property.
  const offset = CIRCUMFERENCE - (value / 100) * CIRCUMFERENCE

  return (
    // Stacks until lg: inside a half-width card the dial and this much text do
    // not fit side by side at smaller breakpoints.
    <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:gap-5">
      <div className="relative shrink-0">
        <svg
          viewBox="0 0 110 110"
          className="size-28 -rotate-90"
          role="img"
          aria-label={`Match score ${target} out of 100`}
        >
          <circle
            cx="55"
            cy="55"
            r={RADIUS}
            fill="none"
            strokeWidth="7"
            className="stroke-raised"
          />
          <circle
            cx="55"
            cy="55"
            r={RADIUS}
            fill="none"
            strokeWidth="7"
            strokeLinecap="round"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={offset}
            className={`${stroke} transition-[stroke-dashoffset] duration-200 ease-out`}
          />
        </svg>

        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={`text-3xl leading-none font-semibold tabular-nums ${text}`}>
            {value}
          </span>
          <span className="mt-0.5 text-[10px] text-ink-faint">out of 100</span>
        </div>
      </div>

      <p className="text-xs leading-relaxed text-ink-muted">
        How well your experience fit this role <em className="text-ink">before</em>{' '}
        tailoring. Rewriting sharpens how it reads — it does not change what you
        have done, so this number is the honest one.
      </p>
    </div>
  )
}
