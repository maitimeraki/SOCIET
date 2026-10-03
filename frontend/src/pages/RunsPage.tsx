import { useEffect, useMemo, useState } from 'react'
import { listRuns } from '../api/rest'
import type { RunSummary } from '../api/types'
import RunTable from '../components/common/RunTable'
import EmptyState from '../components/ui/EmptyState'
import Input from '../components/ui/Input'
import Select from '../components/ui/Select'
import { Link } from 'react-router-dom'

type StatusFilter = 'all' | 'complete' | 'running' | 'failed' | 'interrupted'

export default function RunsPage() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [status, setStatus] = useState<StatusFilter>('all')
  const [text, setText] = useState('')

  useEffect(() => {
    listRuns()
      .then(setRuns)
      .catch(() => setFailed(true))
      .finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(
    () =>
      runs.filter((run) => {
        const statusOk =
          status === 'all' ||
          (status === 'running' ? run.status === 'running' || run.status === 'queued' : run.status === status)
        const textOk = text.trim().length === 0 || run.query.toLowerCase().includes(text.trim().toLowerCase())
        return statusOk && textOk
      }),
    [runs, status, text],
  )

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h1 className="font-serif text-display text-paper">Runs</h1>
        <Link to="/new/ingest" className="text-body text-accent hover:text-accent-strong">
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
        <p className="text-body text-paper-dim">Couldn't reach the server — the run history loads when it's back.</p>
      ) : filtered.length === 0 ? (
        <EmptyState line={runs.length === 0 ? 'No runs yet. Convene your first society →' : 'No runs match this filter.'} />
      ) : (
        <RunTable runs={filtered} />
      )}
    </div>
  )
}
