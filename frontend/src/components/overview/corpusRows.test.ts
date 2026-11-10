import { describe, expect, it } from 'vitest'
import { corpusRows } from './corpusRows'
import type { UploadRow } from '../../api/types'
import type { RunSummary } from '../../api/types'

const upload = (over: Partial<UploadRow>): UploadRow => ({
  id: 'u1',
  name: 'lease.pdf',
  bytes: 100,
  mime: 'application/pdf',
  read: true,
  dataset_id: 'ds-1',
  dataset_name: 'Mill Street expansion',
  created_at: '2026-10-01T10:00:00+00:00',
  ...over,
})

const run = (over: Partial<RunSummary>): RunSummary => ({
  run_id: 'r1',
  created_at: '2026-10-02T10:00:00+00:00',
  query: 'q',
  corpus_label: 'Mill Street expansion',
  dataset_id: 'ds-1',
  status: 'complete',
  rounds_executed: 4,
  converged: true,
  verdict_stance: 'NEGATIVE',
  verdict_confidence: 0.82,
  ...over,
})

describe('the corpora behind the panel', () => {
  it('counts the documents and the reads per corpus', () => {
    const rows = corpusRows(
      [
        upload({ id: 'u1' }),
        upload({ id: 'u2', read: false }),
        upload({ id: 'u3', dataset_name: 'Alder Lane', dataset_id: 'ds-2' }),
      ],
      [],
    )
    expect(rows).toHaveLength(2)
    const mill = rows.find((row) => row.name === 'Mill Street expansion')!
    expect(mill.documents).toBe(2)
    expect(mill.read).toBe(1)
    expect(mill.reading).toBe(1)
  })

  it('names the date the corpus was last used, from the runs', () => {
    const rows = corpusRows([upload({})], [run({ created_at: '2026-10-22T09:00:00+00:00' })])
    expect(rows[0].lastUsed).toBe('2026-10-22T09:00:00+00:00')
  })

  it('leaves a corpus with no run without a date', () => {
    const rows = corpusRows([upload({})], [])
    expect(rows[0].lastUsed).toBeNull()
  })

  it('does not invent a corpus for documents that joined none', () => {
    expect(corpusRows([upload({ dataset_name: null, dataset_id: null })], [])).toEqual([])
  })
})
