import { describe, expect, it } from 'vitest'

import { ACTIVITY_EVENTS, IDLE_TIMEOUT_MS, isIdle } from './idle'

describe('idle detection', () => {
  const now = 1_700_000_000_000

  it('is not idle immediately after activity', () => {
    expect(isIdle(now, now)).toBe(false)
  })

  it('is not idle one millisecond before the limit', () => {
    expect(isIdle(now - IDLE_TIMEOUT_MS + 1, now)).toBe(false)
  })

  it('is idle once past the limit', () => {
    expect(isIdle(now - IDLE_TIMEOUT_MS - 1, now)).toBe(true)
  })

  it('is idle after a day away, which is the case that prompted this', () => {
    expect(isIdle(now - 24 * 60 * 60 * 1000, now)).toBe(true)
  })

  it('treats a clock that jumped backwards as active rather than expired', () => {
    // An NTP correction can put `now` behind the recorded activity. Reading that
    // as a huge idle gap would sign people out at random.
    expect(isIdle(now + 60_000, now)).toBe(false)
  })

  it('matches the backend timeout of two hours', () => {
    // If these drift the server still wins, but the message shown would be
    // wrong. Pinned so a change on one side is a visible failure on the other.
    expect(IDLE_TIMEOUT_MS).toBe(120 * 60 * 1000)
  })

  it('ignores mouse movement, so a nudged desk cannot hold a session open', () => {
    expect(ACTIVITY_EVENTS).not.toContain('mousemove')
  })
})
