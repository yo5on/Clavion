import { FilePlus2, FolderClock, LayoutDashboard, Menu, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import Logo from './Logo'

const nav = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/audit/new', label: 'New audit', icon: FilePlus2 },
  { to: '/cases', label: 'Case history', icon: FolderClock },
]

export default function Layout() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  return (
    <div className="min-h-screen lg:flex">
      <aside
        aria-label="Main navigation"
        className={`fixed inset-y-0 left-0 z-40 flex w-60 flex-col bg-navy-900 text-slate-400 transition-transform duration-200 lg:sticky lg:top-0 lg:h-screen lg:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex h-16 items-center justify-between border-b border-white/5 px-5">
          <Logo />
          <button className="text-slate-400 hover:text-white lg:hidden" onClick={() => setOpen(false)} aria-label="Close menu">
            <X className="size-5" />
          </button>
        </div>
        <nav className="mt-5 space-y-0.5 px-3">
          {nav.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-white/[0.06] text-white before:absolute before:inset-y-1.5 before:-left-3 before:w-0.5 before:rounded-r before:bg-violet-500'
                    : 'hover:bg-white/[0.04] hover:text-slate-100'
                }`
              }
            >
              <Icon className="size-4" strokeWidth={1.75} />
              {label}
            </NavLink>
          ))}
        </nav>
        <p className="mt-auto border-t border-white/5 px-5 py-4 text-xs leading-relaxed text-slate-500">
          Clavion explains settlements. It does not give legal advice or guarantee recovery.
        </p>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-navy-950/50 lg:hidden" onClick={() => setOpen(false)} aria-hidden />}

      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-white/5 bg-navy-900 px-4 lg:hidden">
          <Logo />
          <button className="rounded-md p-1.5 text-slate-300 hover:bg-white/5" onClick={() => setOpen(true)} aria-label="Open menu" aria-expanded={open}>
            <Menu className="size-5" />
          </button>
        </header>
        <main className="mx-auto max-w-[1200px] px-4 py-6 sm:px-8 sm:py-10">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
