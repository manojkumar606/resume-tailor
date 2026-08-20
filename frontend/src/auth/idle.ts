/**
 * Client-side idle detection.
 *
 * The server is the authority — it revokes an idle session regardless of what
 * the browser does. This exists so the user is told, rather than discovering it
 * when their next click fails: the tab returns to the sign-in page with a
 * reason, instead of sitting there looking signed in.
 *
 * Matched to the backend's SESSION_IDLE_TIMEOUT_MINUTES. If the two drift the
 * server still wins, so the failure mode is a confusing message rather than a
 * security hole.
 */
export const IDLE_TIMEOUT_MS = 120 * 60 * 1000

/**
 * Checked on a timer rather than by resetting a setTimeout on every event.
 * Comparing timestamps is both cheaper under a flood of mousemove events and
 * correct across a laptop suspend, where a pending timer simply does not fire
 * for the duration of the sleep.
 */
export const IDLE_CHECK_INTERVAL_MS = 30 * 1000

/**
 * Deliberately excludes mousemove: a nudged desk or a cat on the keyboard
 * should not keep a session alive for hours. These all require intent.
 */
export const ACTIVITY_EVENTS = [
  'mousedown',
  'keydown',
  'touchstart',
  'scroll',
  'focus',
] as const

/**
 * Why the session ended, so the sign-in page can explain itself.
 *
 * `idle`    — this browser noticed the inactivity first.
 * `expired` — the server refused the token: revoked here, revoked from another
 *             device, or past its absolute ceiling.
 * `manual`  — the user pressed sign out, and needs no explanation.
 */
export type SignOutReason = 'idle' | 'expired' | 'manual' | null

export function isIdle(lastActivity: number, now: number): boolean {
  // A clock that has moved backwards (NTP correction, timezone change) must not
  // read as "active forever", nor as instantly idle.
  const elapsed = now - lastActivity
  return elapsed > IDLE_TIMEOUT_MS
}
