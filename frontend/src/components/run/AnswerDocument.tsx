import { Fragment, useEffect, useState } from 'react'
import { getDebateSource } from '../../api/rest'
import type { DebateSource } from '../../api/rest'
import type { ReportSources } from '../../run/events'
import Drawer from '../ui/Drawer'
import { inlineParts, reportBlocks } from './reportBlocks'
import type { ReportBlock } from './reportBlocks'

export interface AnswerDocumentProps {
  runId: string
  /** The report markdown, rendered as given. */
  markdown: string
  sources: ReportSources
}

/**
 * The report as the customer reads it: the backend's markdown, block by block, with no section or
 * heading added. A `[n]` marker that names a source becomes a button; any other marker stays text.
 * A passage is fetched only when its button is pressed.
 */
export default function AnswerDocument({ runId, markdown, sources }: AnswerDocumentProps) {
  const [open, setOpen] = useState<string | null>(null)
  return (
    <section className="rounded-xl bg-paper p-12 shadow-sheet">
      <article className="max-w-[60ch] space-y-4">
        {reportBlocks(markdown).map((block, index) => (
          <Block key={index} block={block} sources={sources} onOpen={setOpen} />
        ))}
      </article>
      <Drawer open={open !== null} onClose={() => setOpen(null)} title={open === null ? 'Source' : `Source ${open}`}>
        {open !== null ? <SourceText key={open} runId={runId} n={open} /> : null}
      </Drawer>
    </section>
  )
}

function Block({ block, sources, onOpen }: { block: ReportBlock; sources: ReportSources; onOpen: (n: string) => void }) {
  switch (block.kind) {
    case 'title':
      return (
        <h2 className="font-ui text-heading text-ink">
          <Inline text={block.text} sources={sources} onOpen={onOpen} />
        </h2>
      )
    case 'heading':
      return (
        <h3 className="pt-4 font-ui text-body font-semibold text-ink">
          <Inline text={block.text} sources={sources} onOpen={onOpen} />
        </h3>
      )
    case 'paragraph':
      // A judgement is the board's own reading, not a cited claim: a rule and a quieter ink mark it
      // apart from a point that rests on the documents. The tag itself is printed and stays legible.
      return (
        <p
          className={
            block.judgement ? 'border-l-2 border-rule pl-3 font-ui text-body text-ink-2' : 'font-ui text-body text-ink'
          }
        >
          <Inline text={block.text} sources={sources} onOpen={onOpen} />
        </p>
      )
    case 'list':
      return (
        <ul className="list-disc space-y-1 pl-5 font-ui text-body text-ink-2">
          {block.items.map((item, index) => (
            <li key={index}>
              <Inline text={item} sources={sources} onOpen={onOpen} />
            </li>
          ))}
        </ul>
      )
  }
}

function Inline({ text, sources, onOpen }: { text: string; sources: ReportSources; onOpen: (n: string) => void }) {
  return (
    <>
      {inlineParts(text).map((part, index) => {
        if (part.kind === 'bold') return <strong key={index} className="font-semibold">{part.text}</strong>
        if (part.kind === 'source' && Object.prototype.hasOwnProperty.call(sources, part.n)) {
          return (
            <button
              key={index}
              type="button"
              aria-label={`Open source ${part.n}`}
              onClick={() => onOpen(part.n)}
              className="font-mono text-micro text-ink-2 underline decoration-rule underline-offset-4 hover:text-ink hover:decoration-accent"
            >
              [{part.n}]
            </button>
          )
        }
        return <Fragment key={index}>{part.kind === 'source' ? part.raw : part.text}</Fragment>
      })}
    </>
  )
}

type Loaded = { phase: 'loading' } | { phase: 'ready'; source: DebateSource } | { phase: 'unavailable' }

/** One cited passage, read on demand. Every failure reads the same way: the source is unavailable. */
function SourceText({ runId, n }: { runId: string; n: string }) {
  const [loaded, setLoaded] = useState<Loaded>({ phase: 'loading' })
  useEffect(() => {
    let cancelled = false
    getDebateSource(runId, n).then(
      (source) => {
        if (!cancelled) setLoaded({ phase: 'ready', source })
      },
      () => {
        if (!cancelled) setLoaded({ phase: 'unavailable' })
      },
    )
    return () => {
      cancelled = true
    }
  }, [runId, n])

  if (loaded.phase === 'loading') return <p className="font-ui text-body text-ink-3">Loading the source…</p>
  if (loaded.phase === 'unavailable') return <p className="font-ui text-body text-ink-2">This source is unavailable.</p>
  const { source } = loaded
  return (
    <div>
      <p className="font-ui text-body-sm font-semibold text-ink">{source.document}</p>
      {source.section ? <p className="font-ui text-body-sm text-ink-2">{source.section}</p> : null}
      {/* Plain text by construction: the passage is data, never markup. */}
      <p className="mt-4 whitespace-pre-wrap font-ui text-body text-ink">{source.text}</p>
    </div>
  )
}
