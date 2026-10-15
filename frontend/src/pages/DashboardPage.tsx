import { Link } from 'react-router-dom'
import { buttonClasses } from '../components/ui/Button'

/**
 * The operate home (plan §1). Placeholder for Task 15c: it exists so a successful sign-in has a
 * destination and `/dashboard` is not NotFound. Task 16 replaces it with the real DashboardPage
 * (recent runs, the convene action, system health).
 */
export default function DashboardPage() {
  return (
    <div className="space-y-5">
      <h1 className="font-titling text-title text-ink">Dashboard</h1>
      <p className="max-w-[60ch] text-body text-ink-2">
        The operate home lands here — recent runs, the convene action and system health. For now, start
        a society or reopen a finished one.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <Link to="/new/ingest" className={buttonClasses('primary', 40)}>
          Convene a society
        </Link>
        <Link to="/runs" className={buttonClasses('ghost', 40)}>
          Reopen a run
        </Link>
      </div>
    </div>
  )
}
