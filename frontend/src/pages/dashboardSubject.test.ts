/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { RunListPage, RunSummary } from '../api/types'
import {
  beginDecisionSubject,
  findDecisionSubject,
  resetDecisionSubject,
  sharedDecisionSubject,
  SUBJECT_PAGE_SIZE,
} from './dashboardSubject'
import type { RunPageReader } from './dashboardSubject'

afterEach(() => {
  vi.unstubAllGlobals()
  resetDecisionSubject()
})

const run = (index: number, patch: Partial<RunSummary> = {}): RunSummary => ({
  run_id: `r${index}`,
  created_at: '2026-10-01T10:00:00Z',
  query: `Question ${index}?`,
  corpus_label: null,
  dataset_id: 'ds-1',
  status: 'complete',
  rounds_executed: 1,
  converged: true,
  verdict_stance: null,
  ...patch,
})

/** A reader over fixed pages that records each call — no network, no browser. */
function pagesReader(pages: RunListPage[]): { read: RunPageReader; calls: { limit?: number; cursor?: string | null }[] } {
  const calls: { limit?: number; cursor?: string | null }[] = []
  const read: RunPageReader = async (options) => {
    calls.push(options)
    const page = pages[calls.length - 1]
    if (!page) throw new Error('read past the fixture')
    return page
  }
  return { read, calls }
}

/** 26 decisions, newest first, as the API orders them. */
const twentySix = (answers: number[]): RunSummary[] =>
  Array.from({ length: 26 }, (_, index) =>
    run(index, {
      status: index === 0 ? 'running' : 'complete',
      verdict_stance: answers.includes(index) ? 'POSITIVE' : null,
    }),
  )

describe('findDecisionSubject — the newest decision that filed an answer', () => {
  it('takes the newest answered decision, not the newest decision', async () => {
    const decisions = twentySix([1]) // newest is still deliberating; the second newest answered
    const { read } = pagesReader([
      { items: decisions.slice(0, 25), next_cursor: 'page-2' },
      { items: decisions.slice(25), next_cursor: null },
    ])

    const subject = await findDecisionSubject(read)
    expect(subject.newest?.run_id).toBe('r0')
    expect(subject.answered?.run_id).toBe('r1')
  })

  it('walks past the first 25-item page — the subject is never "the newest inside a window"', async () => {
    const decisions = twentySix([25]) // only the 26th decision has filed an answer
    const { read, calls } = pagesReader([
      { items: decisions.slice(0, 25), next_cursor: 'page-2' },
      { items: decisions.slice(25), next_cursor: null },
    ])

    const subject = await findDecisionSubject(read)
    expect(subject.answered?.run_id).toBe('r25')
    expect(calls).toHaveLength(2)
    expect(calls[0]).toEqual({ limit: SUBJECT_PAGE_SIZE, cursor: null })
    expect(calls[1]).toEqual({ limit: SUBJECT_PAGE_SIZE, cursor: 'page-2' })
  })

  it('reads every page when no decision has answered, and names the newest', async () => {
    const decisions = twentySix([])
    const { read, calls } = pagesReader([
      { items: decisions.slice(0, 25), next_cursor: 'page-2' },
      { items: decisions.slice(25), next_cursor: null },
    ])

    const subject = await findDecisionSubject(read)
    expect(subject.answered).toBeNull()
    expect(subject.newest?.run_id).toBe('r0')
    expect(calls).toHaveLength(2)
  })

  it('returns two nulls for an account with no decisions', async () => {
    const { read, calls } = pagesReader([{ items: [], next_cursor: null }])
    const subject = await findDecisionSubject(read)
    expect(subject).toEqual({ answered: null, newest: null })
    expect(calls).toHaveLength(1)
  })

  it('is fixed at the v1 page size of 25', () => {
    expect(SUBJECT_PAGE_SIZE).toBe(25)
  })
})

describe('sharedDecisionSubject — one subject for The last answer and Your panel', () => {
  it('both sections receive the same, newest answered decision from one walk', async () => {
    const decisions = twentySix([1])
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: decisions.slice(0, 25), next_cursor: 'page-2' })),
    )
    vi.stubGlobal('fetch', fetchMock)
    resetDecisionSubject()

    const [lastAnswer, panel] = await Promise.all([sharedDecisionSubject(), sharedDecisionSubject()])

    expect(lastAnswer.answered?.run_id).toBe('r1')
    expect(panel.answered?.run_id).toBe('r1')
    expect(panel.answered).toBe(lastAnswer.answered) // the same object, not two walks that agree
    // One walk, one request: the shared promise is what makes the two sections one subject.
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('both sections take the subject from the one shared walk, never their own newest pick', () => {
    for (const file of ['src/sections/ResultsSection.tsx', 'src/sections/PanelSection.tsx']) {
      const source = readFileSync(file, 'utf8')
      expect(source, file).toContain('sharedDecisionSubject')
      // The 25-item helper and its window are gone from both sections.
      expect(source, file).not.toContain('listRuns(')
    }
  })

  it('a fresh visit begins a fresh walk — a later epoch is never served an earlier subject', async () => {
    const decisions = twentySix([1])
    const fetchMock = vi
      .fn()
      .mockImplementation(
        async () => new Response(JSON.stringify({ items: decisions.slice(0, 25), next_cursor: null })),
      )
    vi.stubGlobal('fetch', fetchMock)
    resetDecisionSubject()

    const first = await sharedDecisionSubject(beginDecisionSubject())
    const second = await sharedDecisionSubject(beginDecisionSubject())

    expect(first.answered?.run_id).toBe('r1')
    expect(second.answered?.run_id).toBe('r1')
    expect(fetchMock).toHaveBeenCalledTimes(2) // two visits, two walks
  })

  it('a failure clears the cache so a retry walks again', async () => {
    const decisions = twentySix([1])
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'the list is unavailable' }), { status: 500 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: decisions.slice(0, 25), next_cursor: null })))
    vi.stubGlobal('fetch', fetchMock)
    resetDecisionSubject()

    await expect(sharedDecisionSubject()).rejects.toThrow('the list is unavailable')
    const subject = await sharedDecisionSubject()
    expect(subject.answered?.run_id).toBe('r1')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
