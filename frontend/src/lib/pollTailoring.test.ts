import { describe, expect, it, vi } from 'vitest'

import { PollTimeout, isFinished, pollUntilFinished } from './pollTailoring'
import type { TailoringDetail } from './types'

function row(status: TailoringDetail['status']): TailoringDetail {
  return { id: 'a-run', status } as TailoringDetail
}

/** Runs the loop with no real waiting, so the tests are instant. */
const noSleep = () => Promise.resolve()

describe('knowing when a run has settled', () => {
  it('treats succeeded and failed as finished', () => {
    expect(isFinished('succeeded')).toBe(true)
    expect(isFinished('failed')).toBe(true)
  })

  it('treats pending and running as still going', () => {
    expect(isFinished('pending')).toBe(false)
    expect(isFinished('running')).toBe(false)
  })
})

describe('polling a run', () => {
  it('keeps asking until the run succeeds', async () => {
    const fetchOne = vi
      .fn()
      .mockResolvedValueOnce(row('pending'))
      .mockResolvedValueOnce(row('running'))
      .mockResolvedValueOnce(row('succeeded'))

    const result = await pollUntilFinished('a-run', { fetchOne, sleep: noSleep })

    expect(result?.status).toBe('succeeded')
    expect(fetchOne).toHaveBeenCalledTimes(3)
  })

  it('resolves on failure rather than throwing', async () => {
    // "failed" is a result the page renders, with the reason. Rejecting would
    // make the caller handle it as an exception and lose that reason.
    const fetchOne = vi.fn().mockResolvedValue(row('failed'))

    const result = await pollUntilFinished('a-run', { fetchOne, sleep: noSleep })

    expect(result?.status).toBe('failed')
  })

  it('stops immediately if the run is already finished', async () => {
    const fetchOne = vi.fn().mockResolvedValue(row('succeeded'))

    await pollUntilFinished('a-run', { fetchOne, sleep: noSleep })

    expect(fetchOne).toHaveBeenCalledTimes(1)
  })

  it('reports every reading, so the UI can follow along', async () => {
    const fetchOne = vi
      .fn()
      .mockResolvedValueOnce(row('pending'))
      .mockResolvedValueOnce(row('succeeded'))
    const seen: string[] = []

    await pollUntilFinished('a-run', {
      fetchOne,
      sleep: noSleep,
      onUpdate: (r) => seen.push(r.status),
    })

    expect(seen).toEqual(['pending', 'succeeded'])
  })

  it('gives up once past the timeout', async () => {
    const fetchOne = vi.fn().mockResolvedValue(row('running'))
    let clock = 0
    // Jump past the ceiling on the second reading.
    const now = () => (clock += 60_000)

    await expect(
      pollUntilFinished('a-run', {
        fetchOne,
        sleep: noSleep,
        now,
        timeoutMs: 1000,
      }),
    ).rejects.toBeInstanceOf(PollTimeout)
  })

  it('abandons quietly when the caller is gone', async () => {
    // The component unmounted. Continuing would request a row nobody is
    // looking at, then write to state that no longer exists.
    const fetchOne = vi.fn().mockResolvedValue(row('running'))

    const result = await pollUntilFinished('a-run', {
      fetchOne,
      sleep: noSleep,
      isActive: () => false,
    })

    expect(result).toBeNull()
    expect(fetchOne).not.toHaveBeenCalled()
  })

  it('stops between readings once the caller goes away', async () => {
    const fetchOne = vi.fn().mockResolvedValue(row('running'))
    let alive = true

    const result = await pollUntilFinished('a-run', {
      fetchOne,
      sleep: () => {
        alive = false
        return Promise.resolve()
      },
      isActive: () => alive,
    })

    expect(result).toBeNull()
    expect(fetchOne).toHaveBeenCalledTimes(1)
  })

  it('lets a request failure surface, rather than looping on a dead API', async () => {
    const fetchOne = vi.fn().mockRejectedValue(new Error('Could not reach the server.'))

    await expect(
      pollUntilFinished('a-run', { fetchOne, sleep: noSleep }),
    ).rejects.toThrow('Could not reach the server.')
  })

  it('waits between readings by the configured interval', async () => {
    const fetchOne = vi
      .fn()
      .mockResolvedValueOnce(row('running'))
      .mockResolvedValueOnce(row('succeeded'))
    const sleep = vi.fn().mockResolvedValue(undefined)

    await pollUntilFinished('a-run', { fetchOne, sleep, intervalMs: 2000 })

    expect(sleep).toHaveBeenCalledWith(2000)
  })
})
