import { useEffect, useRef, useState } from 'react'

import { usePrefersReducedMotion } from './Reveal'

/**
 * A looping, self-contained demonstration of what the product does.
 *
 * The content is fixed rather than fetched: this runs on the public page, before
 * anyone has an account, and a live model call there would be slow, cost money,
 * and could fail in front of a first-time visitor.
 *
 * The second panel deliberately shows an unflattering score alongside real gaps.
 * The product's whole stance is that it will not invent experience, so a demo
 * that showed a number leaping upwards after tailoring would be advertising the
 * opposite of what the tool does.
 */

const JOB_KEYWORDS = ['FastAPI', 'REST API design', 'PostgreSQL', 'Docker', 'AWS']

const BEFORE = 'Built Python services that process candidate assessment data.'
const AFTER =
  'Designed and built Python backend services and REST APIs with FastAPI to process candidate assessment data.'

/** Highlighted once typing finishes — the phrases drawn from the posting. */
const INJECTED = ['REST APIs', 'FastAPI', 'backend services']

const HONEST_SCORE = 68
const GAPS = ['Docker', 'Kubernetes', 'AWS', 'CI/CD pipelines']

const TYPE_MS = 22
const HOLD_MS = 2600

type Phase = 'typing' | 'highlighting' | 'holding'

/** Splits text so the phrases taken from the posting can be tinted. */
function withHighlights(text: string, active: boolean) {
  if (!active) return text

  const pattern = new RegExp(`(${INJECTED.join('|')})`, 'g')
  return text.split(pattern).map((part, index) =>
    INJECTED.includes(part) ? (
      <span key={index} className="font-medium text-brand">
        {part}
      </span>
    ) : (
      part
    ),
  )
}

function useCountUp(target: number, run: boolean) {
  const [value, setValue] = useState(run ? 0 : target)

  useEffect(() => {
    if (!run) {
      setValue(target)
      return
    }
    let frame = 0
    const steps = 34
    const timer = setInterval(() => {
      frame += 1
      // Ease-out so it decelerates into the final number instead of stopping dead.
      const progress = 1 - (1 - frame / steps) ** 3
      setValue(Math.round(target * progress))
      if (frame >= steps) clearInterval(timer)
    }, 26)
    return () => clearInterval(timer)
  }, [target, run])

  return value
}

export function RewriteDemo() {
  const reduced = usePrefersReducedMotion()

  const [typed, setTyped] = useState(reduced ? AFTER : '')
  const [phase, setPhase] = useState<Phase>(reduced ? 'holding' : 'typing')
  const [started, setStarted] = useState(reduced)
  const containerRef = useRef<HTMLDivElement | null>(null)

  const score = useCountUp(HONEST_SCORE, started && !reduced)

  // Only run while on screen. A loop ticking away in a scrolled-past section
  // burns battery for nothing.
  useEffect(() => {
    const node = containerRef.current
    if (!node || reduced) return

    const observer = new IntersectionObserver(
      ([entry]) => setStarted(entry.isIntersecting),
      { threshold: 0.3 },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [reduced])

  useEffect(() => {
    if (reduced || !started) return

    if (phase === 'typing') {
      if (typed.length >= AFTER.length) {
        setPhase('highlighting')
        return
      }
      const timer = setTimeout(
        () => setTyped(AFTER.slice(0, typed.length + 1)),
        TYPE_MS,
      )
      return () => clearTimeout(timer)
    }

    if (phase === 'highlighting') {
      const timer = setTimeout(() => setPhase('holding'), 700)
      return () => clearTimeout(timer)
    }

    const timer = setTimeout(() => {
      setTyped('')
      setPhase('typing')
    }, HOLD_MS)
    return () => clearTimeout(timer)
  }, [phase, typed, started, reduced])

  const highlighted = phase !== 'typing'

  return (
    <div ref={containerRef} className="grid gap-4 lg:grid-cols-5">
      {/* The rewrite */}
      <div className="rounded-2xl bg-panel p-5 ring-1 ring-edge lg:col-span-3">
        <p className="text-xs font-semibold tracking-wide text-ink-faint uppercase">
          The posting asks for
        </p>
        <ul className="mt-2.5 flex flex-wrap gap-1.5">
          {JOB_KEYWORDS.map((keyword) => (
            <li
              key={keyword}
              className="rounded-full bg-raised px-2.5 py-1 text-xs text-ink-muted ring-1 ring-edge"
            >
              {keyword}
            </li>
          ))}
        </ul>

        <div className="mt-6 space-y-4">
          <div>
            <p className="text-xs text-ink-faint">Your bullet</p>
            <p className="mt-1.5 text-sm leading-relaxed text-ink-muted line-through decoration-ink-faint/60">
              {BEFORE}
            </p>
          </div>

          <div>
            <p className="text-xs text-ink-faint">Rewritten for this role</p>
            {/* min-height reserves the final two lines so the card does not
                resize as text arrives, which would shove the page around. */}
            <p className="mt-1.5 min-h-[4.5rem] text-sm leading-relaxed text-ink">
              {withHighlights(typed, highlighted)}
              {!reduced && phase === 'typing' && (
                <span className="caret ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 bg-brand" />
              )}
            </p>
          </div>
        </div>
      </div>

      {/* The honest part */}
      <div className="rounded-2xl bg-panel p-5 ring-1 ring-edge lg:col-span-2">
        <p className="text-xs font-semibold tracking-wide text-ink-faint uppercase">
          Your honest fit
        </p>

        <p className="mt-3 text-5xl leading-none font-semibold tabular-nums text-ink">
          {score}
          <span className="text-lg font-normal text-ink-faint">/100</span>
        </p>

        <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-raised">
          <div
            className="h-full rounded-full bg-ink transition-[width] duration-700 ease-out"
            style={{ width: `${score}%` }}
          />
        </div>

        <p className="mt-5 text-xs text-ink-faint">
          Requirements you genuinely do not meet
        </p>
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {GAPS.map((gap) => (
            <li
              key={gap}
              className="rounded-full bg-brand-wash px-2.5 py-1 text-xs font-medium text-brand ring-1 ring-brand/30"
            >
              {gap}
            </li>
          ))}
        </ul>

        <p className="mt-4 text-xs leading-relaxed text-ink-muted">
          Not invented, not glossed over. These are what the screening call will
          probe.
        </p>
      </div>
    </div>
  )
}
