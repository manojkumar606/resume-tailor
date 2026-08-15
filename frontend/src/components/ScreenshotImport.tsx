import { useRef, useState } from 'react'

import { api } from '../lib/api'
import type { JobImportResult } from '../lib/types'
import { Button, ErrorNote } from './ui'

const MAX_SCREENSHOTS = 4

/**
 * Reads a job posting out of screenshots and hands the fields to a form.
 *
 * Screenshots rather than a pasted URL: LinkedIn, Naukri and Indeed all block
 * server-side fetching — auth walls, Cloudflare, datacenter-IP bans — and those
 * are exactly where people find jobs. A screenshot has already been rendered by
 * the user's own logged-in browser, so none of that applies.
 *
 * It fills the form rather than saving. Extraction is fuzzy, and a silently
 * wrong company name is worse than no import at all.
 */
export function ScreenshotImport({
  onParsed,
  compact = false,
}: {
  onParsed: (result: JobImportResult) => void
  /** Hides the explanatory line where space is tight. */
  compact?: boolean
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleFiles(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? [])
    // Reset immediately so re-picking the same file still fires a change event.
    if (inputRef.current) inputRef.current.value = ''
    if (files.length === 0) return

    if (files.length > MAX_SCREENSHOTS) {
      setError(`Pick at most ${MAX_SCREENSHOTS} screenshots at once.`)
      return
    }

    setError(null)
    setBusy(true)
    try {
      onParsed(await api.jobs.parseScreenshots(files))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not read those images.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          variant="secondary"
          loading={busy}
          onClick={() => inputRef.current?.click()}
        >
          Import from screenshot
        </Button>
        {!compact && (
          <p className="text-xs text-ink-faint">
            Works on LinkedIn and Naukri, where pasting a link doesn't.
          </p>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        multiple
        onChange={handleFiles}
        className="hidden"
      />

      {busy && (
        <p className="mt-2 text-xs text-ink-muted">
          Reading the posting… this takes a few seconds.
        </p>
      )}

      <ErrorNote>{error}</ErrorNote>
    </div>
  )
}

/** Shown after an import so the user knows what to check before saving. */
export function ImportNotice({ confidence }: { confidence: string }) {
  if (confidence === 'partial') {
    return (
      <p className="mt-3 rounded-lg bg-brand-wash px-3 py-2.5 text-xs text-brand ring-1 ring-brand/30">
        The description looked cut off. Add another screenshot of the rest, or
        paste the missing text — a truncated posting gives a weaker rewrite.
      </p>
    )
  }
  return (
    <p className="mt-3 rounded-lg bg-raised px-3 py-2.5 text-xs text-ink-muted ring-1 ring-edge">
      Filled in from your screenshot. Check it before saving.
    </p>
  )
}
