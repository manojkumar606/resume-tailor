import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { Spinner } from './ui'

function Booting() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <Spinner label="Loading…" />
    </div>
  )
}

/** Signed in. Says nothing about whether the email is confirmed. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, initialising } = useAuth()
  const location = useLocation()

  // Without this gate the app redirects to /login on every refresh, before the
  // stored token has had a chance to be verified.
  if (initialising) return <Booting />

  if (!user) {
    // Remember where they were headed so login can send them back.
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  return <>{children}</>
}

/**
 * Signed in *and* email confirmed — the requirement for everything except the
 * auth screens. Mirrors get_verified_user on the backend; without it, every
 * request from an unverified account would come back 403 and each page would
 * have to handle that itself.
 */
export function RequireVerified({ children }: { children: ReactNode }) {
  const { user, initialising } = useAuth()
  const location = useLocation()

  if (initialising) return <Booting />

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  if (!user.is_verified) {
    return <Navigate to="/verify-email" replace />
  }

  return <>{children}</>
}
