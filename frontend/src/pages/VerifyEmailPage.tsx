import { useState } from 'react'
import { Navigate } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { Credit, Wordmark } from '../components/Layout'
import { Button, Card, ErrorNote } from '../components/ui'
import { ApiError, api } from '../lib/api'

/**
 * Holding page for a signed-in but unconfirmed account.
 *
 * Verification is mandatory, so this is a dead end by design — the only ways
 * out are clicking the emailed link or signing out.
 */
export function VerifyEmailPage() {
  const { user, refresh, logout } = useAuth()
  const [status, setStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [checking, setChecking] = useState(false)

  if (user?.is_verified) return <Navigate to="/" replace />

  async function handleResend() {
    setError(null)
    setStatus(null)
    setSending(true)
    try {
      const res = await api.auth.resendVerification()
      setStatus(res.detail)
    } catch (err) {
      // 429 is the cooldown, which is expected rather than broken — say so
      // plainly instead of showing it as a failure.
      setError(
        err instanceof ApiError && err.status === 429
          ? err.message
          : err instanceof Error
            ? err.message
            : 'Could not resend the email.',
      )
    } finally {
      setSending(false)
    }
  }

  async function handleCheck() {
    setError(null)
    setChecking(true)
    try {
      await refresh()
    } catch {
      setError('Could not check your status. Please try again.')
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="flex min-h-screen flex-col px-4 py-10">
      <div className="mx-auto flex w-full max-w-md grow flex-col justify-center">
        <div className="mb-7 text-center">
          <Wordmark className="text-2xl" />
        </div>

        <Card>
          <h1 className="text-lg font-semibold text-ink">Confirm your email</h1>
          <p className="mt-2 text-sm text-ink-muted">
            We sent a link to{' '}
            <span className="font-medium text-ink">{user?.email}</span>. Open it to
            finish setting up your account.
          </p>
          <p className="mt-2 text-sm text-ink-muted">
            The link expires in 24 hours. Check your spam folder if it has not
            arrived.
          </p>

          <div className="mt-5 flex flex-col gap-3 sm:flex-row">
            <Button onClick={handleCheck} loading={checking}>
              I've confirmed it
            </Button>
            <Button variant="secondary" onClick={handleResend} loading={sending}>
              Resend email
            </Button>
          </div>

          {status && (
            <p className="mt-3 rounded-lg bg-raised px-3 py-2.5 text-sm text-ink-muted ring-1 ring-edge">
              {status}
            </p>
          )}
          <ErrorNote>{error}</ErrorNote>

          <button
            onClick={logout}
            className="mt-5 min-h-11 text-sm text-ink-faint hover:text-ink"
          >
            Sign out
          </button>
        </Card>
      </div>

      <Credit className="mt-10 text-center text-xs text-ink-faint" />
    </div>
  )
}
