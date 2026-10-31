import { Link } from 'react-router-dom'
import { inlineLinkClasses } from '../ui/Button'
import type { CorpusRow } from './corpusRows'

/**
 * §7.8 — the fifth section. The corpora, as a ruled record: two or three of them do not need a
 * card each, and a card around a single line is noise. A corpus with nothing still reading is a
 * finished corpus; one with a document still reading is the reason the last answer took as long
 * as it did.
 */
export default function YourMaterial({ rows }: { rows: CorpusRow[] }) {
  return (
    <div className="mt-6 overflow-hidden rounded-lg bg-paper shadow-card">
      <div className="flex items-end justify-between gap-4 border-b border-hairline px-6 py-5">
        <div>
          <p className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">Your material</p>
          <h2 className="font-display text-title font-medium tracking-[-0.02em] text-ink">What the panel argues from</h2>
        </div>
        <Link to="/documents" className={`${inlineLinkClasses} font-ui text-body-sm text-accent underline underline-offset-4`}>
          Add material
        </Link>
      </div>
      {rows.length === 0 ? (
        <p className="px-6 py-5 font-ui text-body-sm text-ink-2">
          Nothing has been added yet. Everything your panel argues from comes from a document.
        </p>
      ) : (
        <div className="divide-rule">
          {rows.map((row) => (
            <div key={row.name} className="flex flex-wrap items-center justify-between gap-3 px-6 py-4">
              <span className="font-ui text-body-sm font-medium text-ink">{row.name}</span>
              <span className="font-mono text-micro text-ink-3">
                {row.documents} document{row.documents === 1 ? '' : 's'} &middot;{' '}
                <b className="font-medium text-ink-2">{row.read} read</b> &middot;{' '}
                <b className="font-medium text-ink-2">{row.reading} reading</b>
                {row.lastUsed ? ` · last used ${row.lastUsed.slice(0, 10)}` : ''}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
