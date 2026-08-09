import { Navigate, Route, Routes } from 'react-router-dom'

import { AuthProvider } from './auth/AuthContext'
import { Layout } from './components/Layout'
import { RequireAuth, RequireVerified } from './components/RequireAuth'
import { AuthPage } from './pages/AuthPage'
import { DashboardPage } from './pages/DashboardPage'
import { JobPage } from './pages/JobPage'
import { VerifyEmailPage } from './pages/VerifyEmailPage'
import { VerifyTokenPage } from './pages/VerifyTokenPage'

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="/signup" element={<AuthPage mode="signup" />} />

        {/* Public: the link is opened from a mail client, possibly on another
            device with no session. */}
        <Route path="/verify" element={<VerifyTokenPage />} />

        {/* Signed in but not yet confirmed. Deliberately outside
            RequireVerified, or it would redirect to itself forever. */}
        <Route
          path="/verify-email"
          element={
            <RequireAuth>
              <VerifyEmailPage />
            </RequireAuth>
          }
        />

        <Route
          element={
            <RequireVerified>
              <Layout />
            </RequireVerified>
          }
        >
          <Route path="/" element={<DashboardPage />} />
          <Route path="/jobs/:jobId" element={<JobPage />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  )
}
