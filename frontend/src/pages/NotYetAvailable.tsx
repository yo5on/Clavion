import { Compass } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Card, EmptyState, btn } from '../components/ui'

export default function NotYetAvailable({ title, body }: { title: string; body: string }) {
  return (
    <Card>
      <EmptyState icon={Compass} title={title} actions={<Link to="/" className={btn.secondary}>Back to overview</Link>}>
        {body}
      </EmptyState>
    </Card>
  )
}
