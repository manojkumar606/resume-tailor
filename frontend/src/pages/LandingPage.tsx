import { Link, Navigate } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { Credit, Wordmark } from '../components/Layout'
import { Reveal } from '../components/Reveal'
import { RewriteDemo } from '../components/RewriteDemo'
import { Button } from '../components/ui'
import { tokenStore } from '../lib/api'

const STEPS = [
  {
    n: '01',
    title: 'Upload your resume once',
    body: 'A .docx or .pdf. Tables and all — skills usually live in one, and most parsers drop them.',
  },
  {
    n: '02',
    title: 'Paste the job',
    body: 'The whole posting. More detail gives a sharper rewrite, and a better read on where you actually fall short.',
  },
  {
    n: '03',
    title: 'Get a version written for that role',
    body: 'Download the .docx, then track the application through to an answer.',
  },
]

const BOARD_PREVIEW: { label: string; cards: { role: string; org: string; tag?: string }[] }[] =
  [
    {
      label: 'Saved',
      cards: [{ role: 'Platform Engineer', org: 'Initech', tag: '2d to apply' }],
    },
    {
      label: 'Applied',
      cards: [
        { role: 'Backend Engineer', org: 'Northwind', tag: 'No reply in 18d' },
        { role: 'Data Engineer', org: 'Acme' },
      ],
    },
    {
      label: 'Interviewing',
      cards: [{ role: 'Python Developer', org: 'Globex' }],
    },
    { label: 'Offer', cards: [] },
  ]

function SectionHeading({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string
  title: string
  children?: React.ReactNode
}) {
  return (
    <div className="mx-auto max-w-2xl text-center">
      <Reveal>
        <p className="text-xs font-semibold tracking-[0.2em] text-brand uppercase">
          {eyebrow}
        </p>
      </Reveal>
      <Reveal delay={1}>
        <h2 className="mt-3 text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
          {title}
        </h2>
      </Reveal>
      {children && (
        <Reveal delay={2}>
          <p className="mt-3 text-sm leading-relaxed text-ink-muted sm:text-base">
            {children}
          </p>
        </Reveal>
      )}
    </div>
  )
}

export function LandingPage() {
  const { user, initialising } = useAuth()

  // Hold back the pitch only when there is a stored token still being checked,
  // so a returning user never sees a flash of marketing before the redirect.
  // First-time visitors have no token, so they get the page immediately rather
  // than a blank frame.
  if (initialising && tokenStore.get() !== null) return null

  if (user) return <Navigate to="/app" replace />

  return (
    <div className="overflow-x-hidden">
      <header className="sticky top-0 z-20 border-b border-edge bg-canvas/85 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-3">
          <Wordmark className="text-base" />
          <div className="ml-auto flex items-center gap-2">
            <Link to="/login">
              <Button variant="ghost">Sign in</Button>
            </Link>
            <Link to="/signup">
              <Button>Get started</Button>
            </Link>
          </div>
        </div>
      </header>

      {/* ── Hero ───────────────────────────────────────────────────────────── */}
      <section className="relative isolate px-4 pt-20 pb-24 sm:pt-28 sm:pb-32">
        {/* Decorative only, and hidden from assistive tech. */}
        <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
          <div className="hero-grid absolute inset-0" />
          <div className="glow-pulse absolute top-[-14rem] left-1/2 h-[34rem] w-[34rem] -translate-x-1/2 rounded-full bg-brand/20 blur-[110px]" />
        </div>

        <div className="mx-auto max-w-3xl text-center">
          <Reveal>
            <p className="inline-flex items-center gap-2 rounded-full bg-raised px-3 py-1.5 text-xs text-ink-muted ring-1 ring-edge">
              <span className="size-1.5 rounded-full bg-brand" />
              It never invents experience you don't have
            </p>
          </Reveal>

          <Reveal delay={1}>
            <h1 className="mt-6 text-4xl leading-[1.1] font-semibold tracking-tight text-ink sm:text-6xl">
              Stop sending the
              <br />
              <span className="text-ink-faint">same resume</span> to
              <br />
              every job.
            </h1>
          </Reveal>

          <Reveal delay={2}>
            <p className="mx-auto mt-6 max-w-xl text-base leading-relaxed text-ink-muted sm:text-lg">
              Paste a posting. Get your resume rewritten for that specific role —
              plus an honest read on what you're missing, and a board to track
              every application through to an answer.
            </p>
          </Reveal>

          <Reveal delay={3}>
            <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Link to="/signup" className="w-full sm:w-auto">
                <Button className="w-full px-6 sm:w-auto">Tailor my resume</Button>
              </Link>
              <Link to="/login" className="w-full sm:w-auto">
                <Button variant="secondary" className="w-full px-6 sm:w-auto">
                  I already have an account
                </Button>
              </Link>
            </div>
          </Reveal>

          <Reveal delay={4}>
            <p className="mt-5 text-xs text-ink-faint">
              Free. No card. Your resume is never shared with anyone.
            </p>
          </Reveal>
        </div>
      </section>

      {/* ── The demo ───────────────────────────────────────────────────────── */}
      <section className="border-t border-edge px-4 py-20 sm:py-24">
        <div className="mx-auto max-w-5xl">
          <SectionHeading eyebrow="What it actually does" title="Watch a bullet get rewritten">
            The same experience, aimed at one specific posting. Nothing added that
            isn't already yours.
          </SectionHeading>

          <Reveal delay={1} className="mt-10">
            <RewriteDemo />
          </Reveal>
        </div>
      </section>

      {/* ── How it works ───────────────────────────────────────────────────── */}
      <section className="border-t border-edge px-4 py-20 sm:py-24">
        <div className="mx-auto max-w-5xl">
          <SectionHeading eyebrow="Three steps" title="It takes about a minute" />

          <ol className="mt-12 grid gap-5 sm:grid-cols-3">
            {STEPS.map((step, index) => (
              <Reveal
                as="li"
                key={step.n}
                delay={(index + 1) as 1 | 2 | 3}
                className="rounded-2xl bg-panel p-5 ring-1 ring-edge"
              >
                <p className="text-xs font-semibold tabular-nums text-brand">{step.n}</p>
                <h3 className="mt-3 text-base font-semibold text-ink">{step.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-muted">{step.body}</p>
              </Reveal>
            ))}
          </ol>
        </div>
      </section>

      {/* ── The board ──────────────────────────────────────────────────────── */}
      <section className="border-t border-edge px-4 py-20 sm:py-24">
        <div className="mx-auto max-w-5xl">
          <SectionHeading
            eyebrow="Then don't lose track"
            title="Every application, in one place"
          >
            Which ones did you actually send? Who hasn't replied in three weeks?
            What closes on Friday? A tracker answers all of it — and it works for
            jobs you applied to directly, with no rewriting involved.
          </SectionHeading>

          <Reveal delay={1} className="mt-10">
            <div className="flex gap-3 overflow-x-auto pb-2">
              {BOARD_PREVIEW.map((column) => (
                <div
                  key={column.label}
                  className="w-56 shrink-0 rounded-xl bg-panel p-3 ring-1 ring-edge"
                >
                  <div className="mb-3 flex items-center justify-between px-1">
                    <p className="text-xs font-semibold tracking-wide text-ink uppercase">
                      {column.label}
                    </p>
                    <span className="text-xs tabular-nums text-ink-faint">
                      {column.cards.length}
                    </span>
                  </div>

                  <div className="space-y-2">
                    {column.cards.map((card) => (
                      <div
                        key={card.role}
                        className="rounded-lg bg-raised p-3 ring-1 ring-edge"
                      >
                        <p className="text-sm font-medium text-ink">{card.role}</p>
                        <p className="mt-0.5 text-xs text-ink-muted">{card.org}</p>
                        {card.tag && (
                          <span className="mt-2 inline-block rounded-full bg-brand-wash px-2 py-0.5 text-[11px] font-medium text-brand ring-1 ring-brand/30">
                            {card.tag}
                          </span>
                        )}
                      </div>
                    ))}
                    {column.cards.length === 0 && (
                      <p className="px-1 py-3 text-xs text-ink-faint">Nothing yet.</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── Trust ──────────────────────────────────────────────────────────── */}
      <section className="border-t border-edge px-4 py-20 sm:py-24">
        <div className="mx-auto max-w-3xl">
          <SectionHeading eyebrow="Why we ask you to paste" title="We never touch your LinkedIn" />

          <div className="mt-10 space-y-4">
            {[
              {
                title: 'We never ask for your password',
                body: 'Plenty of tools offer to log in and apply for you. That means handing over your credentials, and it breaks LinkedIn’s terms in a way that gets your account banned — not theirs.',
              },
              {
                title: 'You bring the job to us',
                body: 'Paste the posting, or its link. Slightly more effort, and nothing of yours is ever at risk.',
              },
              {
                title: 'Your resume stays yours',
                body: 'Stored against your account and used to answer your requests. Not shared, not sold, not shown to recruiters.',
              },
            ].map((item, index) => (
              <Reveal
                key={item.title}
                delay={(index + 1) as 1 | 2 | 3}
                className="rounded-2xl bg-panel p-5 ring-1 ring-edge"
              >
                <h3 className="text-base font-semibold text-ink">{item.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-muted">{item.body}</p>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ── Final call to action ───────────────────────────────────────────── */}
      <section className="relative isolate border-t border-edge px-4 py-24 sm:py-32">
        <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
          <div className="glow-pulse absolute bottom-[-18rem] left-1/2 h-[30rem] w-[30rem] -translate-x-1/2 rounded-full bg-brand/20 blur-[110px]" />
        </div>

        <div className="mx-auto max-w-2xl text-center">
          <Reveal>
            <h2 className="float-slow text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
              One posting. One tailored resume.
            </h2>
          </Reveal>
          <Reveal delay={1}>
            <p className="mt-4 text-sm text-ink-muted sm:text-base">
              Try it on a job you actually want and judge the output yourself.
            </p>
          </Reveal>
          <Reveal delay={2}>
            <Link to="/signup" className="mt-8 inline-block">
              <Button className="px-7">Get started free</Button>
            </Link>
          </Reveal>
        </div>
      </section>

      <footer className="border-t border-edge px-4 py-8">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-4 gap-y-2">
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
      </footer>
    </div>
  )
}
