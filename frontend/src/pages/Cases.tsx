import { FolderOpen, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, type CaseSummary } from '../api'
import { Amount, DemoTag, EmptyState, ErrorNote, PageHeader, Skeleton, btn, input } from '../components/ui'

export const caseLink = (c: CaseSummary) => `/cases/${c.id}${c.status === 'audited' ? '?tab=audit' : ''}`

export function CaseStatus({ c }: { c: Pick<CaseSummary, 'status' | 'documents'> }) {
  return c.status === 'audited' ? (
    <span className="inline-flex items-center gap-1.5 text-[13px] text-ink-2">
      <span aria-hidden className="size-1.5 rounded-full bg-ink" /> Audited
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 text-[13px] text-mute">
      <span aria-hidden className="size-1.5 rounded-full ring-1 ring-inset ring-faint" /> Draft · {c.documents.length} of 3 documents
    </span>
  )
}

const FILTERS = [['all', 'All'], ['audited', 'Audited'], ['draft', 'Draft']] as const
const date = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })

function SettledRatio({ c }: { c: CaseSummary }) {
  const claimed = Number(c.claimed_amount)
  if (!claimed || c.approved_amount === null) return <span className="text-faint">—</span>
  const pct = (Number(c.approved_amount) / claimed) * 100
  return (
    <span className="inline-flex items-center justify-end gap-3">
      <span aria-hidden className="h-1 w-14 overflow-hidden rounded-full bg-tile"><span className="fill-approved block h-full rounded-full" style={{ width: `${Math.min(pct, 100)}%` }} /></span>
      <span className="w-12 text-right tabular-nums text-ink-2">{pct.toFixed(1)}%</span>
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
  const th = 'pb-3 text-[13px] font-medium text-mute'

  return (
    <div className="space-y-10">
      <PageHeader
        title="Case history"
        description="Every claim you have opened, with its settlement outcome and the amount the audit found contestable."
        actions={<Link to="/audit/new" className={btn.primary}>New audit</Link>}
      />
      <ErrorNote error={error} />

      {cases?.length === 0 ? (
        <EmptyState icon={FolderOpen} title="No cases yet"
          actions={<Link to="/audit/new" className={btn.primary}>Start an audit</Link>}>
          Cases appear here once you upload a claim or open the demo.
        </EmptyState>
      ) : (
        <div>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative sm:w-80">
              <Search aria-hidden className="pointer-events-none absolute left-3.5 top-3 size-[18px] text-faint" strokeWidth={1.75} />
              <input type="search" className={`${input} rounded-full pl-10`} placeholder="Search cases" aria-label="Search cases" value={query} onChange={(e) => setQuery(e.target.value)} />
            </div>
            <div role="group" aria-label="Filter by status" className="inline-flex self-start rounded-full bg-tile p-1 text-sm">
              {FILTERS.map(([key, label]) => (
                <button key={key} aria-pressed={filter === key} onClick={() => setFilter(key)}
                  className={`rounded-full px-4 py-1.5 font-medium transition-[background-color,color,box-shadow] duration-200 ${
                    filter === key ? 'bg-paper text-ink shadow-[0_1px_2px_rgb(0_0_0/0.08)]' : 'text-mute hover:text-ink'
                  }`}>
                  {label}
                </button>
              ))}
            </div>
          </div>

          {!cases && !error && <div className="mt-8 space-y-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />)}</div>}
          {shown?.length === 0 && <p className="py-16 text-center text-[17px] text-mute">No cases match.</p>}

          {shown && shown.length > 0 && (
            <>
              <table className="mt-10 hidden w-full text-[15px] md:table">
                <thead className="border-b border-hairline text-left">
                  <tr>
                    <th className={`${th} pl-3`}>Case</th>
                    <th className={th}>Status</th>
                    <th className={`${th} text-right`}>Claimed</th>
                    <th className={`${th} text-right`}>Approved</th>
                    <th className={`${th} text-right`}>Settled</th>
                    <th className={`${th} pr-3 text-right`}>Contestable</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline border-b border-hairline">
                  {shown.map((c) => (
                    <tr key={c.id} className="group cursor-pointer transition-colors duration-200 hover:bg-tile/70" onClick={() => navigate(caseLink(c))}>
                      <td className="py-4 pl-3 pr-4">
                        <span className="flex items-center gap-2">
                          <Link to={caseLink(c)} className="rounded-sm font-medium text-ink">{c.title}</Link>
                          {c.demo && <DemoTag />}
                        </span>
                        <span className="mt-0.5 block text-[13px] text-mute">{date(c.created_at)}</span>
                      </td>
                      <td className="whitespace-nowrap py-4 pr-4"><CaseStatus c={c} /></td>
                      <td className="py-4 pr-4 text-right text-ink-2"><Amount value={c.claimed_amount} /></td>
                      <td className="py-4 pr-4 text-right text-ink-2"><Amount value={c.approved_amount} /></td>
                      <td className="py-4 pr-4 text-right"><SettledRatio c={c} /></td>
                      <td className="py-4 pr-3 text-right">
                        <Amount value={c.contestable_total} className={`type-figure ${Number(c.contestable_total) > 0 ? 'text-accent' : 'text-mute'}`} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <ul className="-mx-5 mt-8 divide-y divide-hairline border-y border-hairline md:hidden">
                {shown.map((c) => (
                  <li key={c.id}>
                    <Link to={caseLink(c)} className="flex items-center gap-4 px-5 py-4 transition-colors active:bg-tile">
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-2">
                          <span className="min-w-0 truncate text-[15px] font-medium text-ink">{c.title}</span>
                          {c.demo && <DemoTag />}
                        </span>
                        <span className="mt-1 flex flex-wrap items-center gap-x-2 text-[13px] text-mute">
                          <CaseStatus c={c} /> <span aria-hidden>·</span> {date(c.created_at)}
                        </span>
                      </span>
                      {c.status === 'audited' && (
                        <span className="shrink-0 text-right">
                          <Amount value={c.contestable_total} className={`type-figure block ${Number(c.contestable_total) > 0 ? 'text-accent' : 'text-mute'}`} />
                          <span className="text-xs text-mute">contestable</span>
                        </span>
                      )}
                    </Link>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  )
}
