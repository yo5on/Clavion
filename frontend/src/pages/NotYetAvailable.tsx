import { Compass } from 'lucide-react'
import { Link } from 'react-router-dom'
import { EmptyState, btn } from '../components/ui'

export default function NotYetAvailable({ title, body }: { title: string; body: string }) {
  return (
    <div className="pt-12">
      <EmptyState icon={Compass} title={title} actions={<Link to="/" className={btn.primary}>Back to overview</Link>}>
        {body}
      </EmptyState>
    </div>
  )
}
