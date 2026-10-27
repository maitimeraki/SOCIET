import { useCallback, useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { listRunsPage, listUploads } from '../api/rest'
import type { RunSummary } from '../api/types'
import DocumentsSection from '../sections/DocumentsSection'
import PanelSection from '../sections/PanelSection'
import ResultsSection from '../sections/ResultsSection'
import RunsSection from '../sections/RunsSection'
import DashboardView from './dashboardView'
import { DASHBOARD_ANCHORS, anchorIdFromHash } from './dashboardAnchors'
import { beginDecisionSubject, PAGE_SIZE, sharedDecisionSubject } from './dashboardSubject'

/** The keys that scroll the document. Any of them means the customer has taken over. */
const SCROLL_KEYS = new Set(['ArrowDown', 'ArrowUp', 'PageDown', 'PageUp', 'Home', 'End', ' ', 'Spacebar'])

/** The four sections that must have settled before a deep-linked anchor is scrolled to. */
const SECTION_IDS = [
  DASHBOARD_ANCHORS.material,
  DASHBOARD_ANCHORS.decisions,
  DASHBOARD_ANCHORS.lastAnswer,
  DASHBOARD_ANCHORS.panel,
]

/**
 * Keep a deep-linked section in view while its content settles (§14.3). The four sections fetch
 * independently, so a section above the target can grow after the first scroll; the browser's own
 * hash jump alone lands at the top, which is not the contract. The scroll is `auto` under
 * `prefers-reduced-motion: reduce` and `smooth` otherwise.
 *
 * The observer is a correction, not the scroll. It skips its spec-guaranteed first callback, it
 * stays silent until the initial scroll has had time to finish (a correction mid-animation would
 * cancel the animation in one frame), and it stops for good the moment the customer takes over —
 * a wheel, a touch, or a scroll key. Only content that grows afterwards, while the anchor is still
 * the intent, is re-aligned.
 */
function useAnchorScroll(hash: string, ready: boolean) {
  useEffect(() => {
    if (!ready) return
    const id = anchorIdFromHash(hash)
    if (!id) return
    const target = document.getElementById(id)
    if (!target) return
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    target.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })

    let firstObservation = true
    let correctionsArmed = false
    let userMoved = false
    const stopCorrecting = () => {
      userMoved = true
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (SCROLL_KEYS.has(event.key)) userMoved = true
    }
    // A plain `scroll` listener cannot tell our own scrollIntoView from the customer's, so the
    // intent is read from the inputs that move a document.
    window.addEventListener('wheel', stopCorrecting, { passive: true, once: true })
    window.addEventListener('touchmove', stopCorrecting, { passive: true, once: true })
    window.addEventListener('keydown', onKeyDown)

    const observer = new ResizeObserver(() => {
      if (firstObservation) {
        firstObservation = false
        return
      }
      if (!correctionsArmed || userMoved) return
      target.scrollIntoView({ behavior: 'auto', block: 'start' })
    })
    observer.observe(document.body)
    // The smooth animation outlasts the fetch-driven resize burst; arm corrections once it is done.
    const arm = window.setTimeout(() => {
      correctionsArmed = true
    }, reduce ? 120 : 700)
    const timer = window.setTimeout(() => observer.disconnect(), 1500)
    return () => {
      observer.disconnect()
      window.clearTimeout(arm)
      window.clearTimeout(timer)
      window.removeEventListener('wheel', stopCorrecting)
      window.removeEventListener('touchmove', stopCorrecting)
      window.removeEventListener('keydown', onKeyDown)
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
  // The anchor scroll waits for the sections' own first reads, not just the page probe: a section
  // above the target must have its final height before the target is scrolled to.
  const [readySections, setReadySections] = useState<ReadonlySet<string>>(() => new Set())
  const markReady = useCallback((id: string) => {
    setReadySections((previous) => (previous.has(id) ? previous : new Set(previous).add(id)))
  }, [])
  const materialSettled = useCallback(() => markReady(DASHBOARD_ANCHORS.material), [markReady])
  const decisionsSettled = useCallback(() => markReady(DASHBOARD_ANCHORS.decisions), [markReady])
  const lastAnswerSettled = useCallback(() => markReady(DASHBOARD_ANCHORS.lastAnswer), [markReady])
  const panelSettled = useCallback(() => markReady(DASHBOARD_ANCHORS.panel), [markReady])

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
          setAccountEmpty((uploads.value.items ?? []).length === 0 && runs.value.items.length === 0)
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

  const ready = settled && (accountEmpty || SECTION_IDS.every((id) => readySections.has(id)))
  useAnchorScroll(hash, ready)

  // One retry refreshes the whole surface (§14.3's ERROR row): every section re-reads, and the
  // subject walk starts over because the failed read cleared its cache.
  const refresh = useCallback(() => setRefreshKey((key) => key + 1), [])

  return (
    <DashboardView
      accountEmpty={accountEmpty}
      live={live ? { runId: live.run_id, question: live.query } : null}
      material={
        <DocumentsSection refreshKey={refreshKey} onRefresh={refresh} onSettled={materialSettled} />
      }
      decisions={
        <RunsSection refreshKey={refreshKey} onRefresh={refresh} onSettled={decisionsSettled} />
      }
      lastAnswer={
        <ResultsSection
          refreshKey={refreshKey}
          onRefresh={refresh}
          subjectEpoch={subjectEpoch}
          onSettled={lastAnswerSettled}
        />
      }
      panel={
        <PanelSection
          refreshKey={refreshKey}
          onRefresh={refresh}
          subjectEpoch={subjectEpoch}
          onSettled={panelSettled}
        />
      }
    />
  )
}
