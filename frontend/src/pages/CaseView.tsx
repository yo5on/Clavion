import { ArrowRight, Check, ChevronLeft, FileUp, Loader2, PlayCircle, RotateCcw, Save, Upload } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api, DOC_LABELS, type CaseDetail, type DocType, type Provider } from '../api'
import AuditView from '../components/AuditView'
import { BillEditor, PolicyEditor, SettlementEditor } from '../components/ReviewForms'
import {
  Card,
  ConfirmDialog,
  DemoBanner,
  DemoTag,
  EmptyState,
  ErrorNote,
  PdfButton,
  ProvenanceBadges,
  Skeleton,
  btn,
  eyebrow,
  useToast,
} from '../components/ui'
import { CaseStatus } from './Cases'
import { FileDrop, FilePick, ProviderSelect } from './NewAudit'

type Tab = 'review' | 'audit' | 'appeal'
const DOC_ORDER: DocType[] = ['bill', 'policy', 'settlement']
type Run = (fn: () => Promise<CaseDetail>, success?: string) => Promise<boolean>

export default function CaseView() {
  const { id = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const tab = (params.get('tab') as Tab) || 'review'
  const [c, setCase] = useState<CaseDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [auditing, setAuditing] = useState(false)
  const toast = useToast()

  useEffect(() => {
    api.case(id).then(setCase).catch((e) => setError(e.message))
  }, [id])

  const run: Run = async (fn, success) => {
    try {
      setCase(await fn())
      if (success) toast('success', success)
      return true
    } catch (e) {
      toast('error', (e as Error).message)
      return false
    }
  }

  async function audit() {
    setAuditing(true)
    if (await run(() => api.audit(id), 'Audit complete. Findings are ready.')) setParams({ tab: 'audit' })
    setAuditing(false)
  }

  const go = (t: Tab) => {
    setParams({ tab: t })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  if (!c)
    return error ? (
      <div className="space-y-4">
        <Link to="/cases" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-navy-900"><ChevronLeft className="size-4" /> Case history</Link>
        <ErrorNote error={error} />
      </div>
    ) : (
      <div className="space-y-4" aria-busy>
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-8 w-80 max-w-full" />
        <Skeleton className="h-16" />
        <Skeleton className="h-64" />
      </div>
    )

  const docCount = DOC_ORDER.filter((t) => c.documents[t]).length
  const steps: { key: Tab; label: string; short: string; note: string; done: boolean }[] = [
    { key: 'review', label: 'Review extraction', short: 'Review', note: `${docCount} of 3 documents`, done: docCount > 0 && !!c.documents.settlement },
    { key: 'audit', label: 'Audit findings', short: 'Audit', note: c.audit ? `${c.audit.findings.length} findings` : 'Not run yet', done: !!c.audit },
    { key: 'appeal', label: 'Appeal & export', short: 'Appeal', note: c.appeal ? (c.appeal.edited ? 'Edited draft' : 'Draft ready') : 'After the audit', done: !!c.appeal?.edited },
  ]

  return (
    <div className="space-y-6">
      <header className="space-y-4 border-b border-line pb-6">
        <Link to="/cases" className="inline-flex items-center gap-1 text-sm text-slate-500 transition-colors hover:text-navy-900">
          <ChevronLeft className="size-4" /> Case history
        </Link>
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="min-w-0">
            <h1 className="font-serif text-[1.75rem] font-semibold leading-tight tracking-[-0.01em]">{c.title}</h1>
            <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
              <CaseStatus c={{ status: c.status, documents: DOC_ORDER.filter((t) => c.documents[t]) }} />
              <span>Opened {new Date(c.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</span>
              {c.demo && <DemoTag />}
            </p>
          </div>
          <div className="flex flex-col items-start gap-1.5 md:items-end">
            <button className={btn.primary} onClick={audit} disabled={auditing || !c.documents.settlement}>
              {auditing ? <Loader2 className="size-4 animate-spin" /> : <PlayCircle className="size-4" />}
              {auditing ? 'Auditing…' : c.audit ? 'Re-run audit' : 'Run audit'}
            </button>
            {!c.documents.settlement && <span className="text-xs text-slate-500">Upload the settlement letter to enable</span>}
          </div>
        </div>
      </header>
      {c.demo && <DemoBanner />}

      <nav aria-label="Case workflow">
        <ol className="grid grid-cols-3 overflow-hidden rounded-lg border border-line bg-white">
          {steps.map((s, i) => {
            const active = tab === s.key
            return (
              <li key={s.key} className="border-l border-line first:border-l-0">
                <button
                  onClick={() => go(s.key)}
                  aria-current={active ? 'step' : undefined}
                  className={`relative flex h-full w-full items-center gap-3 px-3 py-3 text-left transition-colors sm:px-4 ${
                    active ? 'bg-white after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 after:bg-violet-600' : 'bg-slate-50/70 hover:bg-white'
                  }`}
                >
                  <span className={`hidden size-6 shrink-0 items-center justify-center rounded-full font-mono text-xs sm:flex ${
                    s.done ? 'bg-navy-900 text-white' : active ? 'border border-violet-600 text-violet-700' : 'border border-slate-300 text-slate-500'
                  }`}>
                    {s.done ? <Check className="size-3.5" /> : i + 1}
                  </span>
                  <span className="min-w-0">
                    <span className={`block truncate text-sm font-medium ${active ? 'text-navy-900' : 'text-slate-600'}`}>
                      <span className="sm:hidden">{s.short}</span>
                      <span className="hidden sm:inline">{s.label}</span>
                    </span>
                    <span className="block truncate text-xs text-slate-500">{s.note}</span>
                  </span>
                </button>
              </li>
            )
          })}
        </ol>
      </nav>

      {tab === 'review' && (
        <div className="space-y-6">
          {DOC_ORDER.map((t) => (
            <DocumentCard key={t} c={c} docType={t} run={run} />
          ))}
          <div className="flex flex-col items-start justify-between gap-3 rounded-lg border border-line bg-white px-5 py-4 sm:flex-row sm:items-center">
            <p className="text-sm text-slate-600">
              <span className="font-medium text-navy-900">Next:</span>{' '}
              {c.documents.settlement
                ? c.audit ? 'the audit reflects the data above.' : 'once the fields look right, run the audit.'
                : 'upload the settlement letter: it lists the deductions to check.'}
            </p>
            {c.audit ? (
              <button className={btn.secondary} onClick={() => go('audit')}>View findings <ArrowRight className="size-4" /></button>
            ) : (
              <button className={btn.primary} onClick={audit} disabled={auditing || !c.documents.settlement}>
                {auditing ? <Loader2 className="size-4 animate-spin" /> : <PlayCircle className="size-4" />} Run audit
              </button>
            )}
          </div>
        </div>
      )}

      {tab === 'audit' &&
        (c.audit ? (
          <AuditView key={c.audit.generated_at} audit={c.audit} clauses={c.documents.policy?.data.clauses ?? []} caseId={c.id} onNext={() => go('appeal')} />
        ) : (
          <Card>
            <EmptyState icon={PlayCircle} title="No current audit"
              actions={
                <>
                  <button className={btn.secondary} onClick={() => go('review')}>Review documents</button>
                  <button className={btn.primary} onClick={audit} disabled={auditing || !c.documents.settlement}>Run audit</button>
                </>
              }>
              Review the extracted data, then run the audit. Correcting or replacing a document clears the previous audit.
            </EmptyState>
          </Card>
        ))}

      {tab === 'appeal' && <AppealTab c={c} onSave={(text) => run(() => api.saveAppeal(id, text), 'Appeal letter saved.')} onAudit={() => go('audit')} />}
    </div>
  )
}

function DocumentCard({ c, docType, run }: { c: CaseDetail; docType: DocType; run: Run }) {
  const [provider, setProvider] = useState<Provider['id']>('local')
  const [uploading, setUploading] = useState(false)
  const [pending, setPending] = useState<{ ok: () => void; cancel: () => void } | null>(null)
  const doc = c.documents[docType]
  const label = DOC_LABELS[docType]

  // Corrections and re-uploads clear the audit and appeal on the server; confirm before discarding them.
  const guard = (fn: () => Promise<unknown>) =>
    !c.audit
      ? fn().then(() => {})
      : new Promise<void>((resolve) =>
          setPending({
            ok: () => { setPending(null); fn().finally(resolve) },
            cancel: () => { setPending(null); resolve() },
          }),
        )

  const upload = (file: File) =>
    guard(async () => {
      setUploading(true)
      await run(() => api.upload(c.id, docType, file, provider), `${label} extracted. Check the fields below.`)
      setUploading(false)
    })

  const save = (data: unknown) =>
    guard(() => run(() => api.correct(c.id, docType, data), c.audit ? `${label} saved. Run the audit again to update the findings.` : `${label} corrections saved.`))
  const editorKey = `${doc?.filename}-${doc?.provenance.provider}-${c.audit?.generated_at}`

  return (
    <Card
      flush
      title={
        <span className="flex flex-wrap items-baseline gap-x-2">
          {label}
          {doc && <span className="max-w-[16rem] truncate font-mono text-xs font-normal text-slate-500">{doc.filename}</span>}
        </span>
      }
      action={
        <div className="flex flex-wrap items-center gap-2">
          <ProviderSelect value={provider} onChange={setProvider} className="h-8 w-48 rounded-md border border-line bg-white px-2 text-xs text-slate-700 hover:border-slate-300 focus:border-violet-500 focus:outline-none" />
          <FilePick disabled={uploading} onFile={upload} className={`${btn.secondary} h-8 px-3`}
            label={<>{uploading ? <Loader2 className="size-4 animate-spin" /> : <FileUp className="size-4" />} {doc ? 'Replace' : 'Upload'}</>} />
        </div>
      }
    >
      {!doc ? (
        <FileDrop onFile={upload} disabled={uploading}>
          {(dragging) => (
            <div className="flex flex-col items-center gap-2 px-5 py-10 text-center">
              {uploading ? <Loader2 className="size-5 animate-spin text-violet-600" /> : <Upload className="size-5 text-slate-400" />}
              <p className="text-sm text-slate-600">
                {uploading ? 'Extracting…' : dragging ? 'Drop to upload' : `No ${label.toLowerCase()} yet. Drop a file here or use Upload.`}
              </p>
            </div>
          )}
        </FileDrop>
      ) : (
        <div className="p-5">
          <div className="mb-5 flex flex-wrap items-center gap-2">
            <span className={eyebrow}>Source</span>
            <ProvenanceBadges p={doc.provenance} />
          </div>
          {doc.provenance.warnings.length > 0 && (
            <ul className="mb-5 list-disc space-y-0.5 rounded-md border border-amber-300/70 bg-amber-50 py-2 pl-8 pr-3 text-sm text-amber-900">
              {doc.provenance.warnings.map((w) => <li key={w}>{w}</li>)}
            </ul>
          )}
          {docType === 'bill' && c.documents.bill && <BillEditor key={editorKey} value={c.documents.bill.data} text={doc.text} onSave={save} />}
          {docType === 'policy' && c.documents.policy && <PolicyEditor key={editorKey} value={c.documents.policy.data} text={doc.text} onSave={save} />}
          {docType === 'settlement' && c.documents.settlement && <SettlementEditor key={editorKey} value={c.documents.settlement.data} text={doc.text} onSave={save} />}
        </div>
      )}
      <ConfirmDialog open={!!pending} title="Clear the current audit?" confirmLabel="Continue"
        onConfirm={() => pending?.ok()} onCancel={() => pending?.cancel()}>
        Changing the {label.toLowerCase()} clears the current audit findings and the appeal letter
        {c.appeal?.edited ? ', including your edits to it' : ''}. You can run the audit again afterwards.
      </ConfirmDialog>
    </Card>
  )
}

function AppealTab({ c, onSave, onAudit }: { c: CaseDetail; onSave: (text: string) => Promise<boolean>; onAudit: () => void }) {
  const [text, setText] = useState(c.appeal?.text ?? '')
  const [saving, setSaving] = useState(false)
  if (!c.appeal || !c.audit)
    return (
      <Card>
        <EmptyState icon={FileUp} title="No appeal letter yet" actions={<button className={btn.primary} onClick={onAudit}>Go to audit</button>}>
          The letter is drafted from the audit findings. Run the audit first.
        </EmptyState>
      </Card>
    )
  const dirty = text !== c.appeal.text
  const words = text.trim() ? text.trim().split(/\s+/).length : 0
  const save = async () => {
    setSaving(true)
    await onSave(text)
    setSaving(false)
  }

  return (
    <div className="grid items-start gap-6 lg:grid-cols-12">
      <Card flush className="lg:col-span-8"
        title="Appeal letter"
        action={<span className="text-xs text-slate-500">{c.appeal.source}{c.appeal.edited ? ' · edited by you' : ''}</span>}>
        <textarea
          aria-label="Appeal letter text"
          className="block min-h-[36rem] w-full resize-y border-0 bg-white px-5 py-6 font-serif text-[15px] leading-7 text-slate-800 focus:outline-none sm:px-10 sm:py-8"
          value={text}
          spellCheck
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 's') {
              e.preventDefault()
              if (dirty && !saving) save()
            }
          }}
        />
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-b-lg border-t border-line bg-slate-50/70 px-5 py-3">
          <span className="flex items-center gap-3 text-xs text-slate-500">
            <span className="tabular-nums">{words} words</span>
            {dirty && (
              <span className="flex items-center gap-1.5 font-medium text-amber-700">
                <span className="size-1.5 rounded-full bg-amber-500" /> Unsaved changes
              </span>
            )}
          </span>
          <span className="flex gap-2">
            {dirty && (
              <button className={btn.secondary} onClick={() => setText(c.appeal!.text)} disabled={saving}>
                <RotateCcw className="size-4" /> Revert
              </button>
            )}
            <button className={btn.primary} disabled={!dirty || saving} onClick={save} title="Ctrl+S">
              <Save className="size-4" /> {saving ? 'Saving…' : 'Save letter'}
            </button>
          </span>
        </div>
      </Card>

      <div className="space-y-6 lg:sticky lg:top-6 lg:col-span-4">
        <Card title="Export">
          <ul className="divide-y divide-line">
            <li className="pb-4">
              <p className="text-sm font-medium text-navy-900">Audit report</p>
              <p className="mt-0.5 text-xs leading-relaxed text-slate-500">Reconciliation, every finding and its evidence.</p>
              <PdfButton href={api.exportUrl(c.id, 'report')} className={`${btn.secondary} mt-2.5 w-full`}>Download PDF</PdfButton>
            </li>
            <li className="pt-4">
              <p className="text-sm font-medium text-navy-900">Appeal letter</p>
              <p className="mt-0.5 text-xs leading-relaxed text-slate-500">The saved version of the letter on the left.</p>
              <PdfButton href={api.exportUrl(c.id, 'appeal')} disabled={dirty} className={`${btn.primary} mt-2.5 w-full`}
                title={dirty ? 'Save your changes first' : undefined}>
                Download PDF
              </PdfButton>
              {dirty && <p className="mt-1.5 text-xs text-amber-700">Save your changes to include them in the PDF.</p>}
            </li>
          </ul>
        </Card>
        <Card title="Before you send">
          <ul className="space-y-2 text-sm text-slate-600">
            {['Check every figure against your own documents.', 'Add your contact details, signature and date.', 'Attach the bill, policy and settlement letter.'].map((t) => (
              <li key={t} className="flex gap-2"><Check className="mt-0.5 size-4 shrink-0 text-slate-400" /> {t}</li>
            ))}
          </ul>
          {c.demo && <p className="mt-4 text-xs text-amber-800">This is a demo letter built from synthetic documents. Do not send it.</p>}
        </Card>
      </div>
    </div>
  )
}
