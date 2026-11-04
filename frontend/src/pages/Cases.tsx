import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, rupees, type CaseSummary } from '../api'
import { Card, ErrorNote, Spinner, btn } from '../components/ui'

export default function Cases() {
  const [cases, setCases] = useState<CaseSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    api.cases().then(setCases).catch((e) => setError(e.message))
  }, [])

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-3">
        <h1 className="text-2xl font-semibold text-navy-900">Case history</h1>
        <Link to="/audit/new" className={btn.primary}>New audit</Link>
      </div>
      <ErrorNote error={error} />
      {!cases && !error && <Spinner label="Loading…" />}
      {cases?.length === 0 && <Card><p className="text-sm text-slate-500">No cases yet.</p></Card>}
      {cases && cases.length > 0 && (
        <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="bg-surface text-left text-xs font-medium text-slate-500">
              <tr>
                <th className="px-4 py-2.5">Case</th>
                <th className="px-4 py-2.5">Created</th>
                <th className="px-4 py-2.5">Status</th>
                <th className="px-4 py-2.5 text-right">Claimed</th>
                <th className="px-4 py-2.5 text-right">Approved</th>
                <th className="px-4 py-2.5 text-right">Contestable</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {cases.map((c) => (
                <tr key={c.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link to={`/cases/${c.id}${c.status === 'audited' ? '?tab=audit' : ''}`} className="font-medium text-navy-900 hover:text-violet-700">
                      {c.title}
                    </Link>
                    {c.demo && <span className="ml-2 rounded bg-amber-50 px-1.5 py-0.5 text-xs text-amber-800">demo</span>}
                  </td>
                  <td className="px-4 py-3 text-slate-500">{new Date(c.created_at).toLocaleDateString()}</td>
                  <td className="px-4 py-3 text-slate-600">{c.status === 'audited' ? 'Audited' : `Draft · ${c.documents.length}/3 docs`}</td>
                  <td className="px-4 py-3 text-right">{rupees(c.claimed_amount)}</td>
                  <td className="px-4 py-3 text-right">{rupees(c.approved_amount)}</td>
                  <td className="px-4 py-3 text-right font-medium text-violet-700">{rupees(c.contestable_total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
