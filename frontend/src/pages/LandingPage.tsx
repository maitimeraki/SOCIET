import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { listRunsPage, listUploads } from '../api/rest'
import type { RunSummary } from '../api/types'
import Skeleton from '../components/ui/Skeleton'
import { PAGE_SIZE } from './pageSize'

/**
 * Where a signed-in account belongs when it lands on `/landing` — the state decides, not a fixed
 * home. An account with nothing in it starts at Documents (there is nothing else to do yet);
 * material but no filed answer goes to Runs (the work is in flight, or waiting to be started);
 * any answered run means Verdict is the thing worth reading.
 */
export function landingTarget(uploads: number, runs: RunSummary[]): '/documents' | '/runs' | '/results' {
  if (uploads === 0 && runs.length === 0) return '/documents'
  if (!runs.some((entry) => entry.verdict_stance)) return '/runs'
  return '/results'
}

/**
 * The bare post-auth address (DEFAULT_NEXT): no chrome of its own, just the read that picks the
 * destination. It renders a skeleton rather than the app shell so a mis-aimed default never flashes
 * the rail before the account state is known; a failed read falls back to Documents.
 */
export default function LandingPage() {
  const navigate = useNavigate()
  useEffect(() => {
    let cancelled = false
    Promise.all([listUploads(), listRunsPage({ limit: PAGE_SIZE })])
      .then(([uploads, runs]) => {
        if (!cancelled) navigate(landingTarget((uploads.items ?? []).length, runs.items), { replace: true })
      })
      .catch(() => {
        if (!cancelled) navigate('/documents', { replace: true })
      })
    return () => {
      cancelled = true
    }
  }, [navigate])
  return (
    <div className="p-8">
      <Skeleton className="h-7 w-52" />
    </div>
  )
}
