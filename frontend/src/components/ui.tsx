import {
  AlertTriangle,
  CheckCircle2,
  CircleHelp,
  Download,
  FlaskConical,
  Info,
  Loader2,
  PlugZap,
  X,
  XCircle,
} from 'lucide-react'
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { rupees, type FindingStatus, type Money, type Provenance, type ProviderState } from '../api'

const base =
  'inline-flex h-9 items-center justify-center gap-2 whitespace-nowrap rounded-md px-3.5 text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-45'

export const btn = {
  primary: `${base} bg-navy-900 text-white hover:bg-navy-700 active:bg-navy-800`,
  secondary: `${base} border border-line bg-white text-navy-900 shadow-[0_1px_0_rgb(11_16_38/0.04)] hover:border-slate-300 hover:bg-slate-50`,
  ghost:
    'inline-flex items-center gap-1.5 rounded px-1.5 py-1 text-xs font-medium text-violet-700 transition-colors hover:bg-violet-50 hover:text-violet-800 disabled:opacity-45',
  icon: 'inline-flex size-8 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700',
}

export const input =
  'h-9 w-full rounded-md border border-line bg-white px-2.5 text-sm text-slate-900 transition-colors placeholder:text-slate-400 hover:border-slate-300 focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/15'

// Spreadsheet-style cell: borderless until hovered or focused, so extracted tables read like the source document.
export const cell =
  'h-8 w-full rounded border border-transparent bg-transparent px-2 text-sm text-slate-900 transition-colors hover:border-line focus:border-violet-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-violet-500/15'

export const eyebrow = 'text-[11px] font-medium uppercase tracking-[0.12em] text-slate-500'

export function Card({ title, action, children, className = '', flush = false }: {
  title?: ReactNode
  action?: ReactNode
  children: ReactNode
  className?: string
  flush?: boolean
}) {
  return (
    <section className={`rounded-lg border border-line bg-white shadow-[0_1px_2px_rgb(11_16_38/0.03)] ${className}`}>
      {(title || action) && (
        <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-line px-5 py-3">
          {title && <h2 className="text-sm font-semibold">{title}</h2>}
          {action}
        </header>
      )}
      <div className={flush ? '' : 'p-5'}>{children}</div>
    </section>
  )
}

export function PageHeader({ kicker, title, description, actions, children }: {
  kicker?: ReactNode
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  children?: ReactNode
}) {
  return (
    <header className="flex flex-col gap-4 border-b border-line pb-6 md:flex-row md:items-end md:justify-between">
      <div className="min-w-0">
        {kicker && <div className={eyebrow}>{kicker}</div>}
        <h1 className="mt-1.5 font-serif text-[1.75rem] font-semibold leading-tight tracking-[-0.01em]">{title}</h1>
        {description && <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-slate-600">{description}</p>}
        {children}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </header>
  )
}

/** A rupee figure with tabular digits and de-emphasised symbol and paise, so magnitudes compare at a glance. */
export function Amount({ value, className = '' }: { value: Money | number | null | undefined; className?: string }) {
  const s = rupees(typeof value === 'number' ? value.toFixed(2) : value)
  if (s === '—') return <span className={`text-slate-300 ${className}`}>—</span>
  const [whole, paise] = s.slice(1).split('.')
  return (
    <span className={`whitespace-nowrap tabular-nums ${className}`}>
      <span className="mr-[0.08em] font-sans text-[0.78em] font-normal text-slate-400">₹</span>
      {whole}
      <span className="text-[0.82em] text-slate-400">.{paise}</span>
    </span>
  )
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-slate-500" role="status">
      <Loader2 className="size-4 animate-spin" /> {label}
    </span>
  )
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-slate-200/70 ${className}`} />
}

export function ErrorNote({ error }: { error: string | null }) {
  if (!error) return null
  return (
    <p role="alert" className="flex items-start gap-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
      <XCircle className="mt-0.5 size-4 shrink-0" /> {error}
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
    <div className="flex flex-col items-center px-6 py-12 text-center">
      <span className="flex size-10 items-center justify-center rounded-md bg-slate-100 text-slate-500">
        <Icon className="size-5" />
      </span>
      <p className="mt-4 text-sm font-semibold text-navy-900">{title}</p>
      {children && <div className="mt-1 max-w-sm text-sm text-slate-500">{children}</div>}
      {actions && <div className="mt-5 flex flex-wrap justify-center gap-2">{actions}</div>}
    </div>
  )
}

export function DemoBanner() {
  return (
    <p className="flex items-start gap-2.5 rounded-md border border-amber-300/70 bg-amber-50 px-3 py-2 text-sm text-amber-900">
      <FlaskConical className="mt-0.5 size-4 shrink-0 text-amber-700" />
      <span>
        <span className="mr-1.5 font-mono text-xs font-medium tracking-wide text-amber-800">DEMO DATA</span>
        Synthetic documents. Figures illustrate the workflow and describe no real claim.
      </span>
    </p>
  )
}

export function DemoTag() {
  return (
    <span className="inline-flex items-center rounded-sm bg-amber-100 px-1.5 py-px font-mono text-[10px] font-medium tracking-wide text-amber-800">
      DEMO
    </span>
  )
}

export const STATUS: Record<FindingStatus, { label: string; fill: string; text: string; tint: string; meaning: string }> = {
  supported: {
    label: 'Supported',
    fill: 'fill-supported',
    text: 'text-slate-600',
    tint: 'bg-slate-100',
    meaning: 'The uploaded documents support this deduction.',
  },
  contestable: {
    label: 'Potentially contestable',
    fill: 'fill-contestable',
    text: 'text-violet-700',
    tint: 'bg-violet-50',
    meaning: 'The documents do not support all of this deduction.',
  },
  unverified: {
    label: 'Unverified',
    fill: 'fill-unverified',
    text: 'text-amber-800',
    tint: 'bg-amber-50',
    meaning: 'Not enough information to check this deduction.',
  },
}

export function Swatch({ fill, className = '' }: { fill: string; className?: string }) {
  return <span aria-hidden className={`inline-block size-2.5 shrink-0 rounded-[2px] ${fill} ${className}`} />
}

export function StatusBadge({ status }: { status: FindingStatus }) {
  const s = STATUS[status]
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded px-1.5 py-0.5 text-xs font-medium ${s.tint} ${s.text}`}>
      <Swatch fill={s.fill} /> {s.label}
    </span>
  )
}

/**
 * Clavion's signature: the claimed amount split into what was paid and what was deducted,
 * with deductions in the three finding states. Display only; every figure comes from the audit.
 */
export function LedgerBar({ approved, supported, contestable, unverified, className = 'h-3' }: {
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
    ['Unverified', unverified, 'fill-unverified'],
  ]
  const total = parts.reduce((s, [, v]) => s + Math.max(v, 0), 0) || 1
  return (
    <div
      role="img"
      aria-label={parts.map(([l, v]) => `${l} ${rupees(v.toFixed(2))}`).join(', ')}
      className={`flex w-full gap-px overflow-hidden rounded-sm bg-slate-100 ${className}`}
    >
      {parts.map(([label, v, fill]) =>
        v > 0 ? (
          <span key={label} title={`${label}: ${rupees(v.toFixed(2))}`} className={`${fill} min-w-[3px] transition-[flex-grow] duration-500`}
            style={{ flexGrow: v / total }} />
        ) : null,
      )}
    </div>
  )
}

export function ProvenanceBadges({ p }: { p: Provenance }) {
  const chip = 'inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium'
  return (
    <span className="flex flex-wrap gap-1.5">
      <span className={`${chip} ${p.ai_generated ? 'bg-violet-50 text-violet-700' : 'bg-slate-100 text-slate-700'}`}>{p.label}</span>
      {p.text_method && <span className={`${chip} bg-slate-100 text-slate-600`}>{p.text_method}</span>}
      {p.demo && <span className={`${chip} bg-amber-100 text-amber-800`}>Synthetic / demo</span>}
      {p.manually_corrected && <span className={`${chip} bg-sky-50 text-sky-800`}>Manually corrected</span>}
    </span>
  )
}

export const PROVIDER_STATE: Record<ProviderState, [string, string, typeof CheckCircle2]> = {
  available: ['Available', 'text-emerald-700', CheckCircle2],
  connected: ['Connected', 'text-emerald-700', PlugZap],
  not_configured: ['Not configured', 'text-slate-500', CircleHelp],
  subscription_required: ['Subscription required', 'text-amber-700', AlertTriangle],
  connection_failed: ['Connection failed', 'text-rose-600', XCircle],
  not_checked: ['Not checked yet', 'text-slate-500', CircleHelp],
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="block text-xs font-medium text-slate-600">
      {label}
      <div className="mt-1">{children}</div>
      {hint && <span className="mt-1 block font-normal text-slate-500">{hint}</span>}
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
  const ICON = { success: [CheckCircle2, 'text-emerald-400'], error: [XCircle, 'text-rose-400'], info: [Info, 'text-violet-300'] } as const
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-4 bottom-4 z-50 flex flex-col items-end gap-2 sm:left-auto sm:w-96">
        {toasts.map((t) => {
          const [Icon, cls] = ICON[t.tone]
          return (
            <div key={t.id} role={t.tone === 'error' ? 'alert' : 'status'}
              className="pointer-events-auto flex w-full animate-toast-in items-start gap-2.5 rounded-md bg-navy-900 px-3.5 py-3 text-sm text-slate-100 shadow-lg shadow-navy-950/20">
              <Icon className={`mt-0.5 size-4 shrink-0 ${cls}`} />
              <span className="flex-1">{t.text}</span>
              <button onClick={() => dismiss(t.id)} aria-label="Dismiss" className="text-slate-400 hover:text-white">
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
      const r = await fetch(href)
      if (!r.ok) {
        const body = await r.json().catch(() => null)
        throw new Error(typeof body?.detail === 'string' ? body.detail : `Export failed (${r.status})`)
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
      {busy ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" />}
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
      className="m-auto w-[min(28rem,calc(100vw-2rem))] rounded-lg border border-line bg-white p-0 text-slate-800 shadow-xl shadow-navy-950/20 backdrop:bg-navy-950/45">
      <div className="p-5">
        <h2 id="confirm-title" className="flex items-center gap-2 text-base font-semibold">
          <AlertTriangle className="size-4 text-amber-600" /> {title}
        </h2>
        <div className="mt-2 text-sm leading-relaxed text-slate-600">{children}</div>
      </div>
      <div className="flex justify-end gap-2 rounded-b-lg border-t border-line bg-slate-50 px-5 py-3">
        <button className={btn.secondary} onClick={onCancel}>Cancel</button>
        <button className={btn.primary} onClick={onConfirm}>{confirmLabel}</button>
      </div>
    </dialog>
  )
}
