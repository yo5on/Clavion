import { AlertTriangle, ArrowRight, CheckCircle2, ChevronDown, CircleHelp, FileSearch, FileText, MinusCircle, X, XCircle } from 'lucide-react'
import { useRef, useState, type ReactNode } from 'react'
import {
  api, DOC_LABELS, rupees, where,
  type AuditReport, type CaseDetail, type Check, type DocType, type Evidence, type Finding, type FindingStatus,
} from '../api'
import DocumentViewer, { type DocTarget } from './DocumentViewer'
import { Amount, LedgerBar, PdfButton, STATUS, Section, StatusBadge, Swatch, btn, caption, panel } from './ui'

const num = (v: string | null | undefined) => Number(v ?? 0) || 0

export function SettlementSummary({ audit, filter, onFilter }: {
  audit: AuditReport
  filter?: FindingStatus | null
  onFilter?: (s: FindingStatus | null) => void
}) {
  const approved = num(audit.approved_amount)
  const totals: Record<FindingStatus, number> = {
    supported: num(audit.supported_total),
    contestable: num(audit.contestable_total),
    unverified: num(audit.unverified_total),
  }
  const base = num(audit.claimed_amount) || approved + totals.supported + totals.contestable + totals.unverified
  const pct = (v: number) => (base ? `${((v / base) * 100).toFixed(1)}%` : '')
  const figures: [string, string | null, string?][] = [
    ['Hospital bill', audit.bill_total],
    ['Claimed', audit.claimed_amount],
    ['Approved', audit.approved_amount],
    ['Paid', audit.paid_amount ?? null, audit.paid_amount == null ? 'Not stated on the letter' : undefined],
    ['Deducted', audit.total_deductions],
  ]

  return (
    <div>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-8 sm:grid-cols-3 lg:grid-cols-5">
        {figures.map(([label, v, note]) => (
          <div key={label}>
            <dt className={caption}>{label}</dt>
            <dd className="type-figure mt-1.5 text-[1.5rem] leading-tight sm:text-[1.75rem]">
              {note ? <span className="text-[15px] font-normal tracking-normal text-mute">{note}</span> : <Amount value={v} />}
            </dd>
          </div>
        ))}
      </dl>

      <LedgerBar className="mt-10 h-2.5" approved={approved} {...totals} />

      <ul className="-mx-3 mt-5 grid gap-1 sm:grid-cols-2 lg:grid-cols-4">
        <li className="flex items-start gap-3 px-3 py-2.5">
          <Swatch fill="fill-approved" className="mt-1.5" />
          <span className="min-w-0 flex-1">
            <span className="block text-sm text-mute">Approved by insurer</span>
            <Amount value={approved} className="type-figure text-[17px]" />
          </span>
          <span className="mt-0.5 text-[13px] tabular-nums text-mute">{pct(approved)}</span>
        </li>
        {(Object.keys(STATUS) as FindingStatus[]).map((s) => {
          const body = (
            <>
              <Swatch fill={STATUS[s].fill} className="mt-1.5" />
              <span className="min-w-0 flex-1 text-left">
                <span className={`block text-sm ${s === 'contestable' ? 'font-medium text-accent' : 'text-mute'}`}>{STATUS[s].label}</span>
                <Amount value={totals[s]} className={`type-figure text-[17px] ${s === 'contestable' && totals[s] > 0 ? 'text-accent!' : ''}`} />
              </span>
              <span className="mt-0.5 text-[13px] tabular-nums text-mute">{pct(totals[s])}</span>
            </>
          )
          const cls = 'flex w-full items-start gap-3 rounded-2xl px-3 py-2.5'
          return (
            <li key={s}>
              {onFilter ? (
                <button type="button" title={`${STATUS[s].meaning} Select to filter findings.`} aria-pressed={filter === s}
                  onClick={() => onFilter(filter === s ? null : s)}
                  className={`${cls} transition-[background-color,box-shadow] duration-200 hover:bg-tile ${filter === s ? 'bg-tile ring-1 ring-hairline-strong' : ''}`}>
                  {body}
                </button>
              ) : (
                <div className={cls} title={STATUS[s].meaning}>{body}</div>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export default function AuditView({ audit, documents, caseId, onNext }: {
  audit: AuditReport
  documents: CaseDetail['documents']
  caseId: string
  onNext: () => void
}) {
  const [selected, setSelected] = useState<number>(
    audit.findings.find((f) => f.status === 'contestable')?.id ?? audit.findings[0]?.id ?? 0,
  )
  const [filter, setFilter] = useState<FindingStatus | null>(null)
  const [viewing, setViewing] = useState<DocTarget | null>(null)
  const evidenceRef = useRef<HTMLDivElement>(null)
  const finding = audit.findings.find((f) => f.id === selected)
  const shown = audit.findings.filter((f) => !filter || f.status === filter)
  const contestable = num(audit.contestable_total)
  const unverified = num(audit.unverified_total)
  const clauses = documents.policy?.data.clauses ?? []
  const open = (e: Evidence) => setViewing({ docType: e.doc_type, source: e.source, label: e.ref })

  function applyFilter(s: FindingStatus | null) {
    setFilter(s)
    const first = audit.findings.find((f) => f.status === s)
    if (s && finding?.status !== s && first) setSelected(first.id)
  }

  function select(id: number) {
    setSelected(id)
    // Master and detail stack below the lg breakpoint, so bring the evidence into view.
    if (!window.matchMedia('(min-width: 1024px)').matches)
      requestAnimationFrame(() => evidenceRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }

  return (
    <div className="space-y-16 sm:space-y-20">
      <section>
        <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <div className="max-w-3xl">
            <p className="text-[15px] font-medium text-mute">Audit result</p>
            <h2 className="type-headline mt-3">
              {contestable > 0 ? (
                <><Amount value={audit.contestable_total} className="text-accent" /> may be contestable.</>
              ) : unverified > 0 ? (
                <><Amount value={audit.unverified_total} /> needs clarification.</>
              ) : (
                'Every deduction is supported.'
              )}
            </h2>
            <p className="type-lead mt-4">
              The insurer deducted {rupees(audit.total_deductions)} from a claim of {rupees(audit.claimed_amount)}.
              Clavion checked {audit.findings.length} deduction{audit.findings.length === 1 ? '' : 's'} against the policy and the bill
              {unverified > 0 && contestable > 0 ? `; ${rupees(audit.unverified_total)} needs an explanation from the insurer.` : '.'}
            </p>
          </div>
          <PdfButton href={api.exportUrl(caseId, 'report')} className={`${btn.secondary} shrink-0 self-start md:self-auto`}>Audit report</PdfButton>
        </div>

        <div className="mt-12">
          <SettlementSummary audit={audit} filter={filter} onFilter={applyFilter} />
        </div>
        <p className="mt-6 max-w-3xl text-[13px] leading-relaxed text-mute">
          {audit.method}{audit.rules_version && `, rules ${audit.rules_version}`} · generated {new Date(audit.generated_at).toLocaleString()}.
          “Potentially contestable” means the uploaded documents do not support that part of a deduction; it is not a
          guarantee of recovery and not a legal opinion.
        </p>
      </section>

      {(audit.missing_information.length > 0 || audit.documents_to_request.length > 0) && (
        <div role="note" className="grid gap-8 rounded-[28px] bg-caution-soft px-6 py-6 sm:px-8 md:grid-cols-2">
          {audit.missing_information.length > 0 && (
            <div>
              <p className="flex items-center gap-2.5 text-[17px] font-semibold text-caution">
                <AlertTriangle className="size-[18px]" strokeWidth={1.75} /> Missing or inconsistent information
              </p>
              <ul className="mt-2 list-disc space-y-1 pl-12 text-[15px] leading-relaxed text-ink-2">
                {audit.missing_information.map((m) => <li key={m}>{m}</li>)}
              </ul>
            </div>
          )}
          {audit.documents_to_request.length > 0 && (
            <div>
              <p className="flex items-center gap-2.5 text-[17px] font-semibold text-ink">
                <FileSearch className="size-[18px] text-caution" strokeWidth={1.75} /> Ask the insurer or hospital for
              </p>
              <ul className="mt-2 list-disc space-y-1 pl-12 text-[15px] leading-relaxed text-ink-2">
                {audit.documents_to_request.map((m) => <li key={m}>{m}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      <Section
        title={<>Findings <span className="font-normal text-mute">{shown.length}{filter && ` of ${audit.findings.length}`}</span></>}
        action={filter && (
          <button className={`${btn.secondarySm} gap-1.5`} onClick={() => applyFilter(null)} aria-label={`Clear filter: ${STATUS[filter].label}`}>
            {STATUS[filter].label} <X className="size-3.5" />
          </button>
        )}>
        <div className="grid items-start gap-8 lg:grid-cols-12 lg:gap-10">
          <ul className="-mx-3 space-y-1 lg:col-span-5">
            {shown.map((f) => {
              const active = f.id === selected
              return (
                <li key={f.id}>
                  <button
                    onClick={() => select(f.id)}
                    aria-current={active}
                    className={`grid w-full grid-cols-[1.5rem_minmax(0,1fr)_auto] gap-x-3 rounded-2xl px-3 py-4 text-left transition-[background-color,box-shadow] duration-200 ${
                      active ? 'bg-tile' : 'hover:bg-wash'
                    }`}
                  >
                    <span className="pt-px text-sm tabular-nums text-mute">{f.id}</span>
                    <span className="min-w-0">
                      <span className="block text-[15px] font-medium leading-snug text-ink">{f.description}</span>
                      <span className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1">
                        <StatusBadge status={f.status} />
                        <span aria-hidden className="text-faint">·</span>
                        <span className="text-[13px] text-mute">{f.category}</span>
                      </span>
                    </span>
                    <span className="text-right">
                      <Amount value={f.insurer_amount} className="type-figure text-[15px]" />
                      {num(f.contestable_amount) > 0 && (
                        <span className="mt-1 block text-[13px] font-medium text-accent">
                          <Amount value={f.contestable_amount} /> <span className="hidden font-normal sm:inline">contestable</span>
                        </span>
                      )}
                    </span>
                  </button>
                </li>
              )
            })}
            {audit.findings.length === 0 && <li className="px-3 py-10 text-[17px] text-mute">The settlement letter lists no deductions to assess.</li>}
          </ul>

          <div ref={evidenceRef} className="scroll-mt-32 lg:sticky lg:top-32 lg:col-span-7">
            {finding && <FindingDetail key={finding.id} finding={finding} total={audit.findings.length} clauses={clauses}
              documents={documents} onOpen={open} />}
          </div>
        </div>
      </Section>

      <Reconciliation audit={audit} onSelect={(id) => { setFilter(null); select(id) }} />

      <Checks checks={audit.checks ?? []} onOpen={open} />

      <section className="flex flex-col items-start justify-between gap-8 border-t border-hairline pt-10 lg:flex-row">
        <div className="max-w-2xl">
          <p className="type-heading">Appeal readiness</p>
          {audit.readiness ? (
            <>
              <p className="mt-1 text-[15px] text-ink-2">{audit.readiness.summary}</p>
              <ul className="mt-4 space-y-2">
                {audit.readiness.items.map((i) => (
                  <li key={i.label} className="flex gap-3 text-[15px]">
                    {i.ok ? <CheckCircle2 aria-label="Met" className="mt-0.5 size-4 shrink-0 text-ok" /> : <XCircle aria-label="Not met" className="mt-0.5 size-4 shrink-0 text-caution" />}
                    <span>
                      <span className="text-ink">{i.label}</span>
                      {!i.ok && i.detail && <span className="mt-0.5 block text-sm text-mute">{i.detail}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="mt-1 text-[15px] text-mute">Run the audit again to assess readiness.</p>
          )}
        </div>
        <div className="shrink-0">
          <p className="text-[15px] text-mute">The draft is built from these findings. Review every statement before sending.</p>
          <button className={`${btn.primary} mt-4`} onClick={onNext}>Continue to appeal <ArrowRight className="size-4" /></button>
        </div>
      </section>

      <DocumentViewer target={viewing} onClose={() => setViewing(null)}
        text={viewing ? documents[viewing.docType]?.text : undefined}
        filename={viewing ? documents[viewing.docType]?.filename : undefined} />
    </div>
  )
}

/** Claimed amount down to approved, line by line, so every rupee of the reduction is accounted for. */
function Reconciliation({ audit, onSelect }: { audit: AuditReport; onSelect: (id: number) => void }) {
  const rec = audit.checks?.find((c) => c.id === 'C-REC-01')
  const claim = audit.checks?.find((c) => c.id === 'C-REC-05')
  const row = 'grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-6 py-3'
  return (
    <Section title="Reconciliation">
      <p className="-mt-2 mb-6 max-w-2xl text-[15px] text-mute">From the amount claimed to the amount approved. Select a deduction to see its finding.</p>
      <div className="max-w-3xl">
        <div className={`${row} text-[15px] text-mute`}>
          <span>Hospital bill, sum of lines</span>
          <Amount value={audit.bill_total} className="tabular-nums" />
        </div>
        {claim?.status === 'failed' && <p className="-mt-1 pb-2 text-[13px] text-caution">{claim.detail}</p>}
        <div className={`${row} border-t border-hairline-strong text-[15px] font-medium text-ink`}>
          <span>Amount claimed</span>
          <Amount value={audit.claimed_amount} className="type-figure text-[17px]" />
        </div>
        <ul className="divide-y divide-hairline border-y border-hairline">
          {audit.findings.map((f) => (
            <li key={f.id}>
              <button onClick={() => onSelect(f.id)} className={`${row} -mx-3 w-[calc(100%+1.5rem)] rounded-xl px-3 text-left transition-colors hover:bg-wash`}>
                <span className="min-w-0">
                  <span className="text-[15px] text-ink-2"><span aria-hidden className="mr-2 text-faint">−</span>{f.description}</span>
                  <span className="mt-1 flex flex-wrap items-center gap-x-2 pl-5">
                    <StatusBadge status={f.status} />
                    {num(f.contestable_amount) > 0 && <span className="text-[13px] text-accent">· <Amount value={f.contestable_amount} /> contestable</span>}
                  </span>
                </span>
                <Amount value={f.insurer_amount} className="tabular-nums text-[15px]" />
              </button>
            </li>
          ))}
        </ul>
        <div className={`${row} text-[15px] font-medium text-ink`}>
          <span>Amount approved</span>
          <Amount value={audit.approved_amount} className="type-figure text-[17px]" />
        </div>
        {audit.paid_amount != null && (
          <div className={`${row} border-t border-hairline text-[15px] text-ink-2`}>
            <span>Amount paid</span>
            <Amount value={audit.paid_amount} className="tabular-nums" />
          </div>
        )}
        {rec && (
          <p className={`mt-2 flex items-start gap-2 text-[13px] ${rec.status === 'passed' ? 'text-ok' : rec.status === 'failed' ? 'text-caution' : 'text-mute'}`}>
            {rec.status === 'passed' ? <CheckCircle2 className="mt-px size-3.5 shrink-0" /> : <AlertTriangle className="mt-px size-3.5 shrink-0" />}
            {rec.detail}
          </p>
        )}
      </div>
    </Section>
  )
}

const CHECK_ICON = {
  failed: [XCircle, 'text-caution', 'Failed'],
  passed: [CheckCircle2, 'text-ok', 'Passed'],
  not_checked: [MinusCircle, 'text-faint', 'Not checked'],
} as const

function CheckRow({ c, onOpen }: { c: Check; onOpen: (e: Evidence) => void }) {
  const [Icon, cls, label] = CHECK_ICON[c.status]
  return (
    <li className="grid grid-cols-[1.25rem_minmax(0,1fr)] gap-3 py-3.5">
      <Icon aria-label={label} className={`mt-0.5 size-4 ${cls}`} strokeWidth={2} />
      <div className="min-w-0">
        <p className="text-[15px] text-ink">{c.title} <span className="ml-1 text-[13px] tabular-nums text-faint">{c.id}</span></p>
        <p className="mt-0.5 text-sm leading-relaxed text-mute">{c.detail}</p>
        {c.evidence.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {c.evidence.map((e, i) => (
              <button key={i} className={btn.linkSm} onClick={() => onOpen(e)}>{e.ref}{e.source && ` (${where(e.source)})`}</button>
            ))}
          </div>
        )}
      </div>
    </li>
  )
}

function Checks({ checks, onOpen }: { checks: Check[]; onOpen: (e: Evidence) => void }) {
  if (checks.length === 0) return null
  const failed = checks.filter((c) => c.status === 'failed')
  const rest = checks.filter((c) => c.status !== 'failed')
  const passed = rest.filter((c) => c.status === 'passed').length
  return (
    <Section title={<>Consistency checks <span className="font-normal text-mute">{failed.length ? `${failed.length} need attention` : 'no problems found'}</span></>}>
      <p className="-mt-2 mb-4 max-w-2xl text-[15px] text-mute">Cross-checks between the bill, the policy and the settlement letter. A failed check is a question to raise, not proof of an error.</p>
      {failed.length > 0 && <ul className="max-w-3xl divide-y divide-hairline">{failed.map((c) => <CheckRow key={c.id} c={c} onOpen={onOpen} />)}</ul>}
      <details className="group mt-2 max-w-3xl border-y border-hairline">
        <summary className="flex cursor-pointer list-none items-center justify-between py-3.5 text-[15px] text-ink-2">
          {passed} passed · {rest.length - passed} not checked
          <ChevronDown aria-hidden className="size-4 text-mute transition-transform duration-300 group-open:rotate-180" />
        </summary>
        <ul className="divide-y divide-hairline border-t border-hairline">{rest.map((c) => <CheckRow key={c.id} c={c} onOpen={onOpen} />)}</ul>
      </details>
    </Section>
  )
}

const DOC_ORDER: DocType[] = ['settlement', 'policy', 'bill']

function Part({ title, children, tone }: { title: string; children: ReactNode; tone?: 'accent' }) {
  return (
    <section className="mt-7">
      <h4 className={`text-[13px] font-semibold ${tone === 'accent' ? 'text-accent' : 'text-mute'}`}>{title}</h4>
      <div className="mt-1.5 text-[15px] leading-relaxed text-ink-2">{children}</div>
    </section>
  )
}

function FindingDetail({ finding: f, total, clauses, documents, onOpen }: {
  finding: Finding
  total: number
  clauses: { id: string; text: string }[]
  documents: CaseDetail['documents']
  onOpen: (e: Evidence) => void
}) {
  const [clauseId, setClauseId] = useState<string | null>(null)
  const clause = clauses.find((c) => c.id === clauseId)
  const figures: [string, string | null, string][] = [
    ['Deducted by insurer', f.insurer_amount, ''],
    ['Supported by documents', f.supported_amount, ''],
    ['Contestable', f.contestable_amount, num(f.contestable_amount) > 0 ? 'text-accent!' : ''],
  ]
  const h = 'text-[15px] font-semibold text-ink'

  return (
    <article aria-label={`Finding ${f.id}`} className={`${panel} animate-fade-in p-6 sm:p-9`}>
      <p className={`${caption} flex flex-wrap items-center gap-x-2`}>
        Finding {f.id} of {total}
        {f.rule_id && <><span aria-hidden className="text-faint">·</span><span className="tabular-nums">Rule {f.rule_id}</span></>}
      </p>
      <h3 className="type-title mt-2">{f.description}</h3>
      <p className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-mute">
        <StatusBadge status={f.status} /> <span aria-hidden className="text-faint">·</span> {STATUS[f.status].meaning}
      </p>

      <dl className="mt-8 grid grid-cols-3 gap-4 border-y border-hairline-strong py-5">
        {figures.map(([label, v, cls]) => (
          <div key={label}>
            <dt className="text-[13px] leading-tight text-mute">{label}</dt>
            <dd className={`type-figure mt-1.5 text-[17px] sm:text-[1.375rem] ${cls}`}>
              {v === null ? <span className="text-sm font-normal tracking-normal text-mute">Cannot be determined</span> : <Amount value={v} />}
            </dd>
          </div>
        ))}
      </dl>

      {f.what_happened && <Part title="What happened">{f.what_happened}</Part>}
      {f.insurer_statement && <Part title="What the insurer stated">{f.insurer_statement}</Part>}
      <Part title="Policy clause applied">{f.policy_clause ?? <span className="text-mute">No clause identified in the uploaded policy.</span>}</Part>
      {f.contestable_reason && <Part title="Why it may be contestable" tone="accent"><span className="text-ink">{f.contestable_reason}</span></Part>}
      <Part title="Analysis">
        {f.explanation}
        {f.basis_label && <span className="mt-2 block text-sm text-mute">Basis: {f.basis_label}.</span>}
      </Part>

      {f.calculation.length > 0 && (
        <section className="mt-8">
          <h4 className={h}>How it was calculated</h4>
          <ol className="mt-3 divide-y divide-hairline-strong">
            {f.calculation.map((s, i) => (
              <li key={i} className="grid grid-cols-[1.5rem_1fr] gap-2 py-2.5 text-sm leading-relaxed tabular-nums text-ink-2">
                <span className="text-mute">{i + 1}</span>
                <span className="break-words">{s}</span>
              </li>
            ))}
          </ol>
          <p className="mt-1 text-xs text-mute">Computed in Python with exact decimal arithmetic.</p>
        </section>
      )}

      <section className="mt-8">
        <h4 className={h}>Source evidence</h4>
        <div className="mt-3 space-y-3">
          {DOC_ORDER.flatMap((dt) => f.evidence.filter((e) => e.doc_type === dt)).map((e, i) => (
            <figure key={i} className={`rounded-2xl px-4 py-3.5 ${e.found ? 'bg-paper' : 'bg-alert-soft ring-1 ring-alert'}`}>
              <figcaption className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px]">
                <FileText aria-hidden className="size-3.5 text-mute" strokeWidth={1.75} />
                <span className="font-medium text-ink">{DOC_LABELS[e.doc_type]}</span>
                <span aria-hidden className="text-faint">·</span>
                <span className="text-mute">{e.ref}{e.source && `, ${where(e.source)}`}</span>
                {!e.found && (
                  <span className="inline-flex items-center gap-1 font-medium text-alert">
                    <AlertTriangle className="size-3" /> Not found in the uploaded document
                  </span>
                )}
                {e.found && documents[e.doc_type]?.text && (
                  <button className={`${btn.linkSm} ml-auto`} onClick={() => onOpen(e)}>Show in document</button>
                )}
              </figcaption>
              <blockquote className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-ink-2">{e.excerpt}</blockquote>
            </figure>
          ))}
        </div>
      </section>

      {f.missing.length > 0 && (
        <Part title="Missing information">
          <ul className="list-disc space-y-1 pl-5">{f.missing.map((m) => <li key={m}>{m}</li>)}</ul>
        </Part>
      )}
      {f.next_step && (
        <section className="mt-8 rounded-2xl bg-paper px-4 py-3.5">
          <h4 className="text-[13px] font-semibold text-mute">Next step</h4>
          <p className="mt-1 text-[15px] font-medium leading-relaxed text-ink">{f.next_step}</p>
        </section>
      )}

      {(f.conditions.length > 0 || f.classification) && (
        <details className="group mt-8 border-y border-hairline-strong">
          <summary className="flex cursor-pointer list-none items-center justify-between py-3.5 text-[15px] font-medium text-ink">
            Rule trace{f.rule_title && <span className="ml-2 font-normal text-mute">{f.rule_title}</span>}
            <ChevronDown aria-hidden className="ml-auto size-4 text-mute transition-transform duration-300 group-open:rotate-180" />
          </summary>
          <div className="pb-4">
            {f.classification && <p className="text-sm text-mute">{f.classification}.</p>}
            <ul className="mt-3 space-y-2">
              {f.conditions.map((c, i) => (
                <li key={i} className="flex gap-2.5 text-sm text-ink-2">
                  {c.met === true ? <CheckCircle2 aria-label="Met" className="mt-0.5 size-4 shrink-0 text-ok" />
                    : c.met === false ? <XCircle aria-label="Not met" className="mt-0.5 size-4 shrink-0 text-caution" />
                      : <CircleHelp aria-label="Could not be checked" className="mt-0.5 size-4 shrink-0 text-faint" />}
                  <span>{c.text}{c.met === null && <span className="text-mute"> (could not be checked)</span>}</span>
                </li>
              ))}
            </ul>
          </div>
        </details>
      )}

      {f.related_clauses.length > 0 && (
        <section className="mt-8">
          <h4 className={h}>Related policy clauses <span className="font-normal text-mute">· keyword search</span></h4>
          <div className="mt-3 flex flex-wrap gap-2">
            {f.related_clauses.map((id) => (
              <button key={id} onClick={() => setClauseId(id === clauseId ? null : id)} aria-expanded={id === clauseId}
                className={`rounded-full px-3.5 py-1.5 text-[13px] font-medium tabular-nums transition-colors duration-200 ${
                  id === clauseId ? 'bg-ink text-white' : 'bg-paper text-ink-2 hover:bg-hairline'
                }`}>
                Clause {id}
              </button>
            ))}
          </div>
          {clauseId && (
            <blockquote className="mt-4 animate-fade-in border-l-2 border-ink pl-4 text-sm leading-relaxed text-ink-2">
              {clause ? <p className="whitespace-pre-wrap">{clause.text}</p> : <p className="text-mute">Clause {clauseId} is not in the extracted policy text.</p>}
            </blockquote>
          )}
        </section>
      )}
    </article>
  )
}
