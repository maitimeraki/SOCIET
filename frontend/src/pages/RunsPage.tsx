import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { listRunsPage } from '../api/rest'
import type { RunSummary } from '../api/types'
import RunTable from '../components/common/RunTable'
import EmptyState from '../components/ui/EmptyState'
import Input from '../components/ui/Input'
import Select from '../components/ui/Select'
import Button from '../components/ui/Button'
import { toast } from '../components/ui/Toast'

export type StatusFilter = 'all' | 'complete' | 'running' | 'failed' | 'interrupted'

/** The list's client-side filter — pure, so it is testable without a DOM (this suite is node-only). */
// eslint-disable-next-line react-refresh/only-export-components -- filterRuns is the page's pure filter, shared with its test
export function filterRuns(runs: RunSummary[], status: StatusFilter, text: string): RunSummary[] {
  const needle = text.trim().toLowerCase()
  return runs.filter((run) => {
    const statusOk =
      status === 'all' ||
      (status === 'running' ? run.status === 'running' || run.status === 'queued' : run.status === status)
    const textOk = needle.length === 0 || run.query.toLowerCase().includes(needle)
    return statusOk && textOk
  })
}

const PAGE_SIZE = 25

export default function RunsPage() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [failed, setFailed] = useState(false)
  const [status, setStatus] = useState<StatusFilter>('all')
  const [text, setText] = useState('')

  useEffect(() => {
    listRunsPage({ limit: PAGE_SIZE })
      .then((page) => {
        setRuns(page.items)
        setCursor(page.next_cursor)
      })
      .catch(() => setFailed(true))
      .finally(() => setLoading(false))
  }, [])

  const loadMore = async () => {
    if (!cursor) return
    setLoadingMore(true)
    try {
      const page = await listRunsPage({ limit: PAGE_SIZE, cursor })
      setRuns((previous) => [...previous, ...page.items])
      setCursor(page.next_cursor)
    } catch (error) {
      toast('error', error instanceof Error ? error.message : "Couldn't load more runs")
    } finally {
      setLoadingMore(false)
    }
  }

  const filtered = useMemo(() => filterRuns(runs, status, text), [runs, status, text])

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h1 className="font-titling text-display text-ink">Runs</h1>
        <Link to="/new/ingest" className="text-body text-datum hover:text-datum">
          Convene a society →
        </Link>
      </div>

      <div className="flex items-center gap-3">
        <Select value={status} onChange={(event) => setStatus(event.target.value as StatusFilter)} aria-label="Filter by status">
          <option value="all">All statuses</option>
          <option value="complete">Complete</option>
          <option value="running">Running</option>
          <option value="failed">Failed</option>
          <option value="interrupted">Interrupted</option>
        </Select>
        <Input
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Filter by question"
          aria-label="Filter by question"
          className="max-w-[320px]"
        />
      </div>

      {loading ? (
        <RunTable runs={[]} loading />
      ) : failed ? (
        <p className="text-body text-ink-2">Couldn't reach the server — the run history loads when it's back.</p>
      ) : filtered.length === 0 ? (
        <EmptyState line={runs.length === 0 ? 'No runs yet. Convene your first society →' : 'No runs match this filter.'} />
      ) : (
        <>
          <RunTable runs={filtered} />
          {cursor !== null && (
            <div className="flex justify-center pt-2">
              <Button onClick={loadMore} loading={loadingMore}>
                Load more
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
