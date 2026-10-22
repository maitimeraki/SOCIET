import { Fragment } from 'react'

/**
 * Inline emphasis — the panel writes `**bold**` and the customer must never see the asterisks.
 *
 * Only the two-marker form is supported, because that is all the panel emits, so this is a
 * splitter and not a markdown parser: no dependency, no library, no second grammar. An unmatched
 * marker is malformed input and is rendered as the plain text it is.
 *
 * The reading view and the export disagree here on purpose: the export is a markdown file, so it
 * keeps its markers; the screen renders them.
 */
export default function Emphasis({ text, className = '' }: { text: string; className?: string }) {
  const parts = text.split('**')
  return (
    <p className={className}>
      {parts.map((part, index) =>
        index % 2 === 1 && index + 1 < parts.length ? (
          <strong key={index} className="font-semibold">
            {part}
          </strong>
        ) : (
          <Fragment key={index}>{part}</Fragment>
        ),
      )}
    </p>
  )
}
