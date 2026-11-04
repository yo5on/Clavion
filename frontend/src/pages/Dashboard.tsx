import { ArrowRight, FlaskConical, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, type CaseDetail, type CaseSummary, type Health, type LLMHealth } from '../api'
import { SettlementSummary } from '../components/AuditView'
import ProviderStatus from '../components/ProviderStatus'
import { Amount, Card, DemoTag, ErrorNote, PageHeader, Skeleton, btn, eyebrow } from '../components/ui'
import { CaseStatus, caseLink } from './Cases'

const STEPS: [string, string][] = [
  ['Upload the claim documents', 'Hospital bill, policy wording and the insurer’s settlement letter. PDFs and scans both work.'],
  ['Review what was extracted', 'Every field and line item is editable. Correct anything the reader got wrong before auditing.'],
  ['Audit, then appeal', 'Each deduction is checked against the policy and bill, with evidence. Export the report and a draft appeal.'],
]

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
        if (audited) api.case(audited.id).then(setLatest).catch((e) => setError(e.message))
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

  const hasAudit = cases?.some((c) => c.status === 'audited')

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Overview"
        title="Claims audit"
        description="Check every deduction on a health-insurance settlement against the policy and the hospital bill."
        actions={
          <>
            <button className={btn.secondary} onClick={demo} disabled={loadingDemo}>
              {loadingDemo ? <Loader2 className="size-4 animate-spin" /> : <FlaskConical className="size-4" />}
              Open demo claim
            </button>
            <Link to="/audit/new" className={btn.primary}>
              Start an audit <ArrowRight className="size-4" />
            </Link>
          </>
        }
      />
      <ErrorNote error={error} />

      {cases && !hasAudit && (
        <Card title="How an audit works">
          <ol className="grid gap-6 md:grid-cols-3">
            {STEPS.map(([title, body], i) => (
              <li key={title} className="border-l-2 border-line pl-4">
                <span className="font-mono text-xs text-violet-700">0{i + 1}</span>
                <p className="mt-1 text-sm font-semibold text-navy-900">{title}</p>
                <p className="mt-1 text-sm leading-relaxed text-slate-600">{body}</p>
              </li>
            ))}
          </ol>
        </Card>
      )}

      {(!cases || hasAudit) && (
        <Card
          title="Latest audit"
          action={latest && (
            <Link to={`/cases/${latest.id}?tab=audit`} className={btn.ghost}>
              Open findings <ArrowRight className="size-3.5" />
            </Link>
          )}
        >
          {latest?.audit ? (
            <>
              <p className="mb-5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
                <span className="font-medium text-navy-900">{latest.title}</span>
                {latest.demo && <DemoTag />}
                <span className="text-xs text-slate-500">
                  · {latest.audit.method} · {new Date(latest.audit.generated_at).toLocaleDateString()}
                </span>
              </p>
              <SettlementSummary audit={latest.audit} />
            </>
          ) : (
            <div className="space-y-4">
              <Skeleton className="h-4 w-64" />
              <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}
              </div>
              <Skeleton className="h-3" />
            </div>
          )}
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Recent cases" className="lg:col-span-2" flush
          action={<Link to="/cases" className={btn.ghost}>All cases <ArrowRight className="size-3.5" /></Link>}>
          {!cases && !error && <div className="space-y-3 p-5">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-6" />)}</div>}
          {cases?.length === 0 && (
            <p className="px-5 py-8 text-center text-sm text-slate-500">
              No cases yet. <Link to="/audit/new" className="font-medium text-violet-700 hover:underline">Start your first audit</Link>.
            </p>
          )}
          {cases && cases.length > 0 && (
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-slate-500">
                <tr className="border-b border-line">
                  <th className="px-5 py-2 font-medium">Case</th>
                  <th className="hidden px-3 py-2 font-medium sm:table-cell">Status</th>
                  <th className="px-5 py-2 text-right font-medium">Contestable</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {cases.slice(0, 6).map((c) => (
                  <tr key={c.id} className="group cursor-pointer transition-colors hover:bg-slate-50" onClick={() => navigate(caseLink(c))}>
                    <td className="w-full max-w-0 px-5 py-3">
                      <span className="flex items-center gap-2">
                        <Link to={caseLink(c)} className="truncate font-medium text-navy-900 group-hover:text-violet-700">{c.title}</Link>
                        {c.demo && <DemoTag />}
                      </span>
                    </td>
                    <td className="hidden whitespace-nowrap px-3 py-3 sm:table-cell"><CaseStatus c={c} /></td>
                    <td className="px-5 py-3 text-right">
                      {c.status === 'audited' ? (
                        <Amount value={c.contestable_total} className={Number(c.contestable_total) > 0 ? 'font-medium text-violet-700' : 'text-slate-500'} />
                      ) : (
                        <span className="text-xs text-slate-400">Not audited</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
        <Card title="Environment">
          <div className="space-y-6">
            <ProviderStatus />
            <SystemStatus />
          </div>
        </Card>
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
    <div>
      <h3 className={eyebrow}>System</h3>
      <ul className="mt-3 space-y-2">
        {rows.map(([label, ok, note]) => (
          <li key={label} className="flex items-center justify-between gap-3 text-sm">
            <span className="text-slate-700">{label}</span>
            <span className="flex items-center gap-2 text-xs text-slate-500">
              {note && <span className="font-mono">{note}</span>}
              <span
                aria-label={ok === null ? 'Checking' : ok ? 'OK' : 'Failed'}
                className={`size-2 rounded-full ${ok === null ? 'animate-pulse bg-slate-300' : ok ? 'bg-emerald-500' : 'bg-rose-500'}`}
              />
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs leading-relaxed text-slate-500">
        Catalog reachability is not inference: only a successful live check marks BharatCode as connected.
      </p>
    </div>
  )
}
