import { CheckCircle2, Download, FileText, FileUp, FlaskConical, Loader2, X } from 'lucide-react'
import { useState, type DragEvent, type FormEvent, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, DOC_LABELS, type DocType, type Provider } from '../api'
import { useProviders } from '../components/ProviderStatus'
import { Card, DemoTag, ErrorNote, Field, PROVIDER_STATE, PageHeader, btn, input } from '../components/ui'

const DOCS: [DocType, string][] = [
  ['bill', 'Final itemised in-patient bill'],
  ['policy', 'Policy wording or schedule with room-rent, sub-limit and non-payable clauses'],
  ['settlement', 'Insurer’s claim settlement letter listing the deductions'],
]
const ACCEPT = '.pdf,.png,.jpg,.jpeg,.webp,.txt'

export function providerUsable(p: Provider) {
  return p.status.state === 'available' || p.status.state === 'connected'
}

export function ProviderSelect({ value, onChange, className = input }: {
  value: Provider['id']
  onChange: (v: Provider['id']) => void
  className?: string
}) {
  const { providers } = useProviders()
  return (
    <select className={className} aria-label="Extraction provider" value={value} onChange={(e) => onChange(e.target.value as Provider['id'])}>
      {(providers ?? []).map((p) => (
        <option key={p.id} value={p.id} disabled={!providerUsable(p)}>
          {p.label}
          {providerUsable(p) ? '' : ` — ${PROVIDER_STATE[p.status.state][0]}`}
        </option>
      ))}
    </select>
  )
}

/** Drop target that also opens the file picker; highlights while a file is dragged over it. */
export function FileDrop({ onFile, disabled, className = '', children }: {
  onFile: (f: File) => void
  disabled?: boolean
  className?: string
  children: (dragging: boolean) => ReactNode
}) {
  const [dragging, setDragging] = useState(false)
  const over = (e: DragEvent, on: boolean) => {
    e.preventDefault()
    if (!disabled) setDragging(on)
  }
  return (
    <div
      className={`${className} transition-colors ${dragging ? 'bg-violet-50/60 outline-2 -outline-offset-2 outline-dashed outline-violet-400' : ''}`}
      onDragOver={(e) => over(e, true)}
      onDragLeave={(e) => over(e, false)}
      onDrop={(e) => {
        over(e, false)
        const f = e.dataTransfer.files?.[0]
        if (f && !disabled) onFile(f)
      }}
    >
      {children(dragging)}
    </div>
  )
}

export function FilePick({ label, onFile, disabled, className = btn.secondary }: {
  label: ReactNode
  onFile: (f: File) => void
  disabled?: boolean
  className?: string
}) {
  return (
    <label className={`${className} cursor-pointer has-[:disabled]:pointer-events-none has-[:disabled]:opacity-45 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-violet-600`}>
      {label}
      <input type="file" accept={ACCEPT} className="sr-only" disabled={disabled}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = '' }} />
    </label>
  )
}

export default function NewAudit() {
  const [title, setTitle] = useState('')
  const [files, setFiles] = useState<Partial<Record<DocType, File>>>({})
  const [provider, setProvider] = useState<Provider['id']>('local')
  const [progress, setProgress] = useState<Partial<Record<DocType, 'working' | 'done'>>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()
  const count = Object.values(files).filter(Boolean).length

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const c = await api.createCase(title || 'Untitled claim')
      for (const [docType] of DOCS) {
        const f = files[docType]
        if (!f) continue
        setProgress((p) => ({ ...p, [docType]: 'working' }))
        try {
          await api.upload(c.id, docType, f, provider)
        } catch (err) {
          throw new Error(`${DOC_LABELS[docType]}: ${(err as Error).message}`)
        }
        setProgress((p) => ({ ...p, [docType]: 'done' }))
      }
      navigate(`/cases/${c.id}?tab=review`)
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  async function demo() {
    setBusy(true)
    try {
      const c = await api.demoCase()
      navigate(`/cases/${c.id}?tab=review`)
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="New case"
        title="New audit"
        description="Files are read in memory on this server and discarded; only the extracted text and fields are saved. You will review every extracted field before the audit runs."
      />

      <form onSubmit={submit} className="grid items-start gap-6 lg:grid-cols-3">
        <Card title="Claim documents" className="lg:col-span-2" flush>
          <div className="border-b border-line p-5">
            <Field label="Case title">
              <input className={input} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Appendectomy, Oct 2026" />
            </Field>
          </div>
          <ul className="divide-y divide-line">
            {DOCS.map(([docType, hint]) => {
              const f = files[docType]
              const state = progress[docType]
              return (
                <li key={docType}>
                  <FileDrop onFile={(file) => setFiles((fs) => ({ ...fs, [docType]: file }))} disabled={busy} className="px-5 py-4">
                    {(dragging) => (
                      <div className="flex gap-4">
                        <span className={`flex size-9 shrink-0 items-center justify-center rounded-md ${f ? 'bg-navy-900 text-white' : 'bg-slate-100 text-slate-500'}`}>
                          <FileText className="size-4" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <p className="flex items-center gap-2 text-sm font-medium text-navy-900">
                                {DOC_LABELS[docType]}
                                {docType === 'settlement' && <span className="text-xs font-normal text-slate-500">· needed for the audit</span>}
                              </p>
                              <p className="mt-0.5 text-xs text-slate-500">{dragging ? 'Drop to attach' : hint}</p>
                            </div>
                            <FilePick disabled={busy} onFile={(file) => setFiles((fs) => ({ ...fs, [docType]: file }))}
                              label={<><FileUp className="size-4" /> {f ? 'Change' : 'Choose file'}</>} />
                          </div>
                          {f && (
                            <p className="mt-2.5 flex items-center gap-2 text-xs text-slate-600">
                              {state === 'working' && <Loader2 className="size-3.5 animate-spin text-violet-600" />}
                              {state === 'done' && <CheckCircle2 className="size-3.5 text-emerald-600" />}
                              <span className="truncate font-medium text-slate-700">{f.name}</span>
                              <span className="shrink-0 tabular-nums text-slate-400">{(f.size / 1024).toFixed(0)} KB</span>
                              {state === 'working' && <span className="text-violet-700">Extracting…</span>}
                              {!busy && (
                                <button type="button" className="ml-auto rounded p-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label={`Remove ${DOC_LABELS[docType]}`}
                                  onClick={() => setFiles((fs) => ({ ...fs, [docType]: undefined }))}>
                                  <X className="size-3.5" />
                                </button>
                              )}
                            </p>
                          )}
                        </div>
                      </div>
                    )}
                  </FileDrop>
                </li>
              )
            })}
          </ul>
          <div className="space-y-4 border-t border-line bg-slate-50/60 p-5">
            <ErrorNote error={error} />
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <div className="sm:w-72">
                <Field label="Extraction provider">
                  <ProviderSelect value={provider} onChange={setProvider} />
                </Field>
              </div>
              <button type="submit" className={btn.primary} disabled={busy || count === 0}>
                {busy && <Loader2 className="size-4 animate-spin" />}
                {busy ? 'Extracting…' : count ? `Extract ${count} document${count > 1 ? 's' : ''}` : 'Extract and review'}
              </button>
            </div>
            <p className="text-xs leading-relaxed text-slate-500">
              PDF text layers are read directly; images and scanned pages go through local OCR. Accepts PDF, PNG, JPG, WEBP and TXT.
            </p>
          </div>
        </Card>

        <Card title={<span className="flex items-center gap-2">Demo claim <DemoTag /></span>}>
          <p className="text-sm leading-relaxed text-slate-600">
            Run the full workflow on Clavion’s synthetic claim. Its documents are invented and labelled as demo throughout.
          </p>
          <button type="button" className={`${btn.secondary} mt-4 w-full`} onClick={demo} disabled={busy}>
            <FlaskConical className="size-4" /> Open demo claim
          </button>
          <p className="mt-6 text-xs font-medium text-slate-600">Or download the synthetic files to try uploading:</p>
          <ul className="mt-2 divide-y divide-line border-y border-line">
            {DOCS.map(([docType]) => (
              <li key={docType} className="flex items-center justify-between py-1.5 text-sm">
                <span className="text-slate-700">{DOC_LABELS[docType]}</span>
                <span className="flex gap-1">
                  <a className={btn.ghost} href={api.demoDocumentUrl(docType, 'pdf')}><Download className="size-3.5" /> PDF</a>
                  <a className={btn.ghost} href={api.demoDocumentUrl(docType, 'png')}><Download className="size-3.5" /> PNG</a>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      </form>
    </div>
  )
}
