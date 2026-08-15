import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { Credit, Wordmark } from '../components/Layout'
import { Button, Card, ErrorNote } from '../components/ui'
import { api } from '../lib/api'

/**
 * Landing page for the "turn reminders off" link in a digest.
 *
 * Public, and it must stay that way: somebody irritated by an email will not
 * log in to find a setting, they will press "mark as spam" — and because the
 * digest and the sign-in codes share one sender, that harms delivery of the
 * codes people need to get in at all.
 *
 * The state change happens on a button press, not on page load. Mail clients
 * and security scanners prefetch links, so unsubscribing on arrival would
 * silently opt people out who never clicked anything.
 */
export function UnsubscribePage() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''

  const [state, setState] = useState<'ready' | 'working' | 'done'>('ready')
  const [error, setError] = useState<string | null>(null)

  async function confirm() {
    setError(null)
    setState('working')
    try {
      await api.auth.unsubscribe(token)
      setState('done')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That link did not work.')
      setState('ready')
    }
  }

  return (
    <div className="flex min-h-screen flex-col px-4 py-10">
      <div className="mx-auto flex w-full max-w-md grow flex-col justify-center">
        <div className="mb-7 text-center">
          <Link to="/">
            <Wordmark className="text-2xl" />
          </Link>
        </div>

        <Card>
          {state === 'done' ? (
            <>
              <h1 className="text-lg font-semibold text-ink">Reminders are off</h1>
              <p className="mt-2 text-sm leading-relaxed text-ink-muted">
                You won't get any more digest emails. Sign-in codes still work
                exactly as before — this doesn't affect getting into your account.
              </p>
              <p className="mt-2 text-sm text-ink-muted">
                Changed your mind? Turn them back on in Settings.
              </p>
              <Link to="/board" className="mt-5 inline-block">
                <Button variant="secondary">Go to my board</Button>
              </Link>
            </>
          ) : !token ? (
            <>
              <h1 className="text-lg font-semibold text-ink">Link incomplete</h1>
              <p className="mt-2 text-sm text-ink-muted">
                This link is missing its code. Use the one in the email, or turn
                reminders off in Settings.
              </p>
            </>
          ) : (
            <>
              <h1 className="text-lg font-semibold text-ink">
                Turn off reminder emails?
              </h1>
              <p className="mt-2 text-sm leading-relaxed text-ink-muted">
                You'll stop getting the digest about closing deadlines and
                applications that have gone quiet.
              </p>
              <p className="mt-2 text-xs text-ink-faint">
                Sign-in codes are unaffected — you'll still be able to log in.
              </p>

              <div className="mt-5">
                <Button loading={state === 'working'} onClick={confirm}>
                  Turn reminders off
                </Button>
              </div>

              <ErrorNote>{error}</ErrorNote>
            </>
          )}
        </Card>
      </div>

      <Credit className="mt-10 text-center text-xs text-ink-faint" />
    </div>
  )
}
