import { AlertTriangle, BookOpen, Calculator, FileSearch } from 'lucide-react'
import { useState } from 'react'
import { DOC_LABELS, rupees, type AuditReport, type Finding, type PolicyClause } from '../api'
import { Card, StatusBadge } from './ui'

export default function AuditView({ audit, clauses }: { audit: AuditReport; clauses: PolicyClause[] }) {
  const [selected, setSelected] = useState<number>(
    audit.findings.find((f) => f.status === 'contestable')?.id ?? audit.findings[0]?.id ?? 0,
  )
  const finding = audit.findings.find((f) => f.id === selected)
  const maxBreakdown = Math.max(...audit.breakdown.map((b) => Number(b.amount)), 1)

  const kpis: [string, string, string][] = [
    ['Hospital bill', rupees(audit.bill_total), 'text-navy-900'],
    ['Claimed', rupees(audit.claimed_amount), 'text-navy-900'],
    ['Approved', rupees(audit.approved_amount), 'text-navy-900'],
    ['Total deductions', rupees(audit.total_deductions), 'text-navy-900'],
    ['Supported by documents', rupees(audit.supported_total), 'text-emerald-700'],
    ['Potentially contestable', rupees(audit.contestable_total), 'text-violet-700'],
    ['Needs explanation', rupees(audit.unverified_total), 'text-amber-700'],
  ]

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        {kpis.map(([label, value, cls]) => (
          <div key={label} className="rounded-xl border border-slate-200 bg-white p-3.5">
            <p className="text-xs font-medium text-slate-500">{label}</p>
            <p className={`mt-1.5 text-base font-semibold ${cls}`}>{value}</p>
          </div>
        ))}
      </div>
      <p className="-mt-3 text-xs text-slate-500">
        {audit.method} · generated {new Date(audit.generated_at).toLocaleString()}. “Potentially contestable” means the
        uploaded documents do not support that part of a deduction; it is not a guarantee of recovery.
      </p>

      <div className="grid gap-6 lg:grid-cols-5">
        <Card title="Deduction breakdown" className="lg:col-span-2">
          <ul className="space-y-3">
            {audit.breakdown.map((b) => (
              <li key={b.category} className="text-sm">
                <div className="flex justify-between gap-2">
                  <span className="text-slate-700">{b.category} <span className="text-xs text-slate-400">×{b.count}</span></span>
                  <span className="font-medium text-navy-900">{rupees(b.amount)}</span>
                </div>
                <div className="mt-1 h-1.5 rounded-full bg-slate-100">
                  <div className="h-1.5 rounded-full bg-violet-brand" style={{ width: `${(Number(b.amount) / maxBreakdown) * 100}%` }} />
                </div>
              </li>
            ))}
          </ul>
          {audit.missing_information.length > 0 && (
            <div className="mt-6 rounded-lg bg-amber-50 p-3">
              <p className="flex items-center gap-1.5 text-xs font-semibold text-amber-800">
                <AlertTriangle className="size-3.5" /> Missing or inconsistent information
              </p>
              <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-amber-900">
                {audit.missing_information.map((m) => <li key={m}>{m}</li>)}
              </ul>
            </div>
          )}
        </Card>

        <Card title="Findings" className="lg:col-span-3">
          <ul className="space-y-2">
            {audit.findings.map((f) => (
              <li key={f.id}>
                <button
                  className={`w-full rounded-lg border p-3 text-left transition-colors ${
                    f.id === selected ? 'border-violet-400 bg-violet-50/50' : 'border-slate-200 hover:border-slate-300'
                  }`}
                  onClick={() => setSelected(f.id)}
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <span className="text-sm font-medium text-navy-900">{f.id}. {f.description}</span>
                    <StatusBadge status={f.status} />
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    {f.category} · deducted {rupees(f.insurer_amount)}
                    {f.status === 'contestable' && <> · <span className="font-medium text-violet-700">{rupees(f.contestable_amount)} contestable</span></>}
                  </p>
                </button>
              </li>
            ))}
            {audit.findings.length === 0 && <p className="text-sm text-slate-500">No deductions to assess.</p>}
          </ul>
        </Card>
      </div>

      {finding && <EvidenceViewer finding={finding} clauses={clauses} />}
    </div>
  )
}

function EvidenceViewer({ finding: f, clauses }: { finding: Finding; clauses: PolicyClause[] }) {
  const [clauseId, setClauseId] = useState<string | null>(null)
  const clause = clauses.find((c) => c.id === clauseId)
  return (
    <Card title={<span className="flex items-center gap-2"><FileSearch className="size-4 text-violet-600" /> Evidence for finding {f.id}</span>}>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={f.status} />
            <span className="text-xs text-slate-500">
              Deducted {rupees(f.insurer_amount)} · supported {f.supported_amount === null ? 'cannot be determined' : rupees(f.supported_amount)} ·
              contestable {rupees(f.contestable_amount)}
            </span>
          </div>
          <p className="text-sm leading-relaxed text-slate-700">{f.explanation}</p>
          {f.calculation.length > 0 && (
            <div className="rounded-lg bg-surface p-3">
              <p className="flex items-center gap-1.5 text-xs font-semibold text-navy-900"><Calculator className="size-3.5" /> Calculation (Python, Decimal)</p>
              <ol className="mt-2 list-decimal space-y-1 pl-4 font-mono text-xs text-slate-700">
                {f.calculation.map((s) => <li key={s}>{s}</li>)}
              </ol>
            </div>
          )}
          {f.related_clauses.length > 0 && (
            <div>
              <p className="flex items-center gap-1.5 text-xs font-semibold text-navy-900"><BookOpen className="size-3.5" /> Related clauses (keyword search)</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {f.related_clauses.map((id) => (
                  <button key={id} onClick={() => setClauseId(id === clauseId ? null : id)}
                    className={`rounded-md px-2 py-1 text-xs font-medium ring-1 ${id === clauseId ? 'bg-navy-900 text-white ring-navy-900' : 'text-violet-700 ring-violet-200 hover:bg-violet-50'}`}>
                    Clause {id}
                  </button>
                ))}
              </div>
              {clause && <pre className="mt-2 whitespace-pre-wrap rounded-lg bg-navy-950 p-3 text-xs leading-relaxed text-slate-200">{clause.text}</pre>}
            </div>
          )}
        </div>
        <ul className="space-y-2">
          {f.evidence.map((e, i) => (
            <li key={i} className={`rounded-lg border p-3 ${e.found ? 'border-slate-200' : 'border-rose-200 bg-rose-50'}`}>
              <p className="text-xs font-semibold text-navy-900">
                {DOC_LABELS[e.doc_type]} · {e.ref}
                {!e.found && <span className="ml-2 text-rose-700">not found in uploaded document</span>}
              </p>
              <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed text-slate-600">{e.excerpt}</p>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  )
}
