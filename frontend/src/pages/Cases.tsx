import { FolderClock, Plus, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, type CaseSummary } from '../api'
import { Amount, Card, DemoTag, EmptyState, ErrorNote, PageHeader, Skeleton, btn, input } from '../components/ui'

export const caseLink = (c: CaseSummary) => `/cases/${c.id}${c.status === 'audited' ? '?tab=audit' : ''}`

export function CaseStatus({ c }: { c: Pick<CaseSummary, 'status' | 'documents'> }) {
  return c.status === 'audited' ? (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-700">
      <span className="size-1.5 rounded-full bg-navy-700" /> Audited
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 text-xs text-slate-500">
      <span className="size-1.5 rounded-full border border-slate-400" /> Draft · {c.documents.length}/3 documents
    </span>
  )
}

const FILTERS = [['all', 'All'], ['audited', 'Audited'], ['draft', 'Draft']] as const

function SettledRatio({ c }: { c: CaseSummary }) {
  const claimed = Number(c.claimed_amount)
  if (!claimed || c.approved_amount === null) return <span className="text-slate-300">—</span>
  const pct = (Number(c.approved_amount) / claimed) * 100
  return (
    <span className="inline-flex items-center gap-2">
      <span className="h-1.5 w-16 overflow-hidden rounded-sm bg-slate-100"><span className="fill-approved block h-full" style={{ width: `${Math.min(pct, 100)}%` }} /></span>
      <span className="w-12 text-right tabular-nums text-slate-600">{pct.toFixed(1)}%</span>
    </span>
  )
}

export default function Cases() {
  const [cases, setCases] = useState<CaseSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<(typeof FILTERS)[number][0]>('all')
  const navigate = useNavigate()
  useEffect(() => {
    api.cases().then(setCases).catch((e) => setError(e.message))
  }, [])

  const shown = cases?.filter(
    (c) => (filter === 'all' || c.status === filter) && c.title.toLowerCase().includes(query.trim().toLowerCase()),
  )

  return (
    <div className="space-y-6">
      <PageHeader
        kicker="Records"
        title="Case history"
        description="Every claim you have opened, with its settlement outcome and the amount the audit found contestable."
        actions={<Link to="/audit/new" className={btn.primary}><Plus className="size-4" /> New audit</Link>}
      />
      <ErrorNote error={error} />

      {cases?.length === 0 ? (
        <Card>
          <EmptyState icon={FolderClock} title="No cases yet"
            actions={<Link to="/audit/new" className={btn.primary}>Start an audit</Link>}>
            Cases appear here once you upload a claim or open the demo.
          </EmptyState>
        </Card>
      ) : (
        <Card flush>
          <div className="flex flex-col gap-3 border-b border-line px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative sm:w-72">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-slate-400" />
              <input className={`${input} pl-8`} placeholder="Search cases" aria-label="Search cases" value={query} onChange={(e) => setQuery(e.target.value)} />
            </div>
            <div role="group" aria-label="Filter by status" className="inline-flex self-start rounded-md border border-line p-0.5 text-sm">
              {FILTERS.map(([key, label]) => (
                <button key={key} aria-pressed={filter === key} onClick={() => setFilter(key)}
                  className={`rounded px-3 py-1 font-medium transition-colors ${filter === key ? 'bg-navy-900 text-white' : 'text-slate-600 hover:text-navy-900'}`}>
                  {label}
                </button>
              ))}
            </div>
          </div>

          {!cases && !error && <div className="space-y-3 p-5">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-8" />)}</div>}
          {shown?.length === 0 && <p className="px-5 py-10 text-center text-sm text-slate-500">No cases match.</p>}

          {shown && shown.length > 0 && (
            <>
              <table className="hidden w-full text-sm md:table">
                <thead className="text-left text-xs text-slate-500">
                  <tr className="border-b border-line">
                    <th className="px-5 py-2.5 font-medium">Case</th>
                    <th className="px-3 py-2.5 font-medium">Status</th>
                    <th className="px-3 py-2.5 text-right font-medium">Claimed</th>
                    <th className="px-3 py-2.5 text-right font-medium">Approved</th>
                    <th className="px-3 py-2.5 text-right font-medium">Settled</th>
                    <th className="px-5 py-2.5 text-right font-medium">Contestable</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {shown.map((c) => (
                    <tr key={c.id} className="group cursor-pointer transition-colors hover:bg-slate-50" onClick={() => navigate(caseLink(c))}>
                      <td className="px-5 py-3">
                        <span className="flex items-center gap-2">
                          <Link to={caseLink(c)} className="font-medium text-navy-900 group-hover:text-violet-700">{c.title}</Link>
                          {c.demo && <DemoTag />}
                        </span>
                        <span className="text-xs text-slate-500">{new Date(c.created_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}</span>
                      </td>
                      <td className="whitespace-nowrap px-3 py-3"><CaseStatus c={c} /></td>
                      <td className="px-3 py-3 text-right"><Amount value={c.claimed_amount} /></td>
                      <td className="px-3 py-3 text-right"><Amount value={c.approved_amount} /></td>
                      <td className="px-3 py-3 text-right"><SettledRatio c={c} /></td>
                      <td className="px-5 py-3 text-right">
                        <Amount value={c.contestable_total} className={Number(c.contestable_total) > 0 ? 'font-medium text-violet-700' : 'text-slate-500'} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <ul className="divide-y divide-line md:hidden">
                {shown.map((c) => (
                  <li key={c.id}>
                    <Link to={caseLink(c)} className="block px-4 py-3.5 transition-colors active:bg-slate-50">
                      <span className="flex items-center gap-2">
                        <span className="min-w-0 truncate font-medium text-navy-900">{c.title}</span>
                        {c.demo && <DemoTag />}
                      </span>
                      <span className="mt-1 flex items-center justify-between gap-3">
                        <CaseStatus c={c} />
                        {c.status === 'audited' && (
                          <span className="text-xs text-slate-500">
                            Contestable <Amount value={c.contestable_total} className="font-medium text-violet-700" />
                          </span>
                        )}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>
      )}
    </div>
  )
}
