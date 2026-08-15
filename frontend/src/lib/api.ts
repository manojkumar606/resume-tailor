import type {
  Application,
  ApplicationPatch,
  AuthResponse,
  CodeSent,
  Job,
  JobDetail,
  JobImportResult,
  JobInput,
  Resume,
  ResumeDetail,
  QuickAddInput,
  RefineInput,
  Tailoring,
  TailoringDetail,
  User,
  UUID,
} from './types'

/**
 * In development this stays empty, so requests go to a relative "/api/v1/..."
 * and Vite's dev proxy forwards them to the backend — one origin, no CORS.
 *
 * In production the frontend and backend are on different domains, so
 * VITE_API_BASE_URL must be set to the backend's origin at build time. Vite
 * inlines it into the bundle; it is not read at runtime.
 */
const API_ORIGIN = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')
const BASE = `${API_ORIGIN}/api/v1`

const TOKEN_KEY = 'resume-tailor.token'

/**
 * fetch() has no default timeout: if the API is unreachable the promise simply
 * never settles, and a submit button spins forever with no error. Observed for
 * real when the backend was down.
 *
 * Tailoring genuinely takes 10-20s, and a sleeping free-tier instance can take
 * a minute to wake, so the ceiling has to be generous rather than snappy.
 */
const REQUEST_TIMEOUT_MS = 120_000

export class ApiError extends Error {
  // Declared explicitly rather than as a constructor parameter property:
  // tsconfig enables erasableSyntaxOnly, which forbids that shorthand.
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

// Set by AuthProvider so an expired token anywhere in the app logs the user out
// once, rather than each caller having to handle 401 itself.
let unauthorizedHandler: (() => void) | null = null
export function setUnauthorizedHandler(fn: (() => void) | null) {
  unauthorizedHandler = fn
}

/**
 * Endpoints where a 401 means "those details are wrong", not "your token died".
 *
 * Without this distinction the global handler treats a failed login as an
 * expired session: it wipes the stored token and reports "your session
 * expired" to someone who never had one.
 */
const CREDENTIAL_ENDPOINTS = [
  '/auth/login',
  '/auth/signup',
  '/auth/verify-code',
  '/auth/resend-code',
]

function isCredentialEndpoint(path: string): boolean {
  return CREDENTIAL_ENDPOINTS.some((endpoint) => path.startsWith(endpoint))
}

/**
 * The backend refuses unverified accounts with 403. That state is unreachable
 * through the normal flow now — a token can only be obtained by submitting a
 * code — but the gate remains as defence in depth. If it ever fires, ending the
 * session is the right recovery: signing in again sends a fresh code, which
 * re-verifies the address.
 */
function isVerificationRefusal(status: number, message: string): boolean {
  return status === 403 && message.toLowerCase().includes('confirm your email')
}

/**
 * FastAPI returns `detail` as a string for HTTPException but as an array of
 * error objects for 422 validation failures. Flatten both into one message so
 * the UI never renders "[object Object]".
 */
function readDetail(body: unknown): string | null {
  if (typeof body !== 'object' || body === null) return null
  const detail = (body as { detail?: unknown }).detail

  if (typeof detail === 'string') return detail

  if (Array.isArray(detail)) {
    const parts = detail.map((entry) => {
      const e = entry as { loc?: unknown[]; msg?: string }
      const field = Array.isArray(e.loc)
        ? e.loc.filter((p) => p !== 'body').join('.')
        : ''
      const msg = e.msg ?? 'is invalid'
      return field ? `${field}: ${msg}` : msg
    })
    return parts.join('; ')
  }

  return null
}

async function toApiError(res: Response): Promise<ApiError> {
  let message = res.statusText || `Request failed (${res.status})`
  try {
    message = readDetail(await res.json()) ?? message
  } catch {
    // Body was not JSON — keep the status text.
  }
  return new ApiError(res.status, message)
}

async function send(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)

  // Credential endpoints are never sent a bearer token. A sign-in attempt has
  // no business carrying a stale session, and it means a 401 from one of them
  // provably cannot be an expired token.
  const credential = isCredentialEndpoint(path)
  const token = credential ? null : tokenStore.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  // Let the browser set the multipart boundary for FormData.
  if (init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  let res: Response
  try {
    res = await fetch(BASE + path, {
      ...init,
      headers,
      signal: init.signal ?? AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    })
  } catch (err) {
    // A network-level failure, not an HTTP error: server unreachable, DNS
    // failure, CORS rejection, or our own timeout firing. Translate it into an
    // ApiError so callers have one error type to handle and the UI can say
    // something useful instead of hanging.
    const timedOut = err instanceof DOMException && err.name === 'TimeoutError'
    throw new ApiError(
      0,
      timedOut
        ? 'The server took too long to respond. Please try again.'
        : 'Could not reach the server. Check your connection and try again.',
    )
  }

  // "Expired session" requires that a session was actually presented. Keyed on
  // whether a token went out rather than on the path alone, so an endpoint
  // missing from CREDENTIAL_ENDPOINTS still cannot produce a nonsensical
  // "your session expired" for someone who never had one.
  if (res.status === 401 && token) {
    tokenStore.clear()
    unauthorizedHandler?.()
    throw new ApiError(401, 'Your session expired. Please sign in again.')
  }

  if (!res.ok) {
    const error = await toApiError(res)
    if (isVerificationRefusal(error.status, error.message)) {
      tokenStore.clear()
      unauthorizedHandler?.()
      throw new ApiError(403, 'Please sign in again to confirm your email address.')
    }
    throw error
  }

  return res
}

async function json<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await send(path, init)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

/** Trigger a browser download for an endpoint that returns a file. */
async function download(path: string, fallbackName: string): Promise<void> {
  const res = await send(path)

  const disposition = res.headers.get('Content-Disposition') ?? ''
  const match = /filename="?([^"]+)"?/.exec(disposition)
  const filename = match?.[1] ?? fallbackName

  const url = URL.createObjectURL(await res.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Revoking immediately can cancel the download in some browsers.
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

export const api = {
  auth: {
    /** Creates the account and emails a code. Returns no token. */
    signup: (email: string, password: string, fullName?: string) =>
      json<CodeSent>('/auth/signup', {
        method: 'POST',
        body: JSON.stringify({
          email,
          password,
          full_name: fullName?.trim() || null,
        }),
      }),

    /** Checks the password and emails a code. Returns no token. */
    login: (email: string, password: string) =>
      json<CodeSent>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      }),

    /** The only call that yields a session. */
    verifyCode: (email: string, code: string) =>
      json<AuthResponse>('/auth/verify-code', {
        method: 'POST',
        body: JSON.stringify({ email, code }),
      }),

    resendCode: (email: string) =>
      json<{ detail: string }>('/auth/resend-code', {
        method: 'POST',
        body: JSON.stringify({ email }),
      }),

    me: () => json<User>('/auth/me'),

    /** Turn reminders off from an emailed link. Needs no session. */
    unsubscribe: (token: string) =>
      json<{ detail: string }>('/auth/unsubscribe', {
        method: 'POST',
        body: JSON.stringify({ token }),
      }),
  },

  account: {
    update: (patch: { full_name?: string | null; reminders_enabled?: boolean }) =>
      json<User>('/me', { method: 'PATCH', body: JSON.stringify(patch) }),

    exportCsv: () => download('/me/export', 'applications.csv'),

    /** Irreversible. The email is typed back as confirmation. */
    remove: (confirmEmail: string) =>
      json<void>('/me', {
        method: 'DELETE',
        body: JSON.stringify({ confirm_email: confirmEmail }),
      }),
  },

  resumes: {
    list: () => json<Resume[]>('/resumes'),

    get: (id: UUID) => json<ResumeDetail>(`/resumes/${id}`),

    upload: (file: File, name?: string) => {
      const form = new FormData()
      form.append('file', file)
      if (name?.trim()) form.append('name', name.trim())
      return json<ResumeDetail>('/resumes', { method: 'POST', body: form })
    },

    setDefault: (id: UUID) =>
      json<ResumeDetail>(`/resumes/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ is_default: true }),
      }),

    remove: (id: UUID) => json<void>(`/resumes/${id}`, { method: 'DELETE' }),

    download: (id: UUID, filename: string) =>
      download(`/resumes/${id}/download`, filename),
  },

  jobs: {
    list: () => json<Job[]>('/jobs'),

    get: (id: UUID) => json<JobDetail>(`/jobs/${id}`),

    create: (input: JobInput) =>
      json<JobDetail>('/jobs', { method: 'POST', body: JSON.stringify(input) }),

    /** Read a posting out of screenshots. Saves nothing — fills a form. */
    parseScreenshots: (files: File[]) => {
      const form = new FormData()
      for (const file of files) form.append('files', file)
      return json<JobImportResult>('/jobs/parse-screenshots', {
        method: 'POST',
        body: form,
      })
    },

    remove: (id: UUID) => json<void>(`/jobs/${id}`, { method: 'DELETE' }),
  },

  applications: {
    /** The whole board in one request. */
    list: () => json<Application[]>('/applications'),

    /** Log a job and its card together, with no tailoring involved. */
    quickAdd: (input: QuickAddInput) =>
      json<Application>('/applications/quick', {
        method: 'POST',
        body: JSON.stringify(input),
      }),

    /** Put a job that already exists on the board. */
    track: (jobId: UUID) =>
      json<Application>('/applications', {
        method: 'POST',
        body: JSON.stringify({ job_id: jobId }),
      }),

    update: (id: UUID, patch: ApplicationPatch) =>
      json<Application>(`/applications/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(patch),
      }),

    remove: (id: UUID) => json<void>(`/applications/${id}`, { method: 'DELETE' }),
  },

  tailorings: {
    listForJob: (jobId: UUID) =>
      json<Tailoring[]>(`/tailorings?job_id=${encodeURIComponent(jobId)}`),

    get: (id: UUID) => json<TailoringDetail>(`/tailorings/${id}`),

    /** Pass `refine` to revise a previous version rather than start fresh. */
    create: (jobId: UUID, resumeId?: UUID, refine?: RefineInput) =>
      json<TailoringDetail>('/tailorings', {
        method: 'POST',
        body: JSON.stringify({
          job_id: jobId,
          resume_id: resumeId ?? null,
          ...(refine ?? {}),
        }),
      }),

    remove: (id: UUID) => json<void>(`/tailorings/${id}`, { method: 'DELETE' }),

    download: (id: UUID) =>
      download(`/tailorings/${id}/download`, 'tailored-resume.docx'),
  },
}
