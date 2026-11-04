import { RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, type Provider } from '../api'
import { Card, ErrorNote, PROVIDER_STATE, Spinner, btn } from './ui'

export function useProviders() {
  const [providers, setProviders] = useState<Provider[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    api.providers().then(setProviders).catch((e) => setError(e.message))
  }, [])
  return { providers, setProviders, error }
}

export default function ProviderStatus() {
  const { providers, setProviders, error } = useProviders()
  const [checking, setChecking] = useState(false)
  const [checkError, setCheckError] = useState<string | null>(null)

  async function check() {
    setChecking(true)
    setCheckError(null)
    try {
      const bc = await api.checkBharatCode()
      setProviders((ps) => ps && ps.map((p) => (p.id === bc.id ? bc : p)))
    } catch (e) {
      setCheckError((e as Error).message)
    } finally {
      setChecking(false)
    }
  }

  return (
    <Card title="Analysis providers">
      <ErrorNote error={error ?? checkError} />
      {!providers && !error && <Spinner label="Loading…" />}
      <ul className="space-y-4">
        {providers?.map((p) => {
          const [label, cls, Icon] = PROVIDER_STATE[p.status.state]
          return (
            <li key={p.id} className="text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="font-medium text-slate-800">{p.label}</span>
                <span className={`flex items-center gap-1.5 text-xs font-medium ${cls}`}>
                  <Icon className="size-4" /> {label}
                </span>
              </div>
              <p className="mt-0.5 text-xs text-slate-500">
                {p.status.detail}
                {p.status.checked_at && ` Last checked ${new Date(p.status.checked_at).toLocaleString()}.`}
              </p>
              {p.id === 'bharatcode' && p.status.state !== 'not_configured' && (
                <button className={`${btn.ghost} mt-1`} onClick={check} disabled={checking}>
                  <RefreshCw className={`size-3.5 ${checking ? 'animate-spin' : ''}`} /> Check connection
                </button>
              )}
            </li>
          )
        })}
      </ul>
      <p className="mt-4 border-t border-slate-100 pt-3 text-xs leading-relaxed text-slate-500">
        All audits currently run on local deterministic rules. No result is presented as BharatCode inference unless
        a live BharatCode call actually produced it.
      </p>
    </Card>
  )
}
