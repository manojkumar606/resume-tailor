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
 * Images accumulate, and EVERY parse re-sends the whole set. Adding a second
 * screenshot used to mean a second independent call, so a shot taken to capture
 * the company name — with a sliver of the description in it — came back with a
 * fragment that overwrote the full description from the first. The model can
 * only stitch what it can see at once, so it always sees everything.
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
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function parse(all: File[]) {
    setError(null)
    setBusy(true)
    try {
      onParsed(await api.jobs.parseScreenshots(all))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not read those images.')
    } finally {
      setBusy(false)
    }
  }

  async function handleFiles(event: React.ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(event.target.files ?? [])
    // Reset immediately so re-picking the same file still fires a change event.
    if (inputRef.current) inputRef.current.value = ''
    if (picked.length === 0) return

    const all = [...files, ...picked]
    if (all.length > MAX_SCREENSHOTS) {
      setError(
        `Up to ${MAX_SCREENSHOTS} screenshots for one posting. Remove one first.`,
      )
      return
    }

    setFiles(all)
    await parse(all)
  }

  async function removeAt(index: number) {
    const all = files.filter((_, i) => i !== index)
    setFiles(all)
    // Re-parse what remains, so removing a bad shot actually takes effect.
    if (all.length > 0) await parse(all)
    else setError(null)
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          variant="secondary"
          loading={busy}
          disabled={files.length >= MAX_SCREENSHOTS}
          onClick={() => inputRef.current?.click()}
        >
          {files.length === 0 ? 'Import from screenshots' : 'Add another shot'}
        </Button>
        {!compact && files.length === 0 && (
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

      {files.length === 0 ? (
        <p className="mt-2 text-xs text-ink-faint">
          Select all of them at once — one for the description, another for the
          company and location. They are read together as a single posting.
        </p>
      ) : (
        <ul className="mt-3 space-y-1.5">
          {files.map((file, index) => (
            <li
              key={`${file.name}-${index}`}
              className="flex items-center gap-2 rounded-lg bg-raised px-2.5 py-1.5 ring-1 ring-edge"
            >
              <span className="min-w-0 flex-1 truncate text-xs text-ink-muted">
                {file.name}
              </span>
              <button
                type="button"
                disabled={busy}
                onClick={() => removeAt(index)}
                className="shrink-0 text-xs font-medium text-brand hover:underline disabled:text-ink-faint"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      {busy && (
        <p className="mt-2 text-xs text-ink-muted">
          Reading {files.length} screenshot{files.length === 1 ? '' : 's'} together…
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
        The description looked cut off. Add another screenshot of the rest — it
        will be re-read together with the others, not on its own.
      </p>
    )
  }
  return (
    <p className="mt-3 rounded-lg bg-raised px-3 py-2.5 text-xs text-ink-muted ring-1 ring-edge">
      Filled in from your screenshots. Check it before saving — you can edit
      anything below.
    </p>
  )
}
