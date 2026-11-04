import { Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, type CaseDetail, type CaseSummary, type Health, type LLMHealth } from '../api'
import { SettlementSummary } from '../components/AuditView'
import ProviderStatus from '../components/ProviderStatus'
import { Amount, Chevron, DemoTag, ErrorNote, Section, Skeleton, btn, caption } from '../components/ui'
import { CaseStatus, caseLink } from './Cases'

const STEPS: [string, string][] = [
  ['Upload the documents.', 'Hospital bill, policy wording and the insurer’s settlement letter. PDFs and scans both work.'],
  ['Review what was read.', 'Every field and line item is editable. Correct anything the reader got wrong before the audit runs.'],
  ['Audit, then appeal.', 'Each deduction is checked against the policy and the bill, with evidence. Export the report and a draft appeal.'],
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
    <div className="space-y-16 sm:space-y-24">
      <header className="mx-auto max-w-3xl pt-16 text-center sm:pt-28">
        <h1 className="type-display">Every deduction,<br />explained.</h1>
        <p className="type-lead mx-auto mt-6 max-w-xl">
          Clavion checks a health-insurance settlement line by line against your policy and hospital bill, and shows
          exactly what the documents do not support.
        </p>
        <div className="mt-10 flex flex-col items-center justify-center gap-x-8 gap-y-5 sm:flex-row">
          <Link to="/audit/new" className={btn.primary}>Start an audit</Link>
          <button className={btn.link} onClick={demo} disabled={loadingDemo}>
            {loadingDemo && <Loader2 className="mr-1 size-4 animate-spin" />}
            Open the demo claim <Chevron />
          </button>
        </div>
      </header>

      <ErrorNote error={error} />

      {(!cases || hasAudit) && (
        <Section
          title="Latest audit"
          action={latest && (
            <Link to={`/cases/${latest.id}?tab=audit`} className={btn.link}>Open findings <Chevron /></Link>
          )}
        >
          {latest?.audit ? (
            <>
              <p className="mb-8 flex flex-wrap items-center gap-x-2 gap-y-1 text-[15px] text-mute">
                <span className="font-medium text-ink">{latest.title}</span>
                {latest.demo && <DemoTag />}
                <span aria-hidden>·</span>
                <span>{new Date(latest.audit.generated_at).toLocaleDateString(undefined, { dateStyle: 'medium' })}</span>
              </p>
              <SettlementSummary audit={latest.audit} />
            </>
          ) : (
            <div className="space-y-6" aria-busy>
              <Skeleton className="h-5 w-64" />
              <div className="grid grid-cols-2 gap-6 md:grid-cols-4">
                {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />)}
              </div>
              <Skeleton className="h-2.5 rounded-full" />
            </div>
          )}
        </Section>
      )}

      <Section title="How an audit works">
        <ol className="grid gap-10 md:grid-cols-3 md:gap-12">
          {STEPS.map(([title, body], i) => (
            <li key={title}>
              <span aria-hidden className="type-figure block text-[40px] leading-none text-faint">{i + 1}</span>
              <p className="type-heading mt-5">{title}</p>
              <p className="mt-2 text-[15px] leading-relaxed text-mute">{body}</p>
            </li>
          ))}
        </ol>
      </Section>

      <Section title="Recent cases" action={<Link to="/cases" className={btn.link}>All cases <Chevron /></Link>}>
        {!cases && !error && <div className="space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-14" />)}</div>}
        {cases?.length === 0 && (
          <p className="py-8 text-[17px] text-mute">
            No cases yet. <Link to="/audit/new" className={btn.link}>Start your first audit <Chevron /></Link>
          </p>
        )}
        {cases && cases.length > 0 && (
          <ul className="-mx-4 divide-y divide-hairline border-y border-hairline sm:mx-0">
            {cases.slice(0, 5).map((c) => (
              <li key={c.id}>
                <Link to={caseLink(c)} className="group flex items-center gap-6 px-4 py-4 transition-colors duration-200 hover:bg-tile/70 sm:px-3">
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="truncate text-[15px] font-medium text-ink">{c.title}</span>
                      {c.demo && <DemoTag />}
                    </span>
                    <span className="mt-1 block"><CaseStatus c={c} /></span>
                  </span>
                  <span className="shrink-0 text-right">
                    {c.status === 'audited' ? (
                      <>
                        <Amount value={c.contestable_total} className={`type-figure block text-[17px] ${Number(c.contestable_total) > 0 ? 'text-accent' : 'text-mute'}`} />
                        <span className="text-xs text-mute">contestable</span>
                      </>
                    ) : (
                      <span className="text-sm text-mute">Not audited</span>
                    )}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="System status">
        <div className="grid gap-12 lg:grid-cols-2 lg:gap-16">
          <ProviderStatus />
          <SystemStatus />
        </div>
      </Section>
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
      <h3 className="type-heading">Services</h3>
      <ul className="mt-2 divide-y divide-hairline">
        {rows.map(([label, ok, note]) => (
          <li key={label} className="flex items-center justify-between gap-4 py-4 text-[15px]">
            <span className="text-ink">{label}</span>
            <span className="flex items-center gap-2.5 text-[13px] text-mute">
              {note && <span>{note}</span>}
              <span className={ok === null ? '' : ok ? 'text-ok' : 'text-alert'}>{ok === null ? 'Checking…' : ok ? 'OK' : 'Failed'}</span>
              <span aria-hidden className={`size-2 rounded-full ${ok === null ? 'animate-pulse bg-hairline-strong' : ok ? 'bg-ok' : 'bg-alert'}`} />
            </span>
          </li>
        ))}
      </ul>
      <p className={`${caption} mt-2 font-normal leading-relaxed`}>
        Catalog reachability is not inference: only a successful live check marks BharatCode as connected.
      </p>
    </div>
  )
}
