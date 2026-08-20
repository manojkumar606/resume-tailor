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


describe('signing out', () => {
  it('sends the token, because the token identifies the session to revoke', async () => {
    tokenStore.set('a-live-token')
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))

    await api.auth.logout()

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toContain('/auth/logout')
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer a-live-token')
  })

  // '/auth/logout' and '/auth/login' share a prefix up to "/auth/log", and the
  // credential check is a startsWith. Were logout ever classified as a
  // credential endpoint it would be sent without a token, the server would 401,
  // and sign-out would silently stop revoking anything.
  it('is not treated as a credential endpoint', async () => {
    tokenStore.set('a-live-token')
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))

    await api.auth.logout()

    const init = fetchMock.mock.calls[0][1]
    expect(new Headers(init.headers).has('Authorization')).toBe(true)
  })

  it('surfaces a 401 as an expired session and clears the token', async () => {
    tokenStore.set('a-dead-token')
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    fetchMock.mockResolvedValue(jsonResponse(401, { detail: 'Not authenticated' }))

    await expect(api.auth.logout()).rejects.toThrow(ApiError)
    expect(tokenStore.get()).toBeNull()
    expect(onUnauthorized).toHaveBeenCalledOnce()
  })
})

describe('the device list', () => {
  it('asks for the sessions belonging to the caller', async () => {
    tokenStore.set('a-live-token')
    fetchMock.mockResolvedValue(jsonResponse(200, []))

    await api.account.sessions()

    expect(fetchMock.mock.calls[0][0]).toContain('/me/sessions')
  })

  it('revokes one session by id', async () => {
    tokenStore.set('a-live-token')
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))

    await api.account.revokeSession('11111111-2222-3333-4444-555555555555')

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toContain('/me/sessions/11111111-2222-3333-4444-555555555555')
    expect(init.method).toBe('DELETE')
  })

  it('revokes the others without naming them', async () => {
    tokenStore.set('a-live-token')
    fetchMock.mockResolvedValue(jsonResponse(200, { revoked: 2 }))

    const res = await api.account.revokeOtherSessions()

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/me\/sessions$/)
    expect(init.method).toBe('DELETE')
    expect(res.revoked).toBe(2)
  })

  it('returns undefined rather than exploding on a 204', async () => {
    tokenStore.set('a-live-token')
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))

    await expect(
      api.account.revokeSession('11111111-2222-3333-4444-555555555555'),
    ).resolves.toBeUndefined()
  })
})
