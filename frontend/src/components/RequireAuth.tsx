import { Navigate, useLocation } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { Spinner } from './ui'

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, initialising } = useAuth()
  const location = useLocation()

  // Without this gate the app would redirect to /login on every refresh, before
  // the stored token has had a chance to be verified.
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
