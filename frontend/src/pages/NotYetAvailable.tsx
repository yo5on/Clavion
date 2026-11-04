import { Construction } from 'lucide-react'

export default function NotYetAvailable({ title, body }: { title: string; body: string }) {
  return (
    <div>
      <h1 className="text-2xl font-semibold text-navy-900">{title}</h1>
      <div className="mt-6 flex flex-col items-center rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
        <Construction className="size-8 text-violet-500" />
        <p className="mt-4 max-w-sm text-sm text-slate-600">{body}</p>
      </div>
    </div>
  )
}
