import { Link, NavLink, Outlet } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { Button } from './ui'

function navClasses({ isActive }: { isActive: boolean }) {
  return `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
    isActive
      ? 'bg-slate-100 text-slate-900 dark:bg-slate-800 dark:text-white'
      : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'
  }`
}

export function Layout() {
  const { user, logout } = useAuth()

  return (
    // Column layout with the main region growing, so the footer sits at the
    // bottom of the viewport on short pages instead of floating mid-screen.
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto flex max-w-5xl items-center gap-4 px-4 py-3">
          <Link to="/" className="font-semibold tracking-tight">
            Resume<span className="text-indigo-600 dark:text-indigo-400">Tailor</span>
          </Link>

          <nav className="flex items-center gap-1">
            <NavLink to="/" end className={navClasses}>
              Dashboard
            </NavLink>
          </nav>

          <div className="ml-auto flex items-center gap-3">
            <span className="hidden text-sm text-slate-500 sm:inline dark:text-slate-400">
              {user?.email}
            </span>
            <Button variant="secondary" onClick={logout}>
              Sign out
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl grow px-4 py-8">
        <Outlet />
      </main>

      <footer className="border-t border-slate-200 dark:border-slate-800">
        <div className="mx-auto max-w-5xl px-4 py-5">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <p className="text-sm text-slate-600 dark:text-slate-300">
              Built by{' '}
              <span className="font-semibold text-slate-900 dark:text-white">
                Manoj
              </span>{' '}
              &amp;{' '}
              <span className="font-semibold text-slate-900 dark:text-white">
                Pragna
              </span>
            </p>
            <a
              href="https://github.com/manojkumar606/resume-tailor"
              target="_blank"
              rel="noreferrer"
              className="ml-auto text-sm font-medium text-indigo-600 hover:underline dark:text-indigo-400"
            >
              Source on GitHub
            </a>
          </div>
          <p className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">
            Tailored resumes are AI-generated — always read one before you send it.
          </p>
        </div>
      </footer>
    </div>
  )
}
