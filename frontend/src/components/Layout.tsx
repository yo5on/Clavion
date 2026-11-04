import { Menu, Plus, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import Logo from './Logo'
import { btn } from './ui'

const nav = [
  { to: '/', label: 'Overview', end: true },
  { to: '/audit/new', label: 'New audit' },
  { to: '/cases', label: 'Case history' },
]

export default function Layout() {
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-3 focus:z-[60] focus:rounded-full focus:bg-ink focus:px-4 focus:py-2 focus:text-sm focus:text-white">
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b border-hairline bg-canvas">
        <div className="mx-auto flex h-14 max-w-[1120px] items-center justify-between px-5 sm:px-8">
          <Link to="/" aria-label="Clavion overview" className="-m-1 rounded-md p-1" onClick={() => setOpen(false)}>
            <Logo />
          </Link>
          <nav aria-label="Main" className="hidden items-center gap-8 md:flex">
            {nav.filter((n) => n.to !== '/audit/new').map(({ to, label, end }) => (
              <NavLink key={to} to={to} end={end}
                className={({ isActive }) => `rounded-sm text-sm transition-colors duration-200 ${isActive ? 'text-ink' : 'text-mute hover:text-ink'}`}>
                {label}
              </NavLink>
            ))}
            <Link to="/audit/new" className={`${btn.primarySm} h-8 px-3.5 text-[13px]`}>
              <Plus className="size-3.5" strokeWidth={2.25} /> New audit
            </Link>
          </nav>
          <button className={`${btn.icon} -mr-2 md:hidden`} onClick={() => setOpen((o) => !o)} aria-label={open ? 'Close menu' : 'Open menu'} aria-expanded={open} aria-controls="mobile-nav">
            {open ? <X className="size-5" strokeWidth={1.75} /> : <Menu className="size-5" strokeWidth={1.75} />}
          </button>
        </div>
        {open && (
          <nav id="mobile-nav" aria-label="Main" className="absolute inset-x-0 top-full h-[calc(100dvh-3.5rem)] animate-fade-in bg-canvas px-5 pt-6 sm:px-8 md:hidden">
            <ul className="space-y-1">
              {nav.map(({ to, label, end }) => (
                <li key={to}>
                  <NavLink to={to} end={end} onClick={() => setOpen(false)}
                    className={({ isActive }) => `block py-2 text-[28px] font-semibold tracking-[-0.02em] transition-colors ${isActive ? 'text-ink' : 'text-mute hover:text-ink'}`}>
                    {label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
        )}
      </header>

      <main id="main" key={pathname} className="mx-auto w-full max-w-[1120px] flex-1 animate-page-in px-5 pb-24 sm:px-8">
        <Outlet />
      </main>

      <footer className="border-t border-hairline">
        <p className="mx-auto max-w-[1120px] px-5 py-6 text-xs leading-relaxed text-mute sm:px-8">
          Clavion explains settlements. It does not give legal advice or guarantee recovery.
        </p>
      </footer>
    </div>
  )
}
