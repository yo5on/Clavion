import { ArrowRight, Check, ChevronLeft, FileText, Loader2, PenLine, RotateCcw, Scale, Upload } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api, DOC_LABELS, type CaseDetail, type DocType, type Provider } from '../api'
import AuditView from '../components/AuditView'
import { BillEditor, PolicyEditor, SettlementEditor } from '../components/ReviewForms'
import {
  ConfirmDialog,
  DemoBanner,
  DemoTag,
  EmptyState,
  ErrorNote,
  PdfButton,
  ProvenanceBadges,
  Skeleton,
  btn,
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

  const back = (
    <Link to="/cases" className="-ml-1 inline-flex items-center gap-0.5 rounded-sm text-sm text-mute transition-colors hover:text-ink">
      <ChevronLeft className="size-4" /> Case history
    </Link>
  )

  if (!c)
    return error ? (
      <div className="space-y-6 pt-10">
        {back}
        <ErrorNote error={error} />
      </div>
    ) : (
      <div className="space-y-6 pt-10" aria-busy>
        <Skeleton className="h-4 w-28" />
        <Skeleton className="h-12 w-[28rem] max-w-full" />
        <Skeleton className="h-5 w-64" />
        <Skeleton className="mt-10 h-80 rounded-[28px]" />
      </div>
    )

  const docCount = DOC_ORDER.filter((t) => c.documents[t]).length
  const steps: { key: Tab; label: string; note: string; done: boolean }[] = [
    { key: 'review', label: 'Review', note: `${docCount} of 3 documents`, done: docCount > 0 && !!c.documents.settlement },
    { key: 'audit', label: 'Audit', note: c.audit ? `${c.audit.findings.length} findings` : 'Not run yet', done: !!c.audit },
    { key: 'appeal', label: 'Appeal', note: c.appeal ? (c.appeal.edited ? 'Edited draft' : 'Draft ready') : 'After the audit', done: !!c.appeal?.edited },
  ]
  const runLabel = auditing ? 'Auditing…' : c.audit ? 'Re-run audit' : 'Run audit'

  return (
    <div>
      {/* Local navigation, in the manner of a product sub-nav: case name, workflow steps, the primary action. */}
      <nav aria-label="Case workflow" className="sticky top-14 z-30 bg-canvas shadow-[0_0_0_100vmax_var(--color-canvas),0_1px_0_100vmax_var(--color-hairline)] [clip-path:inset(0_-100vmax_-1px)]">
        <div className="flex h-16 items-center gap-6">
          <span className="hidden min-w-0 flex-1 truncate text-[17px] font-semibold tracking-[-0.012em] text-ink lg:block">{c.title}</span>
          <ol className="flex flex-1 items-stretch gap-1 self-stretch lg:flex-none">
            {steps.map((s, i) => {
              const active = tab === s.key
              return (
                <li key={s.key} className="flex">
                  <button
                    onClick={() => go(s.key)}
                    aria-current={active ? 'step' : undefined}
                    className={`relative flex items-center gap-2.5 px-3 text-left transition-colors duration-200 after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:rounded-full after:transition-colors after:duration-300 sm:px-4 sm:after:inset-x-4 ${
                      active ? 'text-ink after:bg-ink' : 'text-mute after:bg-transparent hover:text-ink'
                    }`}
                  >
                    <span aria-hidden className={`hidden size-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold tabular-nums sm:flex ${
                      s.done ? 'bg-ink text-white' : active ? 'ring-1 ring-inset ring-ink' : 'ring-1 ring-inset ring-faint'
                    }`}>
                      {s.done ? <Check className="size-3" strokeWidth={3} /> : i + 1}
                    </span>
                    <span className="leading-tight">
                      <span className="block text-sm font-medium">{s.label}</span>
                      <span className="hidden text-xs text-mute md:block">{s.note}</span>
                    </span>
                  </button>
                </li>
              )
            })}
          </ol>
          <button className={`${btn.primarySm} shrink-0`} onClick={audit} disabled={auditing || !c.documents.settlement}
            title={!c.documents.settlement ? 'Upload the settlement letter to enable' : undefined}>
            {auditing && <Loader2 className="size-4 animate-spin" />}
            {runLabel}
          </button>
        </div>
      </nav>

      <header className="pt-8 pb-12 sm:pt-12 sm:pb-16">
        {back}
        <h1 className="type-headline mt-4">{c.title}</h1>
        <p className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 text-[15px] text-mute">
          <CaseStatus c={{ status: c.status, documents: DOC_ORDER.filter((t) => c.documents[t]) }} />
          <span aria-hidden className="text-faint">·</span>
          <span>Opened {new Date(c.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</span>
          {c.demo && <DemoTag />}
        </p>
        {!c.documents.settlement && <p className="mt-2 text-sm text-mute">Upload the settlement letter to run the audit.</p>}
        {c.demo && <div className="mt-8"><DemoBanner /></div>}
      </header>

      <div key={tab} className="animate-page-in">
        {tab === 'review' && (
          <div className="space-y-16 sm:space-y-20">
            {DOC_ORDER.map((t) => (
              <DocumentSection key={t} c={c} docType={t} run={run} />
            ))}
            <section className="flex flex-col items-start justify-between gap-6 border-t border-hairline pt-10 sm:flex-row sm:items-center">
              <div>
                <p className="type-heading">
                  {c.documents.settlement ? (c.audit ? 'The audit reflects the data above.' : 'Ready when you are.') : 'One document to go.'}
                </p>
                <p className="mt-1 text-[15px] text-mute">
                  {c.documents.settlement
                    ? c.audit ? 'Correcting a document clears the audit so it can be run again.' : 'Once the fields look right, run the audit.'
                    : 'Upload the settlement letter: it lists the deductions to check.'}
                </p>
              </div>
              {c.audit ? (
                <button className={btn.secondary} onClick={() => go('audit')}>View findings <ArrowRight className="size-4" /></button>
              ) : (
                <button className={btn.primary} onClick={audit} disabled={auditing || !c.documents.settlement}>
                  {auditing && <Loader2 className="size-4 animate-spin" />} {auditing ? 'Auditing…' : 'Run audit'}
                </button>
              )}
            </section>
          </div>
        )}

        {tab === 'audit' &&
          (c.audit ? (
            <AuditView key={c.audit.generated_at} audit={c.audit} clauses={c.documents.policy?.data.clauses ?? []} caseId={c.id} onNext={() => go('appeal')} />
          ) : (
            <EmptyState icon={Scale} title="No current audit"
              actions={
                <>
                  <button className={btn.primary} onClick={audit} disabled={auditing || !c.documents.settlement}>Run audit</button>
                  <button className={btn.link} onClick={() => go('review')}>Review documents</button>
                </>
              }>
              Review the extracted data, then run the audit. Correcting or replacing a document clears the previous audit.
            </EmptyState>
          ))}

        {tab === 'appeal' && <AppealTab c={c} onSave={(text) => run(() => api.saveAppeal(id, text), 'Appeal letter saved.')} onAudit={() => go('audit')} />}
      </div>
    </div>
  )
}

function DocumentSection({ c, docType, run }: { c: CaseDetail; docType: DocType; run: Run }) {
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
    <section aria-labelledby={`doc-${docType}`} className="border-t border-hairline pt-10 first:border-t-0 first:pt-0">
      <header className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <h2 id={`doc-${docType}`} className="type-title">{label}</h2>
          {doc && (
            <div className="mt-2.5 space-y-1">
              <p className="flex min-w-0 items-center gap-2 text-sm text-mute">
                <FileText aria-hidden className="size-4 shrink-0" strokeWidth={1.75} />
                <span className="truncate">{doc.filename}</span>
              </p>
              <ProvenanceBadges p={doc.provenance} />
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <ProviderSelect value={provider} onChange={setProvider}
            className="h-9 w-56 rounded-full border border-hairline-strong bg-paper px-3.5 text-sm text-ink-2 transition-colors hover:border-faint focus:border-accent-fill focus:outline-none focus:ring-1 focus:ring-accent-fill" />
          <FilePick disabled={uploading} onFile={upload} className={btn.secondarySm}
            label={<>{uploading ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" strokeWidth={1.75} />} {doc ? 'Replace' : 'Upload'}</>} />
        </div>
      </header>

      <div className="mt-8">
        {!doc ? (
          <FileDrop onFile={upload} disabled={uploading} className="rounded-[28px] bg-tile">
            {(dragging) => (
              <div className="flex flex-col items-center gap-3 px-6 py-16 text-center">
                {uploading ? <Loader2 className="size-7 animate-spin text-mute" /> : <Upload className="size-7 text-faint" strokeWidth={1.25} />}
                <p className="text-[17px] text-ink-2">
                  {uploading ? 'Reading the document…' : dragging ? 'Drop to upload.' : `Drop the ${label.toLowerCase()} here.`}
                </p>
                {!uploading && !dragging && (
                  <FilePick onFile={upload} className={btn.link} label={<>or choose a file</>} />
                )}
              </div>
            )}
          </FileDrop>
        ) : (
          <>
            {doc.provenance.warnings.length > 0 && (
              <ul className="mb-8 list-disc space-y-1 rounded-2xl bg-caution-soft py-3.5 pl-9 pr-4 text-[15px] text-ink-2">
                {doc.provenance.warnings.map((w) => <li key={w}>{w}</li>)}
              </ul>
            )}
            {docType === 'bill' && c.documents.bill && <BillEditor key={editorKey} value={c.documents.bill.data} text={doc.text} onSave={save} />}
            {docType === 'policy' && c.documents.policy && <PolicyEditor key={editorKey} value={c.documents.policy.data} text={doc.text} onSave={save} />}
            {docType === 'settlement' && c.documents.settlement && <SettlementEditor key={editorKey} value={c.documents.settlement.data} text={doc.text} onSave={save} />}
          </>
        )}
      </div>
      <ConfirmDialog open={!!pending} title="Clear the current audit?" confirmLabel="Continue"
        onConfirm={() => pending?.ok()} onCancel={() => pending?.cancel()}>
        Changing the {label.toLowerCase()} clears the current audit findings and the appeal letter
        {c.appeal?.edited ? ', including your edits to it' : ''}. You can run the audit again afterwards.
      </ConfirmDialog>
    </section>
  )
}

function AppealTab({ c, onSave, onAudit }: { c: CaseDetail; onSave: (text: string) => Promise<boolean>; onAudit: () => void }) {
  const [text, setText] = useState(c.appeal?.text ?? '')
  const [saving, setSaving] = useState(false)
  if (!c.appeal || !c.audit)
    return (
      <EmptyState icon={PenLine} title="No appeal letter yet" actions={<button className={btn.primary} onClick={onAudit}>Go to audit</button>}>
        The letter is drafted from the audit findings. Run the audit first.
      </EmptyState>
    )
  const dirty = text !== c.appeal.text
  const words = text.trim() ? text.trim().split(/\s+/).length : 0
  const save = async () => {
    setSaving(true)
    await onSave(text)
    setSaving(false)
  }

  return (
    <div className="grid items-start gap-12 lg:grid-cols-12 lg:gap-14">
      <div className="lg:col-span-8">
        <div className="rounded-[32px] bg-tile p-2 sm:p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-4 pt-3 pb-4 sm:px-5">
            <h2 className="text-[15px] font-semibold text-ink">Appeal letter</h2>
            <span className="text-[13px] text-mute">{c.appeal.source}{c.appeal.edited ? ' · edited by you' : ''}</span>
          </div>
          <textarea
            aria-label="Appeal letter text"
            className="block min-h-[40rem] w-full resize-y rounded-[22px] border-0 bg-paper px-6 py-8 text-[16px] leading-[1.75] text-ink shadow-[0_1px_3px_rgb(0_0_0/0.06)] focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-fill sm:px-14 sm:py-14"
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
          <div className="flex flex-wrap items-center justify-between gap-3 px-3 pt-4 pb-2 sm:px-4">
            <span className="flex items-center gap-4 text-[13px] text-mute">
              <span className="tabular-nums">{words} words</span>
              {dirty && (
                <span className="flex animate-fade-in items-center gap-2 font-medium text-caution">
                  <span aria-hidden className="size-1.5 rounded-full bg-caution-fill" /> Unsaved changes
                </span>
              )}
            </span>
            <span className="flex items-center gap-3">
              {dirty && (
                <button className={btn.secondarySm} onClick={() => setText(c.appeal!.text)} disabled={saving}>
                  <RotateCcw className="size-3.5" /> Revert
                </button>
              )}
              <button className={btn.primarySm} disabled={!dirty || saving} onClick={save} title="Ctrl+S">
                {saving ? 'Saving…' : 'Save letter'}
              </button>
            </span>
          </div>
        </div>
      </div>

      <aside className="space-y-12 lg:sticky lg:top-36 lg:col-span-4">
        <section>
          <h2 className="type-heading">Export</h2>
          <ul className="mt-4 divide-y divide-hairline border-y border-hairline">
            <li className="py-5">
              <p className="text-[15px] font-medium text-ink">Audit report</p>
              <p className="mt-1 text-sm leading-relaxed text-mute">Reconciliation, every finding and its evidence.</p>
              <PdfButton href={api.exportUrl(c.id, 'report')} className={`${btn.secondarySm} mt-4`}>Download PDF</PdfButton>
            </li>
            <li className="py-5">
              <p className="text-[15px] font-medium text-ink">Appeal letter</p>
              <p className="mt-1 text-sm leading-relaxed text-mute">The saved version of the letter.</p>
              <PdfButton href={api.exportUrl(c.id, 'appeal')} disabled={dirty} className={`${btn.primarySm} mt-4`}
                title={dirty ? 'Save your changes first' : undefined}>
                Download PDF
              </PdfButton>
              {dirty && <p className="mt-2 text-[13px] text-caution">Save your changes to include them in the PDF.</p>}
            </li>
          </ul>
        </section>
        <section>
          <h2 className="type-heading">Before you send</h2>
          <ul className="mt-4 space-y-3 text-[15px] text-ink-2">
            {['Check every figure against your own documents.', 'Add your contact details, signature and date.', 'Attach the bill, policy and settlement letter.'].map((t) => (
              <li key={t} className="flex gap-3"><Check aria-hidden className="mt-1 size-4 shrink-0 text-faint" strokeWidth={2} /> {t}</li>
            ))}
          </ul>
          {c.demo && <p className="mt-5 text-sm text-caution">This is a demo letter built from synthetic documents. Do not send it.</p>}
        </section>
      </aside>
    </div>
  )
}
