import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react'

/* Shared primitives. Every colour here comes from a token in index.css, so the
   palette can change in one place rather than across a hundred class strings. */

const VARIANTS = {
  primary: 'bg-brand text-white hover:bg-brand-hover',
  secondary: 'bg-raised text-ink ring-1 ring-edge hover:bg-edge hover:ring-edge-strong',
  ghost: 'bg-transparent text-ink-muted hover:bg-raised hover:text-ink',
  danger: 'bg-transparent text-brand ring-1 ring-brand/40 hover:bg-brand-wash',
} as const

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof VARIANTS
  loading?: boolean
}

export function Button({
  variant = 'primary',
  loading = false,
  className = '',
  disabled,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      /* min-h-11 keeps every button at ~44px, the minimum comfortable touch
         target on a phone. */
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-4 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${VARIANTS[variant]} ${className}`}
    >
      {loading && (
        <span
          aria-hidden
          className="size-3.5 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      )}
      {children}
    </button>
  )
}

const FIELD =
  'block w-full min-h-11 rounded-lg border-0 bg-raised px-3.5 py-2.5 text-base text-ink ring-1 ring-edge transition-shadow placeholder:text-ink-faint focus:ring-2 focus:ring-brand sm:text-sm'

export function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: ReactNode
  children: ReactNode
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-ink">{label}</span>
      {children}
      {hint && <span className="mt-1.5 block text-xs text-ink-muted">{hint}</span>}
    </label>
  )
}

/* text-base on mobile then sm:text-sm — iOS Safari zooms the whole page when a
   focused input's font is under 16px, which is jarring mid-form. */
export function Input({ className = '', ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...rest} className={`${FIELD} ${className}`} />
}

export function Textarea({
  className = '',
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...rest} className={`${FIELD} resize-y leading-relaxed ${className}`} />
}

export function Select({
  className = '',
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...rest} className={`${FIELD} ${className}`} />
}

export function Card({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <section
      className={`rounded-xl bg-panel p-4 ring-1 ring-edge sm:p-5 ${className}`}
    >
      {children}
    </section>
  )
}

export function CardTitle({ children }: { children: ReactNode }) {
  return <h2 className="text-sm font-semibold tracking-wide text-ink uppercase">{children}</h2>
}

export function ErrorNote({ children }: { children: ReactNode }) {
  if (!children) return null
  return (
    <p
      role="alert"
      className="mt-3 rounded-lg bg-brand-wash px-3 py-2.5 text-sm text-brand ring-1 ring-brand/30"
    >
      {children}
    </p>
  )
}

export function Spinner({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2.5 py-6 text-sm text-ink-muted">
      <span
        aria-hidden
        className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent"
      />
      {label}
    </div>
  )
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <p className="px-2 py-8 text-center text-sm text-ink-muted">{children}</p>
  )
}

export function Pill({
  children,
  tone = 'neutral',
}: {
  children: ReactNode
  tone?: 'neutral' | 'brand' | 'quiet'
}) {
  const tones = {
    neutral: 'bg-raised text-ink ring-edge',
    brand: 'bg-brand-wash text-brand ring-brand/30',
    quiet: 'bg-transparent text-ink-muted ring-edge',
  } as const
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ring-1 ${tones[tone]}`}
    >
      {children}
    </span>
  )
}


export function Toggle({
  checked,
  onChange,
  disabled,
  label,
}: {
  checked: boolean
  onChange: (next: boolean) => void
  disabled?: boolean
  label: string
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
        checked ? 'bg-brand' : 'bg-edge'
      }`}
    >
      <span
        aria-hidden
        className={`inline-block size-4 rounded-full bg-white transition-transform ${
          checked ? 'translate-x-6' : 'translate-x-1'
        }`}
      />
    </button>
  )
}
