import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { Credit, Wordmark } from '../components/Layout'
import { Button, Card, ErrorNote, Spinner } from '../components/ui'

/**
 * Landing page for the emailed link (/verify?token=…).
 *
 * Public on purpose: the link is opened from a mail client, which may be on a
 * different device from the one that signed up.
 */
export function VerifyTokenPage() {
  const [params] = useSearchParams()
  const token = params.get('token')
  const { verify } = useAuth()

  const [state, setState] = useState<'working' | 'done' | 'failed'>('working')
  const [error, setError] = useState<string | null>(null)

  // Tokens are single-use, so a second call would fail. StrictMode
  // double-invokes effects in development, and without this guard the first
  // call succeeds and the second reports "already used".
  const attempted = useRef(false)

  useEffect(() => {
    if (!token || attempted.current) return
    attempted.current = true

    verify(token)
      .then(() => setState('done'))
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Verification failed.')
        setState('failed')
      })
  }, [token, verify])

  if (!token) return <Navigate to="/login" replace />

  return (
    <div className="flex min-h-screen flex-col px-4 py-10">
      <div className="mx-auto flex w-full max-w-md grow flex-col justify-center">
        <div className="mb-7 text-center">
          <Wordmark className="text-2xl" />
        </div>

        <Card>
          {state === 'working' && <Spinner label="Confirming your email…" />}

          {state === 'done' && (
            <>
              <h1 className="text-lg font-semibold text-ink">Email confirmed</h1>
              <p className="mt-2 text-sm text-ink-muted">
                Your account is ready. Upload a resume to get started.
              </p>
              <Link to="/" className="mt-5 inline-block">
                <Button>Go to dashboard</Button>
              </Link>
            </>
          )}

          {state === 'failed' && (
            <>
              <h1 className="text-lg font-semibold text-ink">
                That link didn't work
              </h1>
              <ErrorNote>{error}</ErrorNote>
              <p className="mt-3 text-sm text-ink-muted">
                Links expire after 24 hours and can only be used once. Sign in to
                request a new one.
              </p>
              <Link to="/login" className="mt-5 inline-block">
                <Button variant="secondary">Sign in</Button>
              </Link>
            </>
          )}
        </Card>
      </div>

      <Credit className="mt-10 text-center text-xs text-ink-faint" />
    </div>
  )
}
