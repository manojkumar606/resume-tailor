import { useEffect, useRef, useState, type ReactNode } from 'react'

/** True when the OS asks for less motion, so effects can opt out entirely. */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () =>
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  )

  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReduced(query.matches)
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])

  return reduced
}

/**
 * Fades and lifts its children in when they first scroll into view.
 *
 * IntersectionObserver rather than a scroll listener: the browser does the work
 * off the main thread, so a long page does not jank while scrolling. It also
 * unobserves after firing — these are one-shot entrances, and re-animating
 * on every pass is what makes scroll effects feel cheap.
 */
export function Reveal({
  children,
  delay,
  className = '',
  as: Tag = 'div',
}: {
  children: ReactNode
  /** 1-4, staggering siblings so a group reads as one movement. */
  delay?: 1 | 2 | 3 | 4
  className?: string
  as?: 'div' | 'section' | 'li' | 'p' | 'h2'
}) {
  const ref = useRef<HTMLElement | null>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const node = ref.current
    if (!node) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true)
          observer.unobserve(entry.target)
        }
      },
      // Fires slightly before the element is fully on screen, so the movement
      // has finished by the time it is properly in view.
      { threshold: 0.15, rootMargin: '0px 0px -40px 0px' },
    )

    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  return (
    <Tag
      ref={ref as never}
      className={`reveal ${delay ? `reveal-${delay}` : ''} ${
        visible ? 'is-visible' : ''
      } ${className}`}
    >
      {children}
    </Tag>
  )
}
