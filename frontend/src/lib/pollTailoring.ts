import type { TailoringDetail, UUID } from './types'

/**
 * Waiting for a background tailoring run to finish.
 *
 * The server no longer holds the connection open for the 10-20 seconds a run
 * takes; it answers at once with a `pending` row and the client asks again
 * until the row settles. Kept as a plain function with its fetcher injected so
 * it can be tested without a network or a component tree.
 */

export const POLL_INTERVAL_MS = 2000

/**
 * Generous on purpose. It is not the real timeout — the server fails a run that
 * has stalled, and polling will read that. This only stops the browser asking
 * forever if the API becomes unreachable mid-run.
 */
export const POLL_TIMEOUT_MS = 5 * 60 * 1000

export type TailoringStatus = TailoringDetail['status']

export function isFinished(status: TailoringStatus): boolean {
  return status === 'succeeded' || status === 'failed'
}

export class PollTimeout extends Error {
  constructor() {
    super('This is taking longer than expected. Refresh to see where it got to.')
    this.name = 'PollTimeout'
  }
}

interface PollOptions {
  fetchOne: (id: UUID) => Promise<TailoringDetail>
  /** Called with every reading, so the UI can show progress as it changes. */
  onUpdate?: (row: TailoringDetail) => void
  /** Returns false to abandon quietly — used when the component unmounts. */
  isActive?: () => boolean
  sleep?: (ms: number) => Promise<void>
  intervalMs?: number
  timeoutMs?: number
  now?: () => number
}

const defaultSleep = (ms: number) =>
  new Promise<void>((resolve) => setTimeout(resolve, ms))

/**
 * Resolves once the run reaches a terminal state.
 *
 * A failed run resolves rather than rejects: "failed" is an outcome the UI
 * renders, complete with the reason, not an exception for it to catch.
 */
export async function pollUntilFinished(
  id: UUID,
  {
    fetchOne,
    onUpdate,
    isActive = () => true,
    sleep = defaultSleep,
    intervalMs = POLL_INTERVAL_MS,
    timeoutMs = POLL_TIMEOUT_MS,
    now = Date.now,
  }: PollOptions,
): Promise<TailoringDetail | null> {
  const startedAt = now()

  for (;;) {
    if (!isActive()) return null

    const row = await fetchOne(id)
    onUpdate?.(row)
    if (isFinished(row.status)) return row

    if (now() - startedAt > timeoutMs) throw new PollTimeout()

    await sleep(intervalMs)
  }
}
