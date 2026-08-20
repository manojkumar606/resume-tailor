/**
 * Mirrors the Pydantic schemas in backend/app/schemas/.
 *
 * Kept hand-written rather than generated so the contract stays readable, but
 * it must be updated whenever a backend schema changes.
 */

export type UUID = string

export interface User {
  id: UUID
  email: string
  full_name: string | null
  is_active: boolean
  /** False until the emailed link is redeemed. Gates every route but /auth. */
  is_verified: boolean
  /** Daily digest opt-out. Never affects sign-in codes. */
  reminders_enabled: boolean
  created_at: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: User
}

/**
 * What signup and login return instead of a token. Neither step grants access on
 * its own — the emailed code has to be submitted first.
 */
export interface CodeSent {
  status: string
  email: string
  expires_in_minutes: number
  detail: string
}

/** One signed-in device, as listed in settings. */
export interface DeviceSession {
  id: UUID
  /** A short label like "Chrome on Windows" — never the raw user agent. */
  device: string
  last_used_at: string
  created_at: string
  expires_at: string
  /** The browser making the request. Cannot be signed out from the list. */
  is_current: boolean
}

export interface Resume {
  id: UUID
  name: string
  original_filename: string | null
  is_default: boolean
  created_at: string
}

export interface ResumeDetail extends Resume {
  parsed_text: string | null
}

export type JobSource = 'manual' | 'url' | 'extension'

export interface Job {
  id: UUID
  title: string
  company: string
  location: string | null
  source_url: string | null
  /** ISO date (no time) for when the posting closes. */
  apply_by: string | null
  /** False for tracking-only jobs — they cannot be tailored. */
  has_description: boolean
  source: JobSource
  created_at: string
}

export interface JobDetail extends Job {
  description: string
}

export interface JobInput {
  title: string
  company: string
  /** Optional: omit to track an application without tailoring. */
  description?: string | null
  location?: string | null
  source_url?: string | null
  apply_by?: string | null
}

/** Fields read from screenshots. Nothing is saved until the user confirms. */
export interface JobImportResult {
  title: string | null
  company: string | null
  location: string | null
  /** ISO date, or null when none was visible. */
  apply_by: string | null
  description: string | null
  /** "partial" means the description was visibly cut off. */
  confidence: 'high' | 'partial' | 'unreadable'
}

export type ApplicationStatus =
  | 'saved'
  | 'applied'
  | 'interviewing'
  | 'offer'
  | 'rejected'

export type ApplicationSource =
  | 'unknown'
  | 'referral'
  | 'job_board'
  | 'company_site'
  | 'recruiter'
  | 'other'

export interface ApplicationJob {
  id: UUID
  title: string
  company: string
  location: string | null
  source_url: string | null
  apply_by: string | null
  has_description: boolean
}

export interface ApplicationTailoring {
  id: UUID
  match_score: number | null
  missing_keywords: string[] | null
}

export interface Application {
  id: UUID
  status: ApplicationStatus
  applied_at: string | null
  notes: string | null
  created_at: string
  updated_at: string
  source: ApplicationSource
  interview_at: string | null
  job: ApplicationJob
  tailoring: ApplicationTailoring | null
  /** Server-computed so the threshold lives in one place. */
  is_stale: boolean
  days_since_update: number
  /** Negative once the deadline has passed; null when none is set. */
  days_until_deadline: number | null
  /** A resume was tailored for this role but the card still says Saved. */
  needs_apply_prompt: boolean
}

export interface QuickAddInput {
  title: string
  company: string
  location?: string | null
  source_url?: string | null
  apply_by?: string | null
  description?: string | null
  status?: ApplicationStatus
  notes?: string | null
  /** How it was submitted. Named apart from the job's own `source`. */
  applied_via?: ApplicationSource
}

export interface ApplicationPatch {
  status?: ApplicationStatus
  notes?: string | null
  tailoring_id?: UUID | null
  source?: ApplicationSource
  interview_at?: string | null
  /** Answering "not yet" to the apply prompt. */
  dismiss_apply_prompt?: boolean
}

export type TailoringStatus = 'pending' | 'running' | 'succeeded' | 'failed'

export interface Tailoring {
  id: UUID
  job_id: UUID
  resume_id: UUID
  status: TailoringStatus
  match_score: number | null
  model: string | null
  error: string | null
  created_at: string
  completed_at: string | null
  /** The version this one was a revision of, if any. */
  refine_of_id: UUID | null
  /** What the candidate said was wrong with that previous version. */
  feedback: string[] | null
  feedback_notes: string | null
}

export interface RefineInput {
  refine_of: UUID
  feedback: string[]
  feedback_notes?: string | null
}

export interface TailoringDetail extends Tailoring {
  tailored_text: string | null
  missing_keywords: string[] | null
  changes: string[] | null
}
