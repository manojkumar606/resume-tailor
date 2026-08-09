import { Link, Outlet } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { Button } from './ui'

export function Wordmark({ className = '' }: { className?: string }) {
  return (
    <span className={`font-semibold tracking-tight ${className}`}>
      Resume<span className="text-brand">Tailor</span>
    </span>
  )
}

function Credit({ className = '' }: { className?: string }) {
  return (
    <p className={className}>
      Built by <span className="font-semibold text-ink">Manoj</span> &amp;{' '}
      <span className="font-semibold text-ink">Pragna</span>
    </p>
  )
}

export { Credit }

export function Layout() {
  const { user, logout } = useAuth()

  return (
    // Flex column with a growing main region, so the footer rests at the bottom
    // of the viewport on short pages rather than floating mid-screen.
    <div className="flex min-h-screen flex-col">
      {/* Sticky on mobile, where vertical space is scarce and scrolling back up
          to reach navigation is the most common annoyance. */}
      <header className="sticky top-0 z-10 border-b border-edge bg-canvas/90 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-3">
          <Link to="/" className="shrink-0 text-base">
            <Wordmark />
          </Link>

          <div className="ml-auto flex min-w-0 items-center gap-3">
            {/* Hidden on narrow screens: the address truncates to uselessness
                and the sign-out button matters more. */}
            <span className="hidden min-w-0 truncate text-sm text-ink-muted sm:inline">
              {user?.email}
            </span>
            <Button variant="secondary" onClick={logout} className="shrink-0">
              Sign out
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl grow px-4 py-6 sm:py-10">
        <Outlet />
      </main>

      <footer className="border-t border-edge">
        <div className="mx-auto max-w-5xl px-4 py-5">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <Credit className="text-sm text-ink-muted" />
            <a
              href="https://github.com/manojkumar606/resume-tailor"
              target="_blank"
              rel="noreferrer"
              className="ml-auto text-sm font-medium text-brand hover:underline"
            >
              Source on GitHub
            </a>
          </div>
          <p className="mt-2 text-xs text-ink-faint">
            Tailored resumes are AI-generated — always read one before you send it.
          </p>
        </div>
      </footer>
    </div>
  )
}
