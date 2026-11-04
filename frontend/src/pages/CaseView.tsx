import { Download, FileUp, Loader2, PlayCircle, Save } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api, DOC_LABELS, type CaseDetail, type DocType, type Provider } from '../api'
import AuditView from '../components/AuditView'
import { BillEditor, PolicyEditor, SettlementEditor } from '../components/ReviewForms'
import { Card, DemoBanner, ErrorNote, Field, ProvenanceBadges, Spinner, btn, input } from '../components/ui'
import { ProviderSelect } from './NewAudit'

const TABS = [
  ['review', 'Extracted data'],
  ['audit', 'Audit'],
  ['appeal', 'Appeal letter'],
] as const
type Tab = (typeof TABS)[number][0]
const DOC_ORDER: DocType[] = ['bill', 'policy', 'settlement']

export default function CaseView() {
  const { id = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const tab = (params.get('tab') as Tab) || 'review'
  const [c, setCase] = useState<CaseDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [auditing, setAuditing] = useState(false)

  useEffect(() => {
    api.case(id).then(setCase).catch((e) => setError(e.message))
  }, [id])

  async function run<T>(fn: () => Promise<CaseDetail>, after?: () => T) {
    setError(null)
    try {
      setCase(await fn())
      after?.()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function audit() {
    setAuditing(true)
    await run(() => api.audit(id), () => setParams({ tab: 'audit' }))
    setAuditing(false)
  }

  if (!c) return error ? <ErrorNote error={error} /> : <Spinner label="Loading case…" />

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <Link to="/cases" className="text-xs text-violet-700 hover:underline">← Case history</Link>
          <h1 className="mt-1 text-2xl font-semibold text-navy-900">{c.title}</h1>
          <p className="text-xs text-slate-500">
            Created {new Date(c.created_at).toLocaleString()} · {c.status === 'audited' ? 'Audited' : 'Draft'}
          </p>
        </div>
        <button className={btn.primary} onClick={audit} disabled={auditing || !c.documents.settlement}>
          {auditing ? <Loader2 className="size-4 animate-spin" /> : <PlayCircle className="size-4" />}
          {c.audit ? 'Re-run audit' : 'Run audit'}
        </button>
      </div>
      {c.demo && <DemoBanner />}
      <ErrorNote error={error} />

      <nav className="flex gap-1 border-b border-slate-200" aria-label="Case sections">
        {TABS.map(([key, label]) => (
          <button
            key={key}
            onClick={() => setParams({ tab: key })}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
              tab === key ? 'border-violet-brand text-navy-900' : 'border-transparent text-slate-500 hover:text-navy-900'
            }`}
          >
            {label}
          </button>
        ))}
      </nav>

      {tab === 'review' && (
        <div className="space-y-6">
          {!c.documents.settlement && (
            <p className="text-sm text-slate-600">Upload the settlement letter to run the audit: it lists the deductions to check.</p>
          )}
          {DOC_ORDER.map((t) => (
            <DocumentCard key={t} c={c} docType={t} onChange={(fn) => run(fn)} />
          ))}
        </div>
      )}

      {tab === 'audit' &&
        (c.audit ? (
          <AuditView key={c.audit.generated_at} audit={c.audit} clauses={c.documents.policy?.data.clauses ?? []} />
        ) : (
          <Card><p className="text-sm text-slate-600">No current audit. Review the extracted data, then run the audit.</p></Card>
        ))}

      {tab === 'appeal' && <AppealTab c={c} onSave={(text) => run(() => api.saveAppeal(id, text))} />}
    </div>
  )
}

function DocumentCard({ c, docType, onChange }: {
  c: CaseDetail
  docType: DocType
  onChange: (fn: () => Promise<CaseDetail>) => Promise<void>
}) {
  const [provider, setProvider] = useState<Provider['id']>('local')
  const [uploading, setUploading] = useState(false)
  const doc = c.documents[docType]

  async function upload(file: File | undefined) {
    if (!file) return
    setUploading(true)
    await onChange(() => api.upload(c.id, docType, file, provider))
    setUploading(false)
  }

  const save = (data: unknown) => onChange(() => api.correct(c.id, docType, data))
  const editorKey = `${doc?.filename}-${doc?.provenance.provider}-${c.audit?.generated_at}`

  return (
    <Card
      title={DOC_LABELS[docType]}
      action={
        <div className="flex flex-wrap items-center gap-2">
          <div className="w-56"><ProviderSelect value={provider} onChange={setProvider} /></div>
          <label className={`${btn.secondary} cursor-pointer py-1.5`}>
            {uploading ? <Loader2 className="size-4 animate-spin" /> : <FileUp className="size-4" />}
            {doc ? 'Replace' : 'Upload'}
            <input type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.txt" className="sr-only" disabled={uploading}
              onChange={(e) => upload(e.target.files?.[0])} />
          </label>
        </div>
      }
    >
      {!doc ? (
        <p className="text-sm text-slate-500">Not uploaded.</p>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <ProvenanceBadges p={doc.provenance} />
            <span className="text-xs text-slate-500">{doc.filename}</span>
          </div>
          {doc.provenance.warnings.length > 0 && (
            <ul className="list-disc rounded-lg bg-amber-50 py-2 pl-7 pr-3 text-xs text-amber-900">
              {doc.provenance.warnings.map((w) => <li key={w}>{w}</li>)}
            </ul>
          )}
          {docType === 'bill' && c.documents.bill && <BillEditor key={editorKey} value={c.documents.bill.data} text={doc.text} onSave={save} />}
          {docType === 'policy' && c.documents.policy && <PolicyEditor key={editorKey} value={c.documents.policy.data} text={doc.text} onSave={save} />}
          {docType === 'settlement' && c.documents.settlement && <SettlementEditor key={editorKey} value={c.documents.settlement.data} text={doc.text} onSave={save} />}
        </div>
      )}
    </Card>
  )
}

function AppealTab({ c, onSave }: { c: CaseDetail; onSave: (text: string) => Promise<void> }) {
  const [text, setText] = useState(c.appeal?.text ?? '')
  const [saving, setSaving] = useState(false)
  if (!c.appeal || !c.audit)
    return <Card><p className="text-sm text-slate-600">Run the audit first; the letter is drafted from its findings.</p></Card>
  const dirty = text !== c.appeal.text

  return (
    <Card
      title="Appeal letter"
      action={
        <div className="flex flex-wrap gap-2">
          <a className={btn.secondary} href={api.exportUrl(c.id, 'report')}><Download className="size-4" /> Audit report PDF</a>
          <a className={`${btn.secondary} ${dirty ? 'pointer-events-none opacity-50' : ''}`} href={api.exportUrl(c.id, 'appeal')} aria-disabled={dirty}>
            <Download className="size-4" /> Letter PDF
          </a>
        </div>
      }
    >
      <p className="mb-3 text-xs text-slate-500">
        {c.appeal.source}{c.appeal.edited ? ' · edited by you' : ''}. Check every figure and add your details before
        sending. Save changes before exporting.
      </p>
      <Field label="Letter text">
        <textarea className={`${input} h-[32rem] font-mono text-xs leading-relaxed`} value={text} onChange={(e) => setText(e.target.value)} />
      </Field>
      <div className="mt-3 flex justify-end">
        <button className={btn.primary} disabled={!dirty || saving}
          onClick={async () => { setSaving(true); await onSave(text); setSaving(false) }}>
          <Save className="size-4" /> {saving ? 'Saving…' : 'Save letter'}
        </button>
      </div>
    </Card>
  )
}
