import { Navigate, Route, Routes } from 'react-router-dom'

import { AuthProvider } from './auth/AuthContext'
import { Layout } from './components/Layout'
import { RequireAuth } from './components/RequireAuth'
import { AuthPage } from './pages/AuthPage'
import { BoardPage } from './pages/BoardPage'
import { DashboardPage } from './pages/DashboardPage'
import { LandingPage } from './pages/LandingPage'
import { SettingsPage } from './pages/SettingsPage'
import { UnsubscribePage } from './pages/UnsubscribePage'
import { JobPage } from './pages/JobPage'

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        {/* Public pitch. Redirects signed-in visitors to the app itself. */}
        <Route path="/" element={<LandingPage />} />

        {/* Public: reached from a link in an email, with no session. */}
        <Route path="/unsubscribe" element={<UnsubscribePage />} />

        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="/signup" element={<AuthPage mode="signup" />} />

        {/* No separate verification route: a session can only be obtained by
            submitting an emailed code, so holding a token already implies a
            confirmed address. RequireAuth is therefore sufficient. */}
        <Route
          element={
            <RequireAuth>
              <Layout />
            </RequireAuth>
          }
        >
          <Route path="/app" element={<DashboardPage />} />
          <Route path="/board" element={<BoardPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/jobs/:jobId" element={<JobPage />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  )
}
