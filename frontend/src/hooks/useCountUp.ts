import { useEffect, useState } from 'react'

/**
 * Animates 0 → target once `run` becomes true.
 *
 * Eases out, so the number decelerates into its final value rather than
 * stopping dead. When `run` is false it reports the target immediately, which
 * is what reduced-motion callers want.
 */
export function useCountUp(target: number, run: boolean, steps = 34): number {
  const [value, setValue] = useState(run ? 0 : target)

  useEffect(() => {
    if (!run) {
      setValue(target)
      return
    }

    let frame = 0
    const timer = setInterval(() => {
      frame += 1
      const progress = 1 - (1 - frame / steps) ** 3
      setValue(Math.round(target * progress))
      if (frame >= steps) clearInterval(timer)
    }, 26)

    return () => clearInterval(timer)
  }, [target, run, steps])

  return value
}
