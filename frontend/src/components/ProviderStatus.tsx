import { useEffect, useState } from 'react'
import { api, type Provider } from '../api'
import { ErrorNote, PROVIDER_STATE, Skeleton } from './ui'

export function useProviders() {
  const [providers, setProviders] = useState<Provider[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    api.providers().then(setProviders).catch((e) => setError(e.message))
  }, [])
  return { providers, setProviders, error }
}

export default function ProviderStatus() {
  const { providers, error } = useProviders()
  return (
    <div>
      <h3 className="type-heading">Analysis providers</h3>
      <div className="mt-4 space-y-3 empty:hidden">
        <ErrorNote error={error} />
        {!providers && !error && [0, 1].map((i) => <Skeleton key={i} className="h-12" />)}
      </div>
      <ul className="mt-2 divide-y divide-hairline">
        {providers?.map((p) => {
          const [label, cls, Icon] = PROVIDER_STATE[p.status.state]
          return (
            <li key={p.id} className="py-4">
              <div className="flex items-baseline justify-between gap-4">
                <span className="text-[15px] font-medium text-ink">{p.label}</span>
                <span className={`flex shrink-0 items-center gap-1.5 text-[13px] font-medium ${cls}`}>
                  <Icon className="size-3.5 translate-y-px" strokeWidth={2} /> {label}
                </span>
              </div>
              {p.status.detail && <p className="mt-1 text-sm leading-relaxed text-mute">{p.status.detail}</p>}
            </li>
          )
        })}
      </ul>
      <p className="mt-2 text-[13px] leading-relaxed text-mute">
        Extraction and auditing are rule-based and run locally. No language model is used.
      </p>
    </div>
  )
}
