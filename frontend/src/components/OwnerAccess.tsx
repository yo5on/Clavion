import { useEffect, useState, type ReactNode } from 'react'
import { api, type OwnerSession } from '../api'
import { createSessionRefresh } from '../owner-session'
import Logo from './Logo'
import { btn, ErrorNote, Field, input, Spinner } from './ui'

export default function OwnerAccess({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<OwnerSession | null>(null)
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const [sessionRefresh] = useState(() => createSessionRefresh((current) => {
    setSession(current)
    setError(null)
  }, (error) => setError(error.message)))

  useEffect(() => {
    void sessionRefresh.refresh()
    const expired = () => {
      sessionRefresh.invalidate()
      setSession({ enabled: true, authenticated: false })
      setPassword('')
    }
    window.addEventListener('clavion-auth-required', expired)
    return () => {
      sessionRefresh.invalidate()
      window.removeEventListener('clavion-auth-required', expired)
    }
  }, [sessionRefresh])

  if (!session || !session.authenticated) return (
    <main className="mx-auto max-w-sm space-y-6 px-5 py-16">
      <Logo />
      <ErrorNote error={error} />
      {!session ? (error ? <button className={btn.secondary} onClick={() => void sessionRefresh.refresh()}>Retry connection</button>
        : <Spinner label="Connecting to Clavion" />) : (
        <form className="space-y-5" onSubmit={async (e) => {
          e.preventDefault()
          sessionRefresh.invalidate()
          setBusy(true)
          setError(null)
          try {
            await api.login(password)
            setPassword('')
            const current = await api.authStatus()
            if (!current.authenticated) throw new Error('Session cookie was blocked. Check HTTPS and cookie settings.')
            setSession(current)
          } catch (e) { setError((e as Error).message) }
          finally { setBusy(false); setPassword('') }
        }}>
          <h1 className="type-title">Owner sign in</h1>
          <Field label="Password">
            <input className={input} type="password" autoComplete="current-password" required maxLength={1024}
              value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <button className={btn.primary} disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        </form>
      )}
    </main>
  )

  return <>
    {session.enabled && <div className="mx-auto flex max-w-[1120px] items-center justify-end gap-3 px-5 py-2 sm:px-8">
      <ErrorNote error={error} />
      <button className={btn.linkSm} disabled={busy} onClick={async () => {
        sessionRefresh.invalidate()
        setBusy(true)
        setError(null)
        try { await api.logout(); setSession({ enabled: true, authenticated: false }) }
        catch (e) { setError((e as Error).message) }
        finally { setBusy(false) }
      }}>Sign out</button>
    </div>}
    {children}
  </>
}
