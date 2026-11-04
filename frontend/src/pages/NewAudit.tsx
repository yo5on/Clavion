import { CheckCircle2, Download, FileUp, FlaskConical, Loader2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, DOC_LABELS, type DocType, type Provider } from '../api'
import { useProviders } from '../components/ProviderStatus'
import { Card, ErrorNote, Field, PROVIDER_STATE, btn, input } from '../components/ui'

const DOCS: [DocType, string][] = [
  ['bill', 'Final itemised in-patient bill'],
  ['policy', 'Policy wording or schedule with room-rent, sub-limit and non-payable clauses'],
  ['settlement', 'Insurer’s claim settlement letter listing the deductions'],
]
const ACCEPT = '.pdf,.png,.jpg,.jpeg,.webp,.txt'

export function providerUsable(p: Provider) {
  return p.status.state === 'available' || p.status.state === 'connected'
}

export function ProviderSelect({ value, onChange }: { value: Provider['id']; onChange: (v: Provider['id']) => void }) {
  const { providers } = useProviders()
  return (
    <select className={input} value={value} onChange={(e) => onChange(e.target.value as Provider['id'])}>
      {(providers ?? []).map((p) => (
        <option key={p.id} value={p.id} disabled={!providerUsable(p)}>
          {p.label}
          {providerUsable(p) ? '' : ` — ${PROVIDER_STATE[p.status.state][0]}`}
        </option>
      ))}
    </select>
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
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-navy-900">New audit</h1>
        <p className="mt-1 text-sm text-slate-600">
          Files are read in memory on this server and discarded; only the extracted text and fields are saved.
        </p>
      </div>

      <form onSubmit={submit} className="grid gap-6 lg:grid-cols-3">
        <Card title="Claim documents" className="lg:col-span-2">
          <div className="space-y-4">
            <Field label="Case title">
              <input className={input} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Appendectomy, Oct 2026" />
            </Field>
            {DOCS.map(([docType, hint]) => (
              <div key={docType} className="rounded-xl border border-dashed border-slate-300 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-navy-900">{DOC_LABELS[docType]}</p>
                    <p className="text-xs text-slate-500">{hint}</p>
                  </div>
                  <label className={`${btn.secondary} cursor-pointer`}>
                    <FileUp className="size-4" /> {files[docType] ? 'Change file' : 'Choose file'}
                    <input
                      type="file"
                      accept={ACCEPT}
                      className="sr-only"
                      onChange={(e) => setFiles((f) => ({ ...f, [docType]: e.target.files?.[0] }))}
                    />
                  </label>
                </div>
                {files[docType] && (
                  <p className="mt-2 flex items-center gap-2 text-xs text-slate-600">
                    {progress[docType] === 'working' && <Loader2 className="size-3.5 animate-spin" />}
                    {progress[docType] === 'done' && <CheckCircle2 className="size-3.5 text-emerald-600" />}
                    {files[docType]!.name} · {(files[docType]!.size / 1024).toFixed(0)} KB
                  </p>
                )}
              </div>
            ))}
            <ErrorNote error={error} />
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div className="w-full sm:w-72">
                <Field label="Extraction provider">
                  <ProviderSelect value={provider} onChange={setProvider} />
                </Field>
              </div>
              <button type="submit" className={btn.primary} disabled={busy || !Object.values(files).some(Boolean)}>
                {busy && <Loader2 className="size-4 animate-spin" />} Extract and review
              </button>
            </div>
            <p className="text-xs text-slate-500">
              PDF text layers are read directly; images and scanned pages go through local OCR. You will review and
              correct every extracted field before the audit runs.
            </p>
          </div>
        </Card>

        <Card title="No documents to hand?">
          <p className="text-sm text-slate-600">
            Run the full workflow on Clavion’s synthetic claim. Its documents are invented and labelled as demo
            throughout.
          </p>
          <button type="button" className={`${btn.secondary} mt-4 w-full`} onClick={demo} disabled={busy}>
            <FlaskConical className="size-4" /> Load synthetic demo case
          </button>
          <p className="mt-5 text-xs font-medium text-slate-600">Or download the synthetic files and upload them:</p>
          <ul className="mt-2 space-y-1">
            {DOCS.map(([docType]) => (
              <li key={docType} className="flex items-center justify-between text-xs">
                <span className="text-slate-700">{DOC_LABELS[docType]}</span>
                <span className="flex gap-1">
                  <a className={btn.ghost} href={api.demoDocumentUrl(docType, 'pdf')}><Download className="size-3.5" /> PDF</a>
                  <a className={btn.ghost} href={api.demoDocumentUrl(docType, 'png')}><Download className="size-3.5" /> Image</a>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      </form>
    </div>
  )
}
