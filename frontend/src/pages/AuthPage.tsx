import { type ReactNode, useEffect, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { Credit, Wordmark } from '../components/Layout'
import { Button, Card, ErrorNote, Field, Input } from '../components/ui'
import { ApiError } from '../lib/api'

const MIN_PASSWORD_LENGTH = 8
const CODE_LENGTH = 6

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
    return err instanceof Error ? err.message : 'Something went wrong. Please try again.'
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
      return err.message
    case 503:
      return 'Sign-in is briefly unavailable because we cannot send codes right now. Please try again in a few minutes.'
    default:
      return err.message
  }
}

// ── Step two: the emailed code ───────────────────────────────────────────────

function CodeStep({
  email,
  expiresInMinutes,
  onBack,
}: {
  email: string
  expiresInMinutes: number
  onBack: () => void
}) {
  const { submitCode, resendCode } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [code, setCode] = useState('')
  const [error, setError] = useState<ReactNode>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [resending, setResending] = useState(false)
  // The server enforces a cooldown; mirroring it here means the resend button
  // is visibly unavailable rather than returning a 429 when pressed.
  const [cooldown, setCooldown] = useState(60)

  useEffect(() => {
    if (cooldown <= 0) return
    const timer = setInterval(() => setCooldown((n) => Math.max(0, n - 1)), 1000)
    return () => clearInterval(timer)
  }, [cooldown])

  const redirectTo = (location.state as { from?: string } | null)?.from ?? '/app'

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setNotice(null)
    setBusy(true)
    try {
      await submitCode(email, code)
      navigate(redirectTo, { replace: true })
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 400
          ? err.message
          : authErrorMessage(err),
      )
      setCode('')
    } finally {
      setBusy(false)
    }
  }

  async function handleResend() {
    setError(null)
    setNotice(null)
    setResending(true)
    try {
      setNotice(await resendCode(email))
      setCode('')
      setCooldown(60)
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setNotice(err.message)
        setCooldown(60)
      } else {
        setError(authErrorMessage(err))
      }
    } finally {
      setResending(false)
    }
  }

  return (
    <>
      <Card>
        <h1 className="text-lg font-semibold text-ink">Enter your code</h1>
        <p className="mt-2 text-sm text-ink-muted">
          We emailed a {CODE_LENGTH}-digit code to{' '}
          <span className="font-medium text-ink">{email}</span>. It expires in{' '}
          {expiresInMinutes} minutes.
        </p>

        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          <Input
            value={code}
            onChange={(e) =>
              // Strip anything non-numeric as it is typed: codes get pasted
              // with stray spaces straight out of the email.
              setCode(e.target.value.replace(/\D/g, '').slice(0, CODE_LENGTH))
            }
            required
            autoFocus
            inputMode="numeric"
            // Lets iOS and Android offer the code from the notification.
            autoComplete="one-time-code"
            placeholder="000000"
            aria-label={`${CODE_LENGTH}-digit code`}
            className="text-center text-2xl tracking-[0.4em] tabular-nums"
          />

          <Button
            type="submit"
            loading={busy}
            disabled={code.length !== CODE_LENGTH}
            className="w-full"
          >
            Continue
          </Button>
        </form>

        {notice && (
          <p className="mt-3 rounded-lg bg-raised px-3 py-2.5 text-sm text-ink-muted ring-1 ring-edge">
            {notice}
          </p>
        )}
        <ErrorNote>{error}</ErrorNote>

        <p className="mt-5 text-sm text-ink-faint">
          Not arrived? Check your spam folder.
        </p>

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
          <button
            onClick={handleResend}
            disabled={resending || cooldown > 0}
            className="min-h-11 text-sm font-medium text-brand hover:underline disabled:text-ink-faint disabled:no-underline"
          >
            {cooldown > 0 ? `Resend in ${cooldown}s` : 'Send a new code'}
          </button>
          <button
            onClick={onBack}
            className="min-h-11 text-sm text-ink-faint hover:text-ink"
          >
            Use a different email
          </button>
        </div>
      </Card>
    </>
  )
}

// ── Step one: credentials ────────────────────────────────────────────────────

export function AuthPage({ mode }: { mode: 'login' | 'signup' }) {
  const isSignup = mode === 'signup'
  const { user, requestSignup, requestLogin } = useAuth()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [error, setError] = useState<ReactNode>(null)
  const [busy, setBusy] = useState(false)
  // Set once a code has been sent; its presence is what shows step two.
  const [pending, setPending] = useState<{ email: string; minutes: number } | null>(
    null,
  )

  if (user) return <Navigate to="/app" replace />

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)

    if (isSignup && password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`)
      return
    }

    setBusy(true)
    try {
      const res = isSignup
        ? await requestSignup(email, password, fullName)
        : await requestLogin(email, password)
      setPending({ email: res.email, minutes: res.expires_in_minutes })
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
            {pending
              ? 'One more step.'
              : isSignup
                ? 'Rewrite your resume for the job you actually want.'
                : 'Welcome back.'}
          </p>
        </div>

        {pending ? (
          <CodeStep
            email={pending.email}
            expiresInMinutes={pending.minutes}
            onBack={() => setPending(null)}
          />
        ) : (
          <>
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
                  hint={
                    isSignup ? `At least ${MIN_PASSWORD_LENGTH} characters` : undefined
                  }
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

            <p className="mt-3 text-center text-xs text-ink-faint">
              We'll email you a {CODE_LENGTH}-digit code to confirm it's you.
            </p>

            <p className="mt-4 text-center text-sm text-ink-muted">
              {isSignup ? 'Already have an account? ' : "Don't have an account? "}
              <Link
                to={isSignup ? '/login' : '/signup'}
                className="font-medium text-brand hover:underline"
              >
                {isSignup ? 'Sign in' : 'Sign up'}
              </Link>
            </p>
          </>
        )}
      </div>

      <Credit className="mt-10 text-center text-xs text-ink-faint" />
    </div>
  )
}
