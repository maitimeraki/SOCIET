import { Link } from 'react-router-dom'
import { buttonClasses } from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'

/**
 * §8.3 Documents — everything the panel argues from. A brand-new account gets exactly one action, no
 * sample data and no tour. The list of uploaded documents lands in this section's own task, so nothing
 * here pretends a row exists; the section states its own purpose and its one next action.
 */
export default function DocumentsSection() {
  return (
    <div className="space-y-6">
      <h1 className="font-titling text-display text-ink">Documents</h1>
      <EmptyState
        icon={
          <span aria-hidden="true" className="text-title leading-none">
            ⇣
          </span>
        }
        line="Add your first document. Drop a PDF, paste a URL, or connect a source — everything your panel argues from comes from here."
        action={
          <Link to="/new/ingest" className={buttonClasses('primary', 40)}>
            Upload documents
          </Link>
        }
      />
    </div>
  )
}
