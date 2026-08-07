import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { Button, Card, ErrorNote, Field, Input } from '../components/ui'

const MIN_PASSWORD_LENGTH = 8

export function AuthPage({ mode }: { mode: 'login' | 'signup' }) {
  const isSignup = mode === 'signup'
  const { user, login, signup } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to="/" replace />

  const redirectTo =
    (location.state as { from?: string } | null)?.from ?? '/'

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)

    if (isSignup && password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`)
      return
    }

    setBusy(true)
    try {
      if (isSignup) {
        await signup(email, password, fullName)
      } else {
        await login(email, password)
      }
      navigate(redirectTo, { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <h1 className="mb-1 text-center text-2xl font-semibold tracking-tight">
          Resume<span className="text-indigo-600 dark:text-indigo-400">Tailor</span>
        </h1>
        <p className="mb-6 text-center text-sm text-slate-500 dark:text-slate-400">
          {isSignup
            ? 'Create an account to start tailoring.'
            : 'Sign in to your account.'}
        </p>

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

        <p className="mt-4 text-center text-sm text-slate-500 dark:text-slate-400">
          {isSignup ? (
            <>
              Already have an account?{' '}
              <Link to="/login" className="font-medium text-indigo-600 dark:text-indigo-400">
                Sign in
              </Link>
            </>
          ) : (
            <>
              Don't have an account?{' '}
              <Link to="/signup" className="font-medium text-indigo-600 dark:text-indigo-400">
                Sign up
              </Link>
            </>
          )}
        </p>

        {/* Layout's footer only renders on authenticated pages, so the credit
            is repeated here — this is the first screen any visitor sees. */}
        <p className="mt-8 text-center text-xs text-slate-500 dark:text-slate-400">
          Built by{' '}
          <span className="font-semibold text-slate-700 dark:text-slate-200">
            Manoj
          </span>{' '}
          &amp;{' '}
          <span className="font-semibold text-slate-700 dark:text-slate-200">
            Pragna
          </span>
        </p>
      </div>
    </div>
  )
}
