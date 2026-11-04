import { AlertTriangle, ArrowRight, FileText, X } from 'lucide-react'
import { useRef, useState } from 'react'
import { api, DOC_LABELS, rupees, type AuditReport, type DocType, type Finding, type FindingStatus, type PolicyClause } from '../api'
import { Amount, Card, LedgerBar, PdfButton, STATUS, StatusBadge, Swatch, btn, eyebrow } from './ui'

const num = (v: string | null | undefined) => Number(v ?? 0) || 0

// Split of one finding's deduction across the three states; mirrors how the audit's own totals are formed.
function split(f: Finding) {
  const supported = num(f.supported_amount)
  const contestable = num(f.contestable_amount)
  return { supported, contestable, unverified: Math.max(num(f.insurer_amount) - supported - contestable, 0) }
}

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
  const figures: [string, string | null][] = [
    ['Hospital bill', audit.bill_total],
    ['Claimed', audit.claimed_amount],
    ['Approved', audit.approved_amount],
    ['Deducted', audit.total_deductions],
  ]

  return (
    <div>
      <dl className="grid grid-cols-2 gap-y-5 md:grid-cols-4 md:divide-x md:divide-line">
        {figures.map(([label, v]) => (
          <div key={label} className="pr-4 md:px-6 md:first:pl-0">
            <dt className={eyebrow}>{label}</dt>
            <dd className="mt-1 font-serif text-[1.375rem] font-semibold leading-tight text-navy-900 sm:text-[1.625rem]">
              <Amount value={v} />
            </dd>
          </div>
        ))}
      </dl>

      <LedgerBar className="mt-6 h-3.5" approved={approved} {...totals} />

      <ul className="mt-4 grid gap-x-6 gap-y-1 sm:grid-cols-2 lg:grid-cols-4">
        <li className="flex items-baseline gap-2 px-2 py-1.5 text-sm">
          <Swatch fill="fill-approved" className="translate-y-px" />
          <span>
            <span className="block text-slate-600">Paid by insurer</span>
            <Amount value={approved} className="font-medium text-navy-900" />
          </span>
          <span className="ml-auto text-xs tabular-nums text-slate-500">{pct(approved)}</span>
        </li>
        {(Object.keys(STATUS) as FindingStatus[]).map((s) => {
          const body = (
            <>
              <Swatch fill={STATUS[s].fill} className="translate-y-px" />
              <span className="text-left">
                <span className={`block ${s === 'contestable' ? 'font-medium text-violet-700' : 'text-slate-600'}`}>{STATUS[s].label}</span>
                <Amount value={totals[s]} className="font-medium text-navy-900" />
              </span>
              <span className="ml-auto text-xs tabular-nums text-slate-500">{pct(totals[s])}</span>
            </>
          )
          const cls = 'flex w-full items-baseline gap-2 rounded-md px-2 py-1.5 text-sm'
          return (
            <li key={s}>
              {onFilter ? (
                <button type="button" title={`${STATUS[s].meaning} Click to filter findings.`} aria-pressed={filter === s}
                  onClick={() => onFilter(filter === s ? null : s)}
                  className={`${cls} transition-colors hover:bg-slate-50 ${filter === s ? 'bg-slate-50 ring-1 ring-slate-300' : ''}`}>
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

export default function AuditView({ audit, clauses, caseId, onNext }: {
  audit: AuditReport
  clauses: PolicyClause[]
  caseId: string
  onNext: () => void
}) {
  const [selected, setSelected] = useState<number>(
    audit.findings.find((f) => f.status === 'contestable')?.id ?? audit.findings[0]?.id ?? 0,
  )
  const [filter, setFilter] = useState<FindingStatus | null>(null)
  const evidenceRef = useRef<HTMLDivElement>(null)
  const finding = audit.findings.find((f) => f.id === selected)
  const shown = audit.findings.filter((f) => !filter || f.status === filter)

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
    <div className="space-y-6">
      <Card title="Settlement reconciliation"
        action={<PdfButton href={api.exportUrl(caseId, 'report')}>Audit report PDF</PdfButton>}>
        <SettlementSummary audit={audit} filter={filter} onFilter={applyFilter} />
        <p className="mt-5 border-t border-line pt-3 text-xs leading-relaxed text-slate-500">
          {audit.method} · generated {new Date(audit.generated_at).toLocaleString()}. “Potentially contestable” means the
          uploaded documents do not support that part of a deduction; it is not a guarantee of recovery.
        </p>
      </Card>

      {audit.missing_information.length > 0 && (
        <div role="note" className="rounded-md border border-amber-300/70 bg-amber-50 px-4 py-3">
          <p className="flex items-center gap-2 text-sm font-semibold text-amber-900">
            <AlertTriangle className="size-4" /> Missing or inconsistent information
          </p>
          <ul className="mt-1.5 list-disc space-y-0.5 pl-10 text-sm text-amber-900">
            {audit.missing_information.map((m) => <li key={m}>{m}</li>)}
          </ul>
        </div>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-12">
        <Card flush className="lg:col-span-5"
          title={<>Findings <span className="ml-1 font-normal text-slate-400">{shown.length}{filter && ` of ${audit.findings.length}`}</span></>}
          action={filter && (
            <button className={btn.ghost} onClick={() => applyFilter(null)}>
              <X className="size-3.5" /> {STATUS[filter].label}
            </button>
          )}>
          <ul className="divide-y divide-line">
            {shown.map((f) => {
              const active = f.id === selected
              return (
                <li key={f.id}>
                  <button
                    onClick={() => select(f.id)}
                    aria-current={active}
                    className={`grid w-full grid-cols-[1.25rem_minmax(0,1fr)_auto] gap-x-3 border-l-2 py-3 pl-[18px] pr-5 text-left transition-colors ${
                      active ? 'border-violet-600 bg-violet-50/50' : 'border-transparent hover:bg-slate-50'
                    }`}
                  >
                    <span className="pt-px font-mono text-xs text-slate-400">{String(f.id).padStart(2, '0')}</span>
                    <span className="min-w-0">
                      <span className="block text-sm font-medium leading-snug text-navy-900">{f.description}</span>
                      <span className="mt-1.5 flex flex-wrap items-center gap-2">
                        <StatusBadge status={f.status} />
                        <span className="text-xs text-slate-500">{f.category}</span>
                      </span>
                    </span>
                    <span className="text-right text-sm">
                      <Amount value={f.insurer_amount} className="font-medium text-navy-900" />
                      {num(f.contestable_amount) > 0 && (
                        <span className="mt-1 block text-xs text-violet-700">
                          <Amount value={f.contestable_amount} /> <span className="hidden sm:inline">contestable</span>
                        </span>
                      )}
                    </span>
                  </button>
                </li>
              )
            })}
            {audit.findings.length === 0 && <li className="px-5 py-8 text-center text-sm text-slate-500">The settlement letter lists no deductions to assess.</li>}
          </ul>
        </Card>

        <div ref={evidenceRef} className="scroll-mt-20 lg:sticky lg:top-6 lg:col-span-7">
          {finding && <EvidenceViewer key={finding.id} finding={finding} clauses={clauses} />}
        </div>
      </div>

      <Breakdown audit={audit} />

      <div className="flex flex-col items-start justify-between gap-3 rounded-lg border border-line bg-white px-5 py-4 sm:flex-row sm:items-center">
        <p className="text-sm text-slate-600">
          <span className="font-medium text-navy-900">Next:</span> review the appeal letter drafted from these findings.
        </p>
        <button className={btn.primary} onClick={onNext}>Appeal letter <ArrowRight className="size-4" /></button>
      </div>
    </div>
  )
}

function Breakdown({ audit }: { audit: AuditReport }) {
  const rows = audit.breakdown.map((b) => {
    const fs = audit.findings.filter((f) => f.category === b.category).map(split)
    return {
      ...b,
      parts: (Object.keys(STATUS) as FindingStatus[]).map((s) => [s, fs.reduce((t, x) => t + x[s], 0)] as const),
    }
  })
  const max = Math.max(...rows.map((r) => num(r.amount)), 1)

  return (
    <Card title="Deductions by reason">
      {rows.length === 0 && <p className="text-sm text-slate-500">No deductions.</p>}
      <ul className="space-y-4">
        {rows.map((r) => (
          <li key={r.category} className="grid items-center gap-x-6 gap-y-1.5 text-sm sm:grid-cols-[minmax(0,14rem)_1fr_7.5rem]">
            <span className="text-slate-700">
              {r.category} <span className="text-xs text-slate-400">× {r.count}</span>
            </span>
            <span className="flex h-2.5 gap-px overflow-hidden rounded-sm" style={{ width: `${(num(r.amount) / max) * 100}%` }}>
              {r.parts.map(([s, v]) => v > 0 && (
                <span key={s} className={`${STATUS[s].fill} min-w-[3px]`} style={{ flexGrow: v }} title={`${STATUS[s].label}: ${rupees(v.toFixed(2))}`} />
              ))}
            </span>
            <Amount value={r.amount} className="font-medium text-navy-900 sm:text-right" />
          </li>
        ))}
      </ul>
    </Card>
  )
}

const DOC_ORDER: DocType[] = ['settlement', 'policy', 'bill']

function EvidenceViewer({ finding: f, clauses }: { finding: Finding; clauses: PolicyClause[] }) {
  const [clauseId, setClauseId] = useState<string | null>(null)
  const clause = clauses.find((c) => c.id === clauseId)
  const figures: [string, string | null, string][] = [
    ['Deducted by insurer', f.insurer_amount, 'text-navy-900'],
    ['Supported by documents', f.supported_amount, 'text-navy-900'],
    ['Contestable', f.contestable_amount, num(f.contestable_amount) > 0 ? 'text-violet-700' : 'text-navy-900'],
  ]

  return (
    <Card>
      <p className={eyebrow}>Finding {String(f.id).padStart(2, '0')} · Evidence</p>
      <h3 className="mt-1.5 text-base font-semibold leading-snug">{f.description}</h3>
      <p className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <StatusBadge status={f.status} /> {STATUS[f.status].meaning}
      </p>

      <dl className="mt-5 grid grid-cols-3 divide-x divide-line rounded-md border border-line">
        {figures.map(([label, v, cls]) => (
          <div key={label} className="px-3 py-2.5 sm:px-4">
            <dt className="text-[11px] leading-tight text-slate-500">{label}</dt>
            <dd className={`mt-1 text-sm font-semibold sm:text-base ${cls}`}>
              {v === null ? <span className="text-xs font-normal text-slate-500">Cannot be determined</span> : <Amount value={v} />}
            </dd>
          </div>
        ))}
      </dl>

      <p className="mt-5 text-sm leading-relaxed text-slate-700">{f.explanation}</p>

      {f.calculation.length > 0 && (
        <section className="mt-6">
          <h4 className={eyebrow}>Calculation</h4>
          <ol className="mt-2 divide-y divide-line rounded-md border border-line bg-slate-50/60">
            {f.calculation.map((s, i) => (
              <li key={s} className="grid grid-cols-[1.5rem_1fr] gap-2 px-3 py-2 font-mono text-[12.5px] leading-relaxed text-slate-700">
                <span className="text-slate-400">{i + 1}</span>
                <span className="break-words">{s}</span>
              </li>
            ))}
          </ol>
          <p className="mt-1.5 text-[11px] text-slate-400">Computed in Python with exact decimal arithmetic.</p>
        </section>
      )}

      <section className="mt-6">
        <h4 className={eyebrow}>Source evidence</h4>
        <div className="mt-2 space-y-4">
          {DOC_ORDER.map((dt) => {
            const items = f.evidence.filter((e) => e.doc_type === dt)
            if (items.length === 0) return null
            return (
              <div key={dt}>
                <p className="flex items-center gap-1.5 text-xs font-medium text-navy-900">
                  <FileText className="size-3.5 text-slate-400" /> {DOC_LABELS[dt]}
                </p>
                <ul className="mt-1.5 space-y-2">
                  {items.map((e, i) => (
                    <li key={i} className={`border-l-2 py-0.5 pl-3 ${e.found ? 'border-line' : 'border-rose-400'}`}>
                      <p className="flex flex-wrap items-center gap-2">
                        <span className="rounded-sm bg-slate-100 px-1.5 py-px font-mono text-[11px] text-slate-700">{e.ref}</span>
                        {!e.found && (
                          <span className="inline-flex items-center gap-1 text-xs font-medium text-rose-700">
                            <AlertTriangle className="size-3" /> Not found in the uploaded document
                          </span>
                        )}
                      </p>
                      <p className="mt-1 whitespace-pre-wrap text-[13px] leading-relaxed text-slate-600">{e.excerpt}</p>
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
        </div>
      </section>

      {f.related_clauses.length > 0 && (
        <section className="mt-6">
          <h4 className={eyebrow}>Related policy clauses <span className="normal-case tracking-normal text-slate-400">· keyword search</span></h4>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {f.related_clauses.map((id) => (
              <button key={id} onClick={() => setClauseId(id === clauseId ? null : id)} aria-expanded={id === clauseId}
                className={`rounded px-2 py-1 font-mono text-xs transition-colors ${
                  id === clauseId ? 'bg-navy-900 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                }`}>
                § {id}
              </button>
            ))}
          </div>
          {clauseId && (
            <div className="mt-2 rounded-md border border-line bg-slate-50/60 p-3 text-[13px] leading-relaxed text-slate-700">
              {clause ? (
                <p className="whitespace-pre-wrap">{clause.text}</p>
              ) : (
                <p className="text-slate-500">Clause {clauseId} is not in the extracted policy text.</p>
              )}
            </div>
          )}
        </section>
      )}
    </Card>
  )
}
