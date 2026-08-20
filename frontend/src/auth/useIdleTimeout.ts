import { useEffect, useRef } from 'react'

import {
  ACTIVITY_EVENTS,
  IDLE_CHECK_INTERVAL_MS,
  IDLE_TIMEOUT_MS,
  isIdle,
} from './idle'

/**
 * Calls `onIdle` once the user has done nothing for the timeout.
 *
 * `onIdle` is held in a ref so a caller passing an inline arrow function does
 * not tear down and rebuild every listener on each render.
 */
export function useIdleTimeout(onIdle: () => void, enabled: boolean) {
  const onIdleRef = useRef(onIdle)
  onIdleRef.current = onIdle

  useEffect(() => {
    if (!enabled) return

    let lastActivity = Date.now()
    let fired = false

    const markActive = () => {
      lastActivity = Date.now()
    }

    // Coming back to a tab is itself activity, but only if the session survived
    // the time away — otherwise returning to a day-old tab would reset the
    // clock and hide the timeout entirely.
    const onVisibility = () => {
      if (document.visibilityState !== 'visible') return
      if (isIdle(lastActivity, Date.now())) {
        check()
      } else {
        markActive()
      }
    }

    function check() {
      if (fired || !isIdle(lastActivity, Date.now())) return
      fired = true
      onIdleRef.current()
    }

    for (const event of ACTIVITY_EVENTS) {
      window.addEventListener(event, markActive, { passive: true })
    }
    document.addEventListener('visibilitychange', onVisibility)
    const timer = window.setInterval(check, IDLE_CHECK_INTERVAL_MS)

    return () => {
      for (const event of ACTIVITY_EVENTS) {
        window.removeEventListener(event, markActive)
      }
      document.removeEventListener('visibilitychange', onVisibility)
      window.clearInterval(timer)
    }
  }, [enabled])
}

export { IDLE_TIMEOUT_MS }
