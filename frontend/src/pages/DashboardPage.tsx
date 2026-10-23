import { useCallback, useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { listRunsPage, listUploads } from '../api/rest'
import type { RunSummary } from '../api/types'
import DocumentsSection from '../sections/DocumentsSection'
import PanelSection from '../sections/PanelSection'
import ResultsSection from '../sections/ResultsSection'
import RunsSection from '../sections/RunsSection'
import DashboardView from './dashboardView'
import { beginDecisionSubject, sharedDecisionSubject } from './dashboardSubject'

/** The v1 page size: one keyset page of 25, the same page every section's first read uses. */
const PAGE_SIZE = 25

/**
 * Keep a deep-linked section in view while its content settles (§14.3). The four sections fetch
 * independently, so a section above the target can grow after the first scroll; the browser's own
 * hash jump alone lands at the top, which is not the contract. The scroll is `auto` under
 * `prefers-reduced-motion: reduce` and `smooth` otherwise. The observer stays just long enough for
 * the page to stop moving and then lets go.
 */
function useAnchorScroll(hash: string, ready: boolean) {
  useEffect(() => {
    if (!ready) return
    const id = decodeURIComponent(hash.replace(/^#/, ''))
    if (!id) return
    const target = document.getElementById(id)
    if (!target) return
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    target.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
    const observer = new ResizeObserver(() => {
      target.scrollIntoView({ behavior: 'auto', block: 'start' })
    })
    observer.observe(document.body)
    const timer = window.setTimeout(() => observer.disconnect(), 1500)
    return () => {
      observer.disconnect()
      window.clearTimeout(timer)
    }
  }, [hash, ready])
}

/**
 * The dashboard (§14.3, D1): the account's one surface. It renders the four sections in the
 * lifecycle's order and owns only what the page itself needs — whether the whole account is empty,
 * the running decision for the one-line live band, one refresh for the whole surface, and the
 * anchor scroll. Each section owns its own fetch.
 */
export default function DashboardPage() {
  const { hash } = useLocation()
  // A fresh visit begins a fresh subject walk; the sections share this epoch.
  const [subjectEpoch] = useState(beginDecisionSubject)
  const [live, setLive] = useState<RunSummary | null>(null)
  const [accountEmpty, setAccountEmpty] = useState(false)
  const [settled, setSettled] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    // The account's emptiness and the live decision are page-level facts. The subject walk is
    // started here too (and cached), so the first anchor scroll waits for the answer's subject
    // rather than for a skeleton that is about to change height.
    Promise.allSettled([
      listUploads(),
      listRunsPage({ limit: PAGE_SIZE }),
      sharedDecisionSubject(subjectEpoch),
    ]).then(
      ([uploads, runs]) => {
        if (cancelled) return
        if (uploads.status === 'fulfilled' && runs.status === 'fulfilled') {
          setAccountEmpty(uploads.value.items.length === 0 && runs.value.items.length === 0)
        }
        if (runs.status === 'fulfilled') {
          setLive(runs.value.items.find((run) => run.status === 'running') ?? null)
        }
        for (const result of [uploads, runs]) {
          if (result.status === 'rejected') {
            // The sections surface their own failures; the page probe must not swallow its own.
            console.error('DashboardPage: could not read the account state.', result.reason)
          }
        }
        setSettled(true)
      },
    )
    return () => {
      cancelled = true
    }
  }, [refreshKey, subjectEpoch])

  useAnchorScroll(hash, settled)

  // One retry refreshes the whole surface (§14.3's ERROR row): every section re-reads, and the
  // subject walk starts over because the failed read cleared its cache.
  const refresh = useCallback(() => setRefreshKey((key) => key + 1), [])

  return (
    <DashboardView
      accountEmpty={accountEmpty}
      live={live ? { runId: live.run_id, question: live.query } : null}
      material={<DocumentsSection refreshKey={refreshKey} onRefresh={refresh} />}
      decisions={<RunsSection refreshKey={refreshKey} onRefresh={refresh} />}
      lastAnswer={
        <ResultsSection refreshKey={refreshKey} onRefresh={refresh} subjectEpoch={subjectEpoch} />
      }
      panel={<PanelSection refreshKey={refreshKey} onRefresh={refresh} subjectEpoch={subjectEpoch} />}
    />
  )
}
