import { useRef, useState } from 'react'

/**
 * Segmented code entry — one box per digit.
 *
 * Built on a *single* real input rather than six. Six inputs need manual focus
 * juggling and still break the things people actually do: pasting the code,
 * hitting backspace across a boundary, and letting the OS autofill it from the
 * notification. One input keeps all of that working for free; the boxes are
 * presentation, sitting under a transparent field that covers the whole row.
 */
export function CodeInput({
  value,
  onChange,
  length,
  disabled,
  label,
}: {
  value: string
  onChange: (next: string) => void
  length: number
  disabled?: boolean
  label: string
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [focused, setFocused] = useState(false)

  const digits = Array.from({ length }, (_, i) => value[i] ?? '')
  // The box that will receive the next keystroke.
  const activeIndex = Math.min(value.length, length - 1)

  return (
    <div
      className="relative"
      // Tapping anywhere on the row focuses the hidden field, so the boxes
      // behave like one control.
      onClick={() => inputRef.current?.focus()}
    >
      <div className="flex justify-between gap-1.5 sm:gap-2">
        {digits.map((digit, index) => {
          const isActive = focused && index === activeIndex && !disabled
          return (
            <div
              key={index}
              aria-hidden
              className={`flex h-14 flex-1 items-center justify-center rounded-lg bg-raised text-xl font-semibold tabular-nums text-ink ring-1 transition-all ${
                isActive
                  ? 'ring-2 ring-brand'
                  : digit
                    ? 'ring-edge-strong'
                    : 'ring-edge'
              } ${disabled ? 'opacity-50' : ''}`}
            >
              {digit || (isActive ? <span className="caret h-6 w-[2px] bg-brand" /> : '')}
            </div>
          )
        })}
      </div>

      <input
        ref={inputRef}
        value={value}
        onChange={(e) =>
          // Strip anything non-numeric as it arrives: codes get pasted with
          // stray spaces and dashes straight out of the email.
          onChange(e.target.value.replace(/\D/g, '').slice(0, length))
        }
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        disabled={disabled}
        required
        autoFocus
        inputMode="numeric"
        // Lets iOS and Android offer the code straight from the notification.
        autoComplete="one-time-code"
        aria-label={label}
        maxLength={length}
        // Transparent rather than hidden: a display:none or visibility:hidden
        // field cannot be focused, and some browsers refuse to autofill it.
        className="absolute inset-0 h-full w-full cursor-pointer bg-transparent text-transparent caret-transparent outline-none"
      />
    </div>
  )
}
