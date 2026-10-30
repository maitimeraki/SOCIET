import type { RunSummary, UploadRow } from '../../api/types'

/**
 * §7.8 — the fifth Overview section: the corpora, as a ruled record.
 *
 * The corpus is a first-class object in the product: the customer names it at step 1 and the
 * panel is drawn from it. The stats band reports corpus *size*; this reports corpus *contents*.
 */
export interface CorpusRow {
  name: string
  documents: number
  read: number
  reading: number
  /** The newest run that used this corpus, or null when none has. */
  lastUsed: string | null
}

export function corpusRows(uploads: UploadRow[], runs: RunSummary[]): CorpusRow[] {
  const rows = new Map<string, CorpusRow>()
  for (const upload of uploads) {
    const name = upload.dataset_name
    if (!name) continue
    const row = rows.get(name) ?? { name, documents: 0, read: 0, reading: 0, lastUsed: null }
    row.documents += 1
    if (upload.read) row.read += 1
    else row.reading += 1
    rows.set(name, row)
  }
  for (const run of runs) {
    const name = run.corpus_label
    if (!name) continue
    const row = rows.get(name)
    if (!row) continue
    if (row.lastUsed === null || run.created_at > row.lastUsed) row.lastUsed = run.created_at
  }
  return [...rows.values()].sort((a, b) => a.name.localeCompare(b.name))
}
