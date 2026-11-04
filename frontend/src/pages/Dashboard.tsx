import { ArrowRight, CheckCircle2, CircleDashed, FlaskConical, Loader2, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, rupees, type CaseDetail, type CaseSummary, type Health, type LLMHealth } from '../api'
import ProviderStatus from '../components/ProviderStatus'
import { Card, DemoBanner, ErrorNote, btn } from '../components/ui'

export default function Dashboard() {
  const [cases, setCases] = useState<CaseSummary[] | null>(null)
  const [latest, setLatest] = useState<CaseDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loadingDemo, setLoadingDemo] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    api
      .cases()
      .then((cs) => {
        setCases(cs)
        const audited = cs.find((c) => c.status === 'audited')
        if (audited) api.case(audited.id).then(setLatest)
      })
      .catch((e) => setError(e.message))
  }, [])

  async function demo() {
    setLoadingDemo(true)
    try {
      const c = await api.demoCase()
      navigate(`/cases/${c.id}?tab=audit`)
    } catch (e) {
      setError((e as Error).message)
      setLoadingDemo(false)
    }
  }

  const a = latest?.audit
  const kpis: [string, string, string?][] = [
    ['Total hospital bill', rupees(a?.bill_total)],
    ['Total claimed', rupees(a?.claimed_amount)],
    ['Amount approved', rupees(a?.approved_amount)],
    ['Total deductions', rupees(a?.total_deductions)],
    ['Potentially contestable', rupees(a?.contestable_total), 'text-violet-700'],
    ['Needs explanation', rupees(a?.unverified_total), 'text-amber-700'],
  ]

  return (
    <div className="space-y-8">
      <section className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-navy-900">Claim audit overview</h1>
          <p className="mt-1 text-sm text-slate-600">
            Upload a hospital bill, policy and settlement letter to see where every rupee went.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className={btn.secondary} onClick={demo} disabled={loadingDemo}>
            {loadingDemo ? <Loader2 className="size-4 animate-spin" /> : <FlaskConical className="size-4" />}
            Try the synthetic demo
          </button>
          <Link to="/audit/new" className={btn.primary}>
            Start an audit <ArrowRight className="size-4" />
          </Link>
        </div>
      </section>
      <ErrorNote error={error} />

      <section className="space-y-3">
        {latest?.demo && <DemoBanner />}
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          {kpis.map(([label, value, cls]) => (
            <div key={label} className="rounded-xl border border-slate-200 bg-white p-4">
              <p className="text-xs font-medium text-slate-500">{label}</p>
              <p className={`mt-2 text-lg font-semibold ${a ? (cls ?? 'text-navy-900') : 'text-slate-300'}`}>{value}</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-500">
          {latest ? (
            <>
              Latest audit: <Link className="text-violet-700 hover:underline" to={`/cases/${latest.id}?tab=audit`}>{latest.title}</Link>
              {' · '}
              {a?.method}
            </>
          ) : (
            'No claim audited yet. Figures appear after an audit completes.'
          )}
        </p>
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Recent cases" className="lg:col-span-2" action={<Link to="/cases" className={btn.ghost}>All cases</Link>}>
          {cases?.length === 0 && <p className="text-sm text-slate-500">No cases yet.</p>}
          <ul className="divide-y divide-slate-100">
            {cases?.slice(0, 6).map((c) => (
              <li key={c.id}>
                <Link to={`/cases/${c.id}`} className="flex items-center justify-between gap-3 py-2.5 text-sm hover:text-violet-700">
                  <span className="min-w-0 truncate font-medium">
                    {c.title}
                    {c.demo && <span className="ml-2 rounded bg-amber-50 px-1.5 py-0.5 text-xs text-amber-800">demo</span>}
                  </span>
                  <span className="shrink-0 text-xs text-slate-500">
                    {c.status === 'audited' ? `${rupees(c.contestable_total)} contestable` : `${c.documents.length}/3 documents`}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
        <div className="space-y-6">
          <ProviderStatus />
          <SystemStatus />
        </div>
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
    ['BharatCode catalog reachable', llm ? llm.reachable : error ? false : null, llm?.model],
    ['API key configured', health ? health.llm_configured : error ? false : null],
  ]

  return (
    <Card title="System status">
      <ul className="space-y-3">
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
        Catalog reachability is not inference: only a successful live check marks BharatCode as connected.
      </p>
    </Card>
  )
}
