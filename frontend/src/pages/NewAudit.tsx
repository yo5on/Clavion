import { Check, FileText, Loader2, X } from 'lucide-react'
import { useState, type DragEvent, type FormEvent, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, DOC_LABELS, type DocType, type Provider } from '../api'
import { useProviders } from '../components/ProviderStatus'
import { Chevron, DemoTag, ErrorNote, Field, PROVIDER_STATE, PageHeader, Section, btn, input } from '../components/ui'

const DOCS: [DocType, string][] = [
  ['bill', 'The final itemised in-patient bill.'],
  ['policy', 'Policy wording or schedule, with room-rent, sub-limit and non-payable clauses.'],
  ['settlement', 'The insurer’s settlement letter listing each deduction.'],
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
      className={`${className} transition-[background-color,box-shadow] duration-200 ${dragging ? 'bg-paper! ring-2 ring-accent-fill ring-inset' : ''}`}
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
    <label className={`${className} cursor-pointer has-[:disabled]:pointer-events-none has-[:disabled]:opacity-36 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-3 has-[:focus-visible]:outline-accent-fill`}>
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
    <div className="space-y-16 sm:space-y-20">
      <PageHeader
        title="Start a new audit"
        description="Add the three claim documents. You will review every field Clavion reads from them before the audit runs."
      />

      <form onSubmit={submit} className="space-y-10">
        <div className="max-w-md">
          <Field label="Case title">
            <input className={input} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Appendectomy, Oct 2026" />
          </Field>
        </div>

        <ul className="grid gap-4 md:grid-cols-3">
          {DOCS.map(([docType, hint]) => {
            const f = files[docType]
            const state = progress[docType]
            const pick = (file: File) => setFiles((fs) => ({ ...fs, [docType]: file }))
            return (
              <li key={docType}>
                <FileDrop onFile={pick} disabled={busy}
                  className={`flex h-full min-h-60 flex-col rounded-[28px] p-6 sm:p-7 ${f ? 'bg-paper ring-1 ring-hairline-strong' : 'bg-tile'}`}>
                  {(dragging) => (
                    <>
                      <span aria-hidden className={`flex size-10 items-center justify-center rounded-full transition-colors duration-300 ${f ? 'bg-ink text-white' : 'bg-paper text-mute'}`}>
                        {state === 'working' ? <Loader2 className="size-[18px] animate-spin" /> : f ? <Check className="size-[18px]" strokeWidth={2.25} /> : <FileText className="size-[18px]" strokeWidth={1.75} />}
                      </span>
                      <p className="type-heading mt-6">{DOC_LABELS[docType]}</p>
                      <p className="mt-1.5 text-[15px] leading-relaxed text-mute">
                        {dragging ? 'Drop to attach.' : hint}
                        {docType === 'settlement' && !dragging && <span className="block text-ink-2">Required for the audit.</span>}
                      </p>
                      <div className="mt-auto pt-6">
                        {f ? (
                          <div className="flex items-center gap-3 text-sm">
                            <span className="min-w-0 flex-1">
                              <span className="block truncate font-medium text-ink">{f.name}</span>
                              <span className="tabular-nums text-mute">
                                {(f.size / 1024).toFixed(0)} KB
                                {state === 'working' && ' · Reading…'}
                                {state === 'done' && ' · Read'}
                              </span>
                            </span>
                            {!busy && (
                              <button type="button" className={`${btn.icon} -mr-2 shrink-0`} aria-label={`Remove ${DOC_LABELS[docType]}`}
                                onClick={() => setFiles((fs) => ({ ...fs, [docType]: undefined }))}>
                                <X className="size-4" />
                              </button>
                            )}
                          </div>
                        ) : (
                          <FilePick disabled={busy} onFile={pick} className={btn.link}
                            label={<>Choose a file <Chevron /></>} />
                        )}
                      </div>
                    </>
                  )}
                </FileDrop>
              </li>
            )
          })}
        </ul>

        <ErrorNote error={error} />

        <div className="flex flex-col gap-6 border-t border-hairline pt-8 sm:flex-row sm:items-end sm:justify-between">
          <div className="sm:w-80">
            <Field label="Read documents with">
              <ProviderSelect value={provider} onChange={setProvider} />
            </Field>
          </div>
          <button type="submit" className={`${btn.primary} self-start sm:self-auto`} disabled={busy || count === 0}>
            {busy && <Loader2 className="size-4 animate-spin" />}
            {busy ? 'Reading documents…' : count ? `Read ${count} document${count > 1 ? 's' : ''}` : 'Read and review'}
          </button>
        </div>
        <p className="max-w-3xl text-sm leading-relaxed text-mute">
          Files are read in memory on this server and discarded; only the extracted text and fields are saved. PDF text
          layers are read directly; images and scanned pages go through local OCR. Accepts PDF, PNG, JPG, WEBP and TXT.
        </p>
      </form>

      <Section>
        <div className="grid gap-10 md:grid-cols-2 md:gap-16">
          <div>
            <h2 className="type-title flex items-center gap-3">Try the demo claim <DemoTag /></h2>
            <p className="mt-3 text-[17px] leading-relaxed text-mute">
              Run the full workflow on Clavion’s synthetic claim. Its documents are invented and labelled as demo throughout.
            </p>
            <button type="button" className={`${btn.secondary} mt-6`} onClick={demo} disabled={busy}>Open the demo claim</button>
          </div>
          <div>
            <p className="text-[15px] font-medium text-ink">Or download the synthetic files to try uploading</p>
            <ul className="mt-3 divide-y divide-hairline border-y border-hairline">
              {DOCS.map(([docType]) => (
                <li key={docType} className="flex items-center justify-between gap-4 py-3 text-[15px]">
                  <span className="text-ink-2">{DOC_LABELS[docType]}</span>
                  <span className="flex gap-5">
                    <a className={btn.linkSm} href={api.demoDocumentUrl(docType, 'pdf')} aria-label={`Download demo ${DOC_LABELS[docType]} as PDF`}>PDF</a>
                    <a className={btn.linkSm} href={api.demoDocumentUrl(docType, 'png')} aria-label={`Download demo ${DOC_LABELS[docType]} as PNG`}>PNG</a>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Section>
    </div>
  )
}
