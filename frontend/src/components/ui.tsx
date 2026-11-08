import { AlertCircle, AlertTriangle, CheckCircle2, ChevronRight, Download, Info, Loader2, X, XCircle } from 'lucide-react'
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { rupees, type FindingStatus, type Money, type Provenance, type ProviderState } from '../api'

const pill =
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full font-medium transition-[background-color,color,box-shadow,transform] duration-200 ease-apple active:scale-[0.98] disabled:pointer-events-none disabled:opacity-36'
// apple.com's .button (filled blue) and .button-secondary (blue outline that fills on hover).
const primary = 'bg-accent-fill text-white hover:bg-accent-fill-hover active:bg-accent-fill-active'
const secondary = 'bg-transparent text-accent ring-1 ring-inset ring-accent hover:bg-accent-fill-hover hover:text-white hover:ring-accent-fill-hover active:bg-accent-fill-active'

export const btn = {
  primary: `${pill} ${primary} h-11 px-5 text-[15px]`,
  secondary: `${pill} ${secondary} h-11 px-5 text-[15px]`,
  primarySm: `${pill} ${primary} h-9 px-4 text-sm`,
  secondarySm: `${pill} ${secondary} h-9 px-4 text-sm`,
  /** Inline action in the accent colour, in the manner of “Learn more ›”. */
  link: 'inline-flex items-center gap-0.5 rounded-sm text-[15px] text-accent hover:underline underline-offset-4 disabled:pointer-events-none disabled:opacity-42',
  linkSm: 'inline-flex items-center gap-1 rounded-sm text-sm text-accent hover:underline underline-offset-4 disabled:pointer-events-none disabled:opacity-42',
  icon: 'inline-flex size-9 items-center justify-center rounded-full text-mute transition-colors hover:bg-tile hover:text-ink',
}

export const input =
  'h-11 w-full rounded-xl border border-hairline-strong bg-paper px-3.5 text-[15px] text-ink transition-[border-color,box-shadow] duration-200 placeholder:text-faint hover:border-faint focus:border-accent-fill focus:outline-none focus:ring-1 focus:ring-accent-fill'

// Spreadsheet-style cell: borderless until hovered or focused, so extracted tables read like the source document.
export const cell =
  'h-9 w-full rounded-lg border border-transparent bg-transparent px-2 text-[15px] text-ink transition-[border-color,box-shadow,background-color] duration-200 hover:border-hairline-strong focus:border-accent-fill focus:bg-paper focus:outline-none focus:ring-1 focus:ring-accent-fill'

/** Small sentence-case label for figures and fields. */
export const caption = 'text-[13px] font-medium text-mute'

/** The one raised surface: used for things that are a “document” or a focused detail, never for layout. */
export const panel = 'rounded-[28px] bg-tile'

export const Chevron = () => <ChevronRight aria-hidden className="size-4 translate-y-px" strokeWidth={2} />

export function PageHeader({ kicker, title, description, actions, children }: {
  kicker?: ReactNode
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  children?: ReactNode
}) {
  return (
    <header className="flex flex-col gap-6 pt-6 pb-2 sm:pt-12 md:flex-row md:items-end md:justify-between">
      <div className="min-w-0 max-w-3xl">
        {kicker && <div className="mb-3 text-[15px] font-medium text-mute">{kicker}</div>}
        <h1 className="type-headline">{title}</h1>
        {description && <p className="type-lead mt-4 max-w-2xl">{description}</p>}
        {children}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-3">{actions}</div>}
    </header>
  )
}

/** A titled region separated by whitespace and a hairline rather than a box. */
export function Section({ title, action, children, className = '', id }: {
  title?: ReactNode
  action?: ReactNode
  children: ReactNode
  className?: string
  id?: string
}) {
  return (
    <section id={id} className={`border-t border-hairline pt-8 sm:pt-10 ${className}`}>
      {(title || action) && (
        <header className="mb-6 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
          {title && <h2 className="type-title">{title}</h2>}
          {action}
        </header>
      )}
      {children}
    </section>
  )
}

/** A rupee figure with tabular digits and de-emphasised symbol and paise, so magnitudes compare at a glance. */
export function Amount({ value, className = '' }: { value: Money | number | null | undefined; className?: string }) {
  const s = rupees(value)
  if (s === '—') return <span className={`text-faint ${className}`}>—</span>
  const [whole, paise] = s.slice(s.indexOf('₹') + 1).split('.')
  return (
    <span className={`whitespace-nowrap tabular-nums ${className}`}>
      {s.startsWith('-') && '−'}
      <span className="mr-[0.06em] text-[0.8em] font-normal">₹</span>
      {whole}
      <span className="text-[0.72em] font-normal">.{paise}</span>
    </span>
  )
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-mute" role="status">
      <Loader2 className="size-4 animate-spin" /> {label}
    </span>
  )
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-xl bg-tile ${className}`} />
}

export function ErrorNote({ error }: { error: string | null }) {
  if (!error) return null
  return (
    <p role="alert" className="flex animate-fade-in items-start gap-3 rounded-2xl bg-alert-soft px-4 py-3.5 text-[15px] text-alert">
      <AlertCircle className="mt-0.5 size-[18px] shrink-0" strokeWidth={1.75} /> <span className="min-w-0">{error}</span>
    </p>
  )
}

export function EmptyState({ icon: Icon, title, children, actions }: {
  icon: typeof Info
  title: string
  children?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center px-6 py-16 text-center sm:py-24">
      <Icon aria-hidden className="size-9 text-faint" strokeWidth={1.25} />
      <p className="type-title mt-6">{title}</p>
      {children && <div className="mt-3 max-w-md text-[17px] leading-relaxed text-mute">{children}</div>}
      {actions && <div className="mt-8 flex flex-wrap items-center justify-center gap-x-6 gap-y-3">{actions}</div>}
    </div>
  )
}

export function DemoBanner() {
  return (
    <p className="flex items-start gap-3 rounded-2xl bg-caution-soft px-4 py-3.5 text-[15px] text-ink-2">
      <span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-caution-fill" />
      <span><span className="font-semibold text-caution">Demo claim.</span> These documents are synthetic. The figures illustrate the workflow and describe no real claim.</span>
    </p>
  )
}

export function DemoTag() {
  return (
    <span className="inline-flex shrink-0 items-center rounded-full bg-caution-soft px-2 py-0.5 text-xs font-medium text-caution">Demo</span>
  )
}

export const STATUS: Record<FindingStatus, { label: string; fill: string; text: string; meaning: string }> = {
  supported: {
    label: 'Supported',
    fill: 'fill-supported',
    text: 'text-mute',
    meaning: 'The uploaded documents support this deduction.',
  },
  contestable: {
    label: 'Potentially contestable',
    fill: 'fill-contestable',
    text: 'text-accent',
    meaning: 'The documents do not support all of this deduction.',
  },
  unverified: {
    label: 'Needs clarification',
    fill: 'fill-unverified',
    text: 'text-caution',
    meaning: 'The documents cannot settle this deduction; the insurer must explain it.',
  },
}

export function Swatch({ fill, className = '' }: { fill: string; className?: string }) {
  return <span aria-hidden className={`inline-block size-2 shrink-0 rounded-full ${fill} ${className}`} />
}

export function StatusBadge({ status }: { status: FindingStatus }) {
  const s = STATUS[status]
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap text-[13px] font-medium ${s.text}`}>
      <Swatch fill={s.fill} /> {s.label}
    </span>
  )
}

/**
 * Clavion's signature: the claimed amount split into what was paid and what was deducted,
 * with deductions in the three finding states. Display only; every figure comes from the audit.
 */
export function LedgerBar({ approved, supported, contestable, unverified, className = 'h-2.5' }: {
  approved: number
  supported: number
  contestable: number
  unverified: number
  className?: string
}) {
  const parts: [string, number, string][] = [
    ['Approved', approved, 'fill-approved'],
    ['Supported deductions', supported, 'fill-supported'],
    ['Potentially contestable', contestable, 'fill-contestable'],
    ['Needs clarification', unverified, 'fill-unverified'],
  ]
  const total = parts.reduce((s, [, v]) => s + Math.max(v, 0), 0) || 1
  return (
    <div
      role="img"
      aria-label={parts.map(([l, v]) => `${l} ${rupees(v)}`).join(', ')}
      className={`flex w-full gap-[3px] overflow-hidden rounded-full ${className}`}
    >
      {parts.map(([label, v, fill]) =>
        v > 0 ? (
          <span key={label} title={`${label}: ${rupees(v)}`} className={`${fill} min-w-1 rounded-full transition-[flex-grow] duration-700 ease-apple`}
            style={{ flexGrow: v / total }} />
        ) : null,
      )}
    </div>
  )
}

/** Where a document's data came from, as a quiet line of facts rather than a row of chips. */
export function ProvenanceBadges({ p }: { p: Provenance }) {
  const facts: [string, string][] = [[p.label, p.ai_generated ? 'text-accent' : 'text-ink-2']]
  if (p.text_method) facts.push([p.text_method, 'text-mute'])
  if (p.demo) facts.push(['Synthetic / demo', 'text-caution'])
  if (p.manually_corrected) facts.push(['Manually corrected', 'text-ink-2'])
  return (
    <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
      {facts.map(([t, cls], i) => (
        <span key={t} className="flex items-center gap-2">
          {i > 0 && <span aria-hidden className="text-faint">·</span>}
          <span className={cls}>{t}</span>
        </span>
      ))}
    </span>
  )
}

export const PROVIDER_STATE: Record<ProviderState, [string, string, typeof CheckCircle2]> = {
  available: ['Available', 'text-ok', CheckCircle2],
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="block text-[13px] font-medium text-ink-2">
      {label}
      <div className="mt-1.5">{children}</div>
      {hint && <span className="mt-1.5 block font-normal text-mute">{hint}</span>}
    </label>
  )
}

type Toast = { id: number; tone: 'success' | 'error' | 'info'; text: string }
const ToastContext = createContext<(tone: Toast['tone'], text: string) => void>(() => {})
export const useToast = () => useContext(ToastContext)
let toastId = 0

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const dismiss = useCallback((id: number) => setToasts((ts) => ts.filter((t) => t.id !== id)), [])
  const push = useCallback(
    (tone: Toast['tone'], text: string) => {
      const id = ++toastId
      setToasts((ts) => [...ts.slice(-2), { id, tone, text }])
      setTimeout(() => dismiss(id), tone === 'error' ? 7000 : 4000)
    },
    [dismiss],
  )
  const ICON = { success: [CheckCircle2, 'text-on-dark-ok'], error: [XCircle, 'text-on-dark-alert'], info: [Info, 'text-on-dark-accent'] } as const
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-4 bottom-5 z-50 flex flex-col items-center gap-2">
        {toasts.map((t) => {
          const [Icon, cls] = ICON[t.tone]
          return (
            <div key={t.id} role={t.tone === 'error' ? 'alert' : 'status'}
              className="pointer-events-auto flex w-full max-w-md animate-toast-in items-start gap-3 rounded-2xl bg-ink px-4 py-3.5 text-[15px] text-white shadow-[0_12px_32px_-12px_rgb(0_0_0/0.35)]">
              <Icon className={`mt-0.5 size-[18px] shrink-0 ${cls}`} strokeWidth={1.75} />
              <span className="flex-1">{t.text}</span>
              <button onClick={() => dismiss(t.id)} aria-label="Dismiss" className="-m-1 rounded-full p-1 text-on-dark-mute transition-colors hover:text-white">
                <X className="size-4" />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

/** Fetches a PDF before saving it, so a failed export shows a message instead of navigating to an error page. */
export function PdfButton({ href, children, disabled, title, className = btn.secondary }: {
  href: string
  children: ReactNode
  disabled?: boolean
  title?: string
  className?: string
}) {
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  async function download() {
    setBusy(true)
    try {
      const r = await fetch(href, { credentials: 'include' })
      if (!r.ok) {
        if (r.status === 401) window.dispatchEvent(new Event('clavion-auth-required'))
        const body = await r.json().catch(() => null)
        throw new Error(typeof body?.detail === 'string' ? body.detail.charAt(0).toUpperCase() + body.detail.slice(1) : `Export failed (${r.status})`)
      }
      const name = /filename="([^"]+)"/.exec(r.headers.get('Content-Disposition') ?? '')?.[1] ?? 'clavion.pdf'
      const url = URL.createObjectURL(await r.blob())
      const a = Object.assign(document.createElement('a'), { href: url, download: name })
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      toast('success', `Downloaded ${name}`)
    } catch (e) {
      toast('error', (e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <button type="button" className={className} onClick={download} disabled={disabled || busy} title={title}>
      {busy ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" strokeWidth={1.75} />}
      {busy ? 'Preparing PDF…' : children}
    </button>
  )
}

export function ConfirmDialog({ open, title, children, confirmLabel, onConfirm, onCancel }: {
  open: boolean
  title: string
  children: ReactNode
  confirmLabel: string
  onConfirm: () => void
  onCancel: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const d = ref.current
    if (open && !d?.open) d?.showModal()
    if (!open && d?.open) d.close()
  }, [open])
  return (
    <dialog ref={ref} aria-labelledby="confirm-title" onCancel={(e) => { e.preventDefault(); onCancel() }}
      className="m-auto w-[min(24rem,calc(100vw-2rem))] rounded-[28px] bg-paper p-0 text-ink-2 shadow-[0_24px_64px_-16px_rgb(0_0_0/0.3)] open:animate-toast-in backdrop:bg-black/40 backdrop:animate-fade-in">
      <div className="px-7 pt-8 pb-6 text-center">
        <AlertTriangle aria-hidden className="mx-auto size-7 text-caution" strokeWidth={1.5} />
        <h2 id="confirm-title" className="type-heading mt-4">{title}</h2>
        <div className="mt-2 text-[15px] leading-relaxed text-mute">{children}</div>
      </div>
      <div className="grid grid-cols-2 gap-3 px-6 pb-6">
        <button className={btn.secondary} onClick={onCancel}>Cancel</button>
        <button className={btn.primary} onClick={onConfirm}>{confirmLabel}</button>
      </div>
    </dialog>
  )
}
