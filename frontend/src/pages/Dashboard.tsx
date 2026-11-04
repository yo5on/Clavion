import { ArrowRight, CheckCircle2, CircleDashed, Loader2, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Health, type LLMHealth } from '../api'

const kpis = [
  'Total hospital bill',
  'Total claimed',
  'Amount approved',
  'Total deductions',
  'Potentially contestable',
  'Findings',
]

const pipeline = [
  'Document ingestion',
  'Information extraction',
  'Bill item normalisation',
  'Policy clause retrieval',
  'Deduction analysis',
  'Deterministic calculation',
  'Independent verification',
  'Audit report',
]

export default function Dashboard() {
  return (
    <div className="space-y-8">
      <section className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-navy-900">Claim audit overview</h1>
          <p className="mt-1 text-sm text-slate-600">
            Upload a hospital bill, policy and settlement letter to see where every rupee went.
          </p>
        </div>
        <Link
          to="/audit/new"
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-violet-brand px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-violet-700"
        >
          Start an audit <ArrowRight className="size-4" />
        </Link>
      </section>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {kpis.map((label) => (
          <div key={label} className="rounded-xl border border-slate-200 bg-white p-4">
            <p className="text-xs font-medium text-slate-500">{label}</p>
            <p className="mt-2 text-xl font-semibold text-slate-300">—</p>
          </div>
        ))}
      </section>
      <p className="-mt-5 text-xs text-slate-500">No claim analysed yet. Figures appear after an audit completes.</p>

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="rounded-2xl border border-slate-200 bg-white p-6 lg:col-span-2">
          <h2 className="text-sm font-semibold text-navy-900">Analysis pipeline</h2>
          <p className="mt-1 text-xs text-slate-500">
            Amounts are computed in code, not by the model. Each finding links back to its source document.
          </p>
          <ol className="mt-5 grid gap-2 sm:grid-cols-2">
            {pipeline.map((step, i) => (
              <li key={step} className="flex items-center gap-3 rounded-lg bg-surface px-3 py-2.5 text-sm text-slate-700">
                <span className="grid size-6 shrink-0 place-items-center rounded-full bg-navy-900 text-xs font-medium text-white">
                  {i + 1}
                </span>
                {step}
              </li>
            ))}
          </ol>
        </section>
        <SystemStatus />
      </div>
    </div>
  )
}

function SystemStatus() {
  const [health, setHealth] = useState<Health | null>(null)
  const [llm, setLlm] = useState<LLMHealth | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    api.health().then(setHealth).catch(() => setError(true))
    api.llmHealth().then(setLlm).catch(() => setError(true))
  }, [])

  const rows: [string, boolean | null, string?][] = [
    ['API server', error ? false : health ? true : null],
    ['Database', health ? health.database : error ? false : null],
    ['BharatCode reachable', llm ? llm.reachable : error ? false : null, llm?.model],
    ['API key configured', health ? health.llm_configured : error ? false : null],
    [
      'Image input supported',
      llm ? !!llm.model_capabilities?.input?.includes('image') : error ? false : null,
    ],
    ['Tool calling supported', llm ? !!llm.model_capabilities?.toolCalling : error ? false : null],
  ]

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6">
      <h2 className="text-sm font-semibold text-navy-900">System status</h2>
      <ul className="mt-4 space-y-3">
        {rows.map(([label, ok, note]) => (
          <li key={label} className="flex items-center justify-between gap-3 text-sm">
            <span className="text-slate-700">{label}</span>
            <span className="flex items-center gap-1.5 text-xs text-slate-500">
              {note}
              {ok === null ? (
                <Loader2 className="size-4 animate-spin text-slate-400" />
              ) : ok ? (
                <CheckCircle2 className="size-4 text-emerald-600" />
              ) : (
                <XCircle className="size-4 text-rose-500" />
              )}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-5 flex items-start gap-2 text-xs text-slate-500">
        <CircleDashed className="mt-0.5 size-3.5 shrink-0" />
        Capabilities come from the BharatCode model catalog; run the feasibility probe to verify them live.
      </p>
    </section>
  )
}
