import { AlertTriangle, ArrowRight, FileText, X } from 'lucide-react'
import { useRef, useState } from 'react'
import { api, DOC_LABELS, rupees, type AuditReport, type DocType, type Finding, type FindingStatus, type PolicyClause } from '../api'
import { Amount, LedgerBar, PdfButton, STATUS, Section, StatusBadge, Swatch, btn, caption, panel } from './ui'

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
      <dl className="grid grid-cols-2 gap-x-6 gap-y-8 md:grid-cols-4">
        {figures.map(([label, v]) => (
          <div key={label}>
            <dt className={caption}>{label}</dt>
            <dd className="type-figure mt-1.5 text-[1.625rem] leading-tight sm:text-[2rem]">
              <Amount value={v} />
            </dd>
          </div>
        ))}
      </dl>

      <LedgerBar className="mt-10 h-2.5" approved={approved} {...totals} />

      <ul className="-mx-3 mt-5 grid gap-1 sm:grid-cols-2 lg:grid-cols-4">
        <li className="flex items-start gap-3 px-3 py-2.5">
          <Swatch fill="fill-approved" className="mt-1.5" />
          <span className="min-w-0 flex-1">
            <span className="block text-sm text-mute">Paid by insurer</span>
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
  const contestable = num(audit.contestable_total)
  const unverified = num(audit.unverified_total)

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
              ) : (
                'No deduction appears contestable.'
              )}
            </h2>
            <p className="type-lead mt-4">
              The insurer deducted {rupees(audit.total_deductions)} from a claim of {rupees(audit.claimed_amount)}.
              Clavion checked {audit.findings.length} deduction{audit.findings.length === 1 ? '' : 's'} against the policy and the bill
              {unverified > 0 ? `; ${rupees(audit.unverified_total)} could not be verified.` : '.'}
            </p>
          </div>
          <PdfButton href={api.exportUrl(caseId, 'report')} className={`${btn.secondary} shrink-0 self-start md:self-auto`}>Audit report</PdfButton>
        </div>

        <div className="mt-12">
          <SettlementSummary audit={audit} filter={filter} onFilter={applyFilter} />
        </div>
        <p className="mt-6 max-w-3xl text-[13px] leading-relaxed text-mute">
          {audit.method} · generated {new Date(audit.generated_at).toLocaleString()}. “Potentially contestable” means the
          uploaded documents do not support that part of a deduction; it is not a guarantee of recovery.
        </p>
      </section>

      {audit.missing_information.length > 0 && (
        <div role="note" className="rounded-[28px] bg-caution-soft px-6 py-5 sm:px-8 sm:py-6">
          <p className="flex items-center gap-2.5 text-[17px] font-semibold text-caution">
            <AlertTriangle className="size-[18px]" strokeWidth={1.75} /> Missing or inconsistent information
          </p>
          <ul className="mt-2 list-disc space-y-1 pl-12 text-[15px] leading-relaxed text-ink-2">
            {audit.missing_information.map((m) => <li key={m}>{m}</li>)}
          </ul>
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
            {finding && <EvidenceViewer key={finding.id} finding={finding} total={audit.findings.length} clauses={clauses} />}
          </div>
        </div>
      </Section>

      <Breakdown audit={audit} />

      <section className="flex flex-col items-start justify-between gap-6 border-t border-hairline pt-10 sm:flex-row sm:items-center">
        <div>
          <p className="type-heading">Next, the appeal letter.</p>
          <p className="mt-1 text-[15px] text-mute">The draft is written from these findings. Review and edit it before sending.</p>
        </div>
        <button className={btn.primary} onClick={onNext}>Continue to appeal <ArrowRight className="size-4" /></button>
      </section>
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
    <Section title="Deductions by reason">
      {rows.length === 0 && <p className="text-[17px] text-mute">No deductions.</p>}
      <ul className="divide-y divide-hairline">
        {rows.map((r) => (
          <li key={r.category} className="grid items-center gap-x-8 gap-y-2 py-4 sm:grid-cols-[minmax(0,15rem)_1fr_8rem]">
            <span className="text-[15px] text-ink">
              {r.category} <span className="text-mute">· {r.count}</span>
            </span>
            <span className="flex h-2 gap-[3px] overflow-hidden rounded-full" style={{ width: `${(num(r.amount) / max) * 100}%` }}>
              {r.parts.map(([s, v]) => v > 0 && (
                <span key={s} className={`${STATUS[s].fill} min-w-1 rounded-full`} style={{ flexGrow: v }} title={`${STATUS[s].label}: ${rupees(v.toFixed(2))}`} />
              ))}
            </span>
            <Amount value={r.amount} className="type-figure text-[15px] sm:text-right" />
          </li>
        ))}
      </ul>
    </Section>
  )
}

const DOC_ORDER: DocType[] = ['settlement', 'policy', 'bill']

function EvidenceViewer({ finding: f, total, clauses }: { finding: Finding; total: number; clauses: PolicyClause[] }) {
  const [clauseId, setClauseId] = useState<string | null>(null)
  const clause = clauses.find((c) => c.id === clauseId)
  const figures: [string, string | null, string][] = [
    ['Deducted by insurer', f.insurer_amount, ''],
    ['Supported by documents', f.supported_amount, ''],
    ['Contestable', f.contestable_amount, num(f.contestable_amount) > 0 ? 'text-accent!' : ''],
  ]
  const h = 'text-[15px] font-semibold text-ink'

  return (
    <article aria-label={`Finding ${f.id} evidence`} className={`${panel} animate-fade-in p-6 sm:p-9`}>
      <p className={caption}>Finding {f.id} of {total}</p>
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

      <p className="mt-6 text-[16px] leading-relaxed text-ink-2">{f.explanation}</p>

      {f.calculation.length > 0 && (
        <section className="mt-9">
          <h4 className={h}>How it was calculated</h4>
          <ol className="mt-3 divide-y divide-hairline-strong">
            {f.calculation.map((s, i) => (
              <li key={s} className="grid grid-cols-[1.5rem_1fr] gap-2 py-2.5 text-sm leading-relaxed tabular-nums text-ink-2">
                <span className="text-mute">{i + 1}</span>
                <span className="break-words">{s}</span>
              </li>
            ))}
          </ol>
          <p className="mt-1 text-xs text-mute">Computed in Python with exact decimal arithmetic.</p>
        </section>
      )}

      <section className="mt-9">
        <h4 className={h}>Source evidence</h4>
        <div className="mt-3 space-y-3">
          {DOC_ORDER.map((dt) => {
            const items = f.evidence.filter((e) => e.doc_type === dt)
            if (items.length === 0) return null
            return items.map((e, i) => (
              <figure key={`${dt}-${i}`} className={`rounded-2xl px-4 py-3.5 ${e.found ? 'bg-paper' : 'bg-alert-soft ring-1 ring-alert'}`}>
                <figcaption className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px]">
                  <FileText aria-hidden className="size-3.5 text-mute" strokeWidth={1.75} />
                  <span className="font-medium text-ink">{DOC_LABELS[dt]}</span>
                  <span aria-hidden className="text-faint">·</span>
                  <span className="text-mute">{e.ref}</span>
                  {!e.found && (
                    <span className="inline-flex items-center gap-1 font-medium text-alert">
                      <AlertTriangle className="size-3" /> Not found in the uploaded document
                    </span>
                  )}
                </figcaption>
                <blockquote className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-ink-2">{e.excerpt}</blockquote>
              </figure>
            ))
          })}
        </div>
      </section>

      {f.related_clauses.length > 0 && (
        <section className="mt-9">
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
              {clause ? (
                <p className="whitespace-pre-wrap">{clause.text}</p>
              ) : (
                <p className="text-mute">Clause {clauseId} is not in the extracted policy text.</p>
              )}
            </blockquote>
          )}
        </section>
      )}
    </article>
  )
}
