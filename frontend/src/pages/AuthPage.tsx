import { type ReactNode, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { Credit, Wordmark } from '../components/Layout'
import { Button, Card, ErrorNote, Field, Input } from '../components/ui'
import { ApiError } from '../lib/api'

const MIN_PASSWORD_LENGTH = 8

const INLINE_LINK = 'font-medium underline underline-offset-2 hover:no-underline'

/**
 * Turn a failed request into something a person can act on.
 *
 * The 401 wording is deliberately ambiguous about *which* detail was wrong.
 * Saying "no such account" would turn this form into a way to check whether a
 * given person has signed up — and on a resume-tailoring site, that discloses
 * that someone is job hunting. The backend returns an identical 401 for an
 * unknown email and a wrong password for the same reason, so the UI must not
 * undo it.
 */
function authErrorMessage(err: unknown): ReactNode {
  if (!(err instanceof ApiError)) {
    return err instanceof Error
      ? err.message
      : 'Something went wrong. Please try again.'
  }

  switch (err.status) {
    case 401:
      return (
        <>
          Incorrect email or password. Check both, or{' '}
          <Link to="/signup" className={INLINE_LINK}>
            create an account
          </Link>{' '}
          if you don't have one yet.
        </>
      )

    case 409:
      return (
        <>
          An account with that email already exists.{' '}
          <Link to="/login" className={INLINE_LINK}>
            Sign in instead
          </Link>
          .
        </>
      )

    case 403:
      return 'That account has been disabled. Please get in touch if you think this is a mistake.'

    case 422:
      // Pydantic's field-level messages, already flattened by the API client.
      return err.message

    case 503:
      return 'Sign-ups are briefly unavailable because confirmation emails cannot be sent right now. Please try again in a few minutes.'

    default:
      return err.message
  }
}

export function AuthPage({ mode }: { mode: 'login' | 'signup' }) {
  const isSignup = mode === 'signup'
  const { user, login, signup } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [error, setError] = useState<ReactNode>(null)
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to="/" replace />

  const redirectTo = (location.state as { from?: string } | null)?.from ?? '/'

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)

    if (isSignup && password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`)
      return
    }

    setBusy(true)
    try {
      if (isSignup) await signup(email, password, fullName)
      else await login(email, password)
      navigate(redirectTo, { replace: true })
    } catch (err) {
      setError(authErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen flex-col px-4 py-10">
      <div className="mx-auto flex w-full max-w-sm grow flex-col justify-center">
        <div className="mb-7 text-center">
          <Wordmark className="text-2xl" />
          <p className="mt-2 text-sm text-ink-muted">
            {isSignup
              ? 'Rewrite your resume for the job you actually want.'
              : 'Welcome back.'}
          </p>
        </div>

        <Card>
          <form onSubmit={handleSubmit} className="space-y-4">
            {isSignup && (
              <Field label="Full name" hint="Optional">
                <Input
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  autoComplete="name"
                />
              </Field>
            )}

            <Field label="Email">
              <Input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                inputMode="email"
                autoCapitalize="none"
              />
            </Field>

            <Field
              label="Password"
              hint={isSignup ? `At least ${MIN_PASSWORD_LENGTH} characters` : undefined}
            >
              <Input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={isSignup ? 'new-password' : 'current-password'}
              />
            </Field>

            <ErrorNote>{error}</ErrorNote>

            <Button type="submit" loading={busy} className="w-full">
              {isSignup ? 'Create account' : 'Sign in'}
            </Button>
          </form>
        </Card>

        <p className="mt-5 text-center text-sm text-ink-muted">
          {isSignup ? 'Already have an account? ' : "Don't have an account? "}
          <Link
            to={isSignup ? '/login' : '/signup'}
            className="font-medium text-brand hover:underline"
          >
            {isSignup ? 'Sign in' : 'Sign up'}
          </Link>
        </p>
      </div>

      {/* Layout's footer only wraps authenticated pages, so the credit is
          repeated here — this is the first screen any visitor sees. */}
      <Credit className="mt-10 text-center text-xs text-ink-faint" />
    </div>
  )
}
