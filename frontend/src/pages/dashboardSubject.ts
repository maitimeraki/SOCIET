import { listRunsPage } from '../api/rest'
import type { RunListPage, RunSummary } from '../api/types'

/** The v1 keyset page size: one page of 25, then `next_cursor` walks the rest. */
export const SUBJECT_PAGE_SIZE = 25

export type RunPageReader = (options: { limit?: number; cursor?: string | null }) => Promise<RunListPage>

export interface DecisionSubject {
  /** The newest decision that has filed an answer — the subject both sections describe. */
  answered: RunSummary | null
  /** The newest decision of any state; the section names it when it has no answer yet. */
  newest: RunSummary | null
}

/**
 * The newest decision that has filed an answer (§14.3, the 25-run window fix).
 *
 * `verdict_stance` is already in the list payload, so the list alone says whether a decision has
 * answered. Pages are read newest-first and the walk stops at the first answered item — never at
 * the end of the first page — so a 26th (or 260th) decision is not hidden behind a 25-item window.
 * Pure and injectable, so the 26-decision case is unit-tested without a browser.
 */
export async function findDecisionSubject(
  readPage: RunPageReader = listRunsPage,
  limit: number = SUBJECT_PAGE_SIZE,
): Promise<DecisionSubject> {
  let cursor: string | null = null
  let newest: RunSummary | null = null
  for (;;) {
    const page = await readPage({ limit, cursor })
    if (newest === null && page.items.length > 0) newest = page.items[0] ?? null
    const answered = page.items.find((run) => run.verdict_stance !== null)
    if (answered) return { answered, newest }
    if (page.next_cursor === null) return { answered: null, newest }
    cursor = page.next_cursor
  }
}

/**
 * The one walk both "The last answer" and "Your panel" read. The promise is cached for the page's
 * lifetime, so the two sections cannot each pick their own subject out of a changing list; a
 * failure clears the cache so a retry can walk again.
 */
let pending: { epoch: number; promise: Promise<DecisionSubject> } | null = null
let epoch = 0

/**
 * A fresh page mount begins a new epoch, so a subject cached during an earlier visit cannot be
 * served to a later one (a decision filed while the customer was reading a run is the newest
 * answer when they come back). Called from the dashboard's state initializer, before its children
 * mount.
 */
export function beginDecisionSubject(): number {
  epoch += 1
  return epoch
}

export function sharedDecisionSubject(scope: number = epoch): Promise<DecisionSubject> {
  if (pending !== null && pending.epoch === scope) return pending.promise
  const promise = findDecisionSubject().catch((error: unknown) => {
    if (pending?.promise === promise) pending = null
    throw error
  })
  pending = { epoch: scope, promise }
  return promise
}

/** A test seam: the suite starts each case from a clean walk. */
export function resetDecisionSubject(): void {
  pending = null
}
