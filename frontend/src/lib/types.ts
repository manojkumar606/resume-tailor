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
  created_at: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: User
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
  source: JobSource
  created_at: string
}

export interface JobDetail extends Job {
  description: string
}

export interface JobInput {
  title: string
  company: string
  description: string
  location?: string | null
  source_url?: string | null
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
}

export interface TailoringDetail extends Tailoring {
  tailored_text: string | null
  missing_keywords: string[] | null
  changes: string[] | null
}
