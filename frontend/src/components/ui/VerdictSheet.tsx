import PositionMark from './PositionMark'
import type { Position } from './PositionMark'

export interface VerdictSheetProps {
  question: string
  filed: string
  position: Position
  /** The weighted share; null when the decision recorded no confidence — stated, never invented. */
  share: number | null
  caseAgainst: string
  reasoning: string[]
  whoHeldWhichView: { position: Position; names: string[] }[]
  sources: { document: string; reference: string }[]
  onExport?: () => void
  /** §7.2 — render only the filed fragment (outcome, case against, sources) for the auth evidence
   *  panel. The reasoning and the view split belong to the full document. */
  cropped?: boolean
}

/**
 * §8.6 The signature component. Paper, 24px radius, 48px padding, one deep shadow, no border.
 *
 * The order is the argument: the position, the share and the date come before any prose; the
 * case against gets its own ruled block, because it is the product's differentiator and must
 * not read at the same weight as the reasoning.
 *
 * The share is a measurement: it is set in mono and never coloured by the position.
 */
export default function VerdictSheet({
  question,
  filed,
  position,
  share,
  caseAgainst,
  reasoning,
  whoHeldWhichView,
  sources,
  onExport,
  cropped = false,
}: VerdictSheetProps) {
  return (
    <article className="max-w-[760px] rounded-xl bg-paper p-12 shadow-sheet print:max-w-none print:rounded-none print:shadow-none">
      {/* Standing, not dismissible: AI Act Art. 50(1). It prints with the document. */}
      <p className="mb-4 font-mono text-micro text-ink-3">These are AI-generated perspectives, not human advisors.</p>

      <div className="flex items-center justify-between gap-4">
        <p className="font-mono text-micro uppercase tracking-[0.08em] text-ink-3">Filed &middot; {filed}</p>
        {onExport ? (
          <button
            type="button"
            onClick={onExport}
            className="min-h-11 font-ui text-body-sm text-accent underline underline-offset-4 print:hidden"
          >
            Export document
          </button>
        ) : null}
      </div>

      <h2 className="mt-5 font-display text-title font-medium tracking-[-0.02em] text-ink">{question}</h2>

      <div className="mt-5 flex flex-wrap items-baseline gap-5 border-y border-rule py-5">
        <PositionMark position={position} ground="light" />
        <span className="tnum font-mono text-numeral tracking-[-0.04em] text-ink">
          {share === null ? '—' : share.toFixed(2)}
        </span>
        <span className="font-mono text-micro uppercase tracking-[0.08em] text-ink-3">weighted share</span>
      </div>

      <section className="border-b border-rule py-6">
        <p className="font-ui text-label uppercase tracking-[0.1em] text-caution">The case against</p>
        <p className="mt-2 border-l-3 border-caution pl-4 font-ui text-body text-ink-2">{caseAgainst}</p>
      </section>

      {cropped ? null : (
        <>
          <section className="border-b border-rule py-6">
            <p className="font-ui text-label uppercase tracking-[0.1em] text-ink-3">The reasoning</p>
            {reasoning.map((paragraph) => (
              <p key={paragraph} className="mt-3 max-w-[60ch] font-ui text-body text-ink-2">
                {paragraph}
              </p>
            ))}
          </section>

          <section className="border-b border-rule py-6">
            <p className="font-ui text-label uppercase tracking-[0.1em] text-ink-3">Who held which view</p>
            {whoHeldWhichView.map((row) => (
              <div key={row.position} className="mt-3 grid grid-cols-[120px_1fr] gap-4 border-t border-hairline py-2.5 first:border-t-0">
                <PositionMark position={row.position} size="sm" ground="light" />
                <span className="font-ui text-body-sm text-ink-2">{row.names.join(', ')}</span>
              </div>
            ))}
          </section>
        </>
      )}

      <section className="py-6">
        <p className="font-ui text-label uppercase tracking-[0.1em] text-ink-3">Sources</p>
        {sources.map((source) => (
          <div key={source.document} className="mt-3 flex items-baseline justify-between gap-4 border-t border-hairline py-2.5 first:border-t-0">
            <span className="font-ui text-body-sm text-ink-2">{source.document}</span>
            <span className="font-mono text-micro text-ink-3">{source.reference}</span>
          </div>
        ))}
      </section>
    </article>
  )
}
