import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { Spinner } from './ui'

/**
 * Signed in. That is now also sufficient proof the address was confirmed: a
 * token can only be obtained by submitting an emailed code, so there is no
 * separate "verified" check to make on the client.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, initialising } = useAuth()
  const location = useLocation()

  // Without this gate the app redirects to /login on every refresh, before the
  // stored token has had a chance to be verified.
  if (initialising) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner label="Loading…" />
      </div>
    )
  }

  if (!user) {
    // Remember where they were headed so login can send them back.
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  return <>{children}</>
}
