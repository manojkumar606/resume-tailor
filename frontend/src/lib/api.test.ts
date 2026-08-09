import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, api, setUnauthorizedHandler, tokenStore } from './api'

/**
 * These exist because the same bug was reported twice: a failed sign-in telling
 * the user their session had expired. The handling is a few lines and looks
 * obviously correct by inspection, which is exactly why it needs a test rather
 * than another read-through.
 */

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  localStorage.clear()
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthorizedHandler(null)
})

describe('a 401 from signing in', () => {
  it('reports the wrong-credentials message, not an expired session', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(401, { detail: 'Incorrect email or password' }),
    )

    await expect(api.auth.login('nobody@example.com', 'guess')).rejects.toThrow(
      'Incorrect email or password',
    )
  })

  it('does not wipe a stored token', async () => {
    // Somebody signing in again while an old token is still in storage must not
    // have that treated as the cause of the failure.
    tokenStore.set('stale-token')
    fetchMock.mockResolvedValue(
      jsonResponse(401, { detail: 'Incorrect email or password' }),
    )

    await expect(api.auth.login('a@example.com', 'wrong')).rejects.toBeInstanceOf(
      ApiError,
    )
    expect(tokenStore.get()).toBe('stale-token')
  })

  it('does not fire the logout handler', async () => {
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    tokenStore.set('stale-token')
    fetchMock.mockResolvedValue(
      jsonResponse(401, { detail: 'Incorrect email or password' }),
    )

    await expect(api.auth.login('a@example.com', 'wrong')).rejects.toBeInstanceOf(
      ApiError,
    )
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('sends no Authorization header at all', async () => {
    tokenStore.set('stale-token')
    fetchMock.mockResolvedValue(jsonResponse(202, { status: 'code_sent' }))

    await api.auth.login('a@example.com', 'pw')

    const headers = new Headers(fetchMock.mock.calls[0][1].headers)
    // A sign-in attempt carrying a stale session is what made "expired" a
    // plausible-looking diagnosis in the first place.
    expect(headers.has('Authorization')).toBe(false)
  })
})

describe('a 401 from a genuine session', () => {
  it('reports an expired session and clears the token', async () => {
    tokenStore.set('expired-token')
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    fetchMock.mockResolvedValue(jsonResponse(401, { detail: 'Not authenticated' }))

    await expect(api.resumes.list()).rejects.toThrow('session expired')
    expect(tokenStore.get()).toBeNull()
    expect(onUnauthorized).toHaveBeenCalledOnce()
  })

  it('does not claim expiry when no token was ever sent', async () => {
    fetchMock.mockResolvedValue(jsonResponse(401, { detail: 'Not authenticated' }))

    await expect(api.resumes.list()).rejects.toThrow('Not authenticated')
  })
})

describe('error message extraction', () => {
  it('flattens FastAPI 422 validation arrays', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(422, {
        detail: [
          { loc: ['body', 'password'], msg: 'String should have at least 8 characters' },
        ],
      }),
    )

    // Rendering the raw array would show "[object Object]" to the user.
    await expect(api.auth.signup('a@example.com', 'short')).rejects.toThrow(
      'password: String should have at least 8 characters',
    )
  })

  it('surfaces a plain string detail unchanged', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(409, { detail: 'An account with that email already exists' }),
    )

    await expect(api.auth.signup('a@example.com', 'password123')).rejects.toThrow(
      'An account with that email already exists',
    )
  })

  it('turns an unreachable server into a readable error', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

    await expect(api.auth.login('a@example.com', 'pw')).rejects.toThrow(
      'Could not reach the server',
    )
  })
})

describe('the verification gate', () => {
  it('ends the session so signing in again can re-confirm the address', async () => {
    tokenStore.set('token-for-unverified-user')
    fetchMock.mockResolvedValue(
      jsonResponse(403, {
        detail: 'Please confirm your email address before using the app.',
      }),
    )

    await expect(api.jobs.list()).rejects.toThrow('sign in again')
    expect(tokenStore.get()).toBeNull()
  })

  it('leaves other 403s alone', async () => {
    tokenStore.set('good-token')
    fetchMock.mockResolvedValue(jsonResponse(403, { detail: 'Account is disabled' }))

    await expect(api.jobs.list()).rejects.toThrow('Account is disabled')
    expect(tokenStore.get()).toBe('good-token')
  })
})
