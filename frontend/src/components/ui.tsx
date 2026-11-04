import { AlertTriangle, CheckCircle2, CircleHelp, FlaskConical, Loader2, PlugZap, Scale, XCircle } from 'lucide-react'
import type { ReactNode } from 'react'
import type { FindingStatus, Provenance, ProviderState } from '../api'

export const btn = {
  primary:
    'inline-flex items-center justify-center gap-2 rounded-lg bg-violet-brand px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-violet-700 disabled:opacity-50',
  secondary:
    'inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-navy-900 hover:bg-slate-50 disabled:opacity-50',
  ghost: 'inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-violet-700 hover:bg-violet-50',
}

export const input =
  'w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm text-slate-900 focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-200'

export function Card({ title, action, children, className = '' }: {
  title?: ReactNode
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`rounded-2xl border border-slate-200 bg-white p-5 ${className}`}>
      {(title || action) && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold text-navy-900">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-slate-500">
      <Loader2 className="size-4 animate-spin" /> {label}
    </span>
  )
}

export function ErrorNote({ error }: { error: string | null }) {
  if (!error) return null
  return (
    <p role="alert" className="flex items-start gap-2 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">
      <XCircle className="mt-0.5 size-4 shrink-0" /> {error}
    </p>
  )
}

export function DemoBanner() {
  return (
    <p className="flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-800">
      <FlaskConical className="size-4 shrink-0" />
      Demo — synthetic documents. Figures illustrate the workflow and describe no real claim.
    </p>
  )
}

const STATUS_STYLE: Record<FindingStatus, [string, string, typeof CheckCircle2]> = {
  supported: ['Supported', 'bg-emerald-50 text-emerald-700 ring-emerald-200', CheckCircle2],
  contestable: ['Potentially contestable', 'bg-violet-50 text-violet-700 ring-violet-200', Scale],
  unverified: ['Unverified', 'bg-amber-50 text-amber-800 ring-amber-200', CircleHelp],
}

export function StatusBadge({ status }: { status: FindingStatus }) {
  const [label, cls, Icon] = STATUS_STYLE[status]
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${cls}`}>
      <Icon className="size-3.5" /> {label}
    </span>
  )
}

export function ProvenanceBadges({ p }: { p: Provenance }) {
  const chip = 'rounded-full px-2 py-0.5 text-xs font-medium ring-1'
  return (
    <span className="flex flex-wrap gap-1.5">
      <span className={`${chip} ${p.ai_generated ? 'bg-violet-50 text-violet-700 ring-violet-200' : 'bg-slate-50 text-slate-700 ring-slate-200'}`}>
        {p.label}
      </span>
      {p.text_method && <span className={`${chip} bg-slate-50 text-slate-600 ring-slate-200`}>{p.text_method}</span>}
      {p.demo && <span className={`${chip} bg-amber-50 text-amber-800 ring-amber-200`}>Synthetic / demo</span>}
      {p.manually_corrected && <span className={`${chip} bg-sky-50 text-sky-700 ring-sky-200`}>Manually corrected</span>}
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

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block text-xs font-medium text-slate-600">
      {label}
      <div className="mt-1">{children}</div>
    </label>
  )
}
