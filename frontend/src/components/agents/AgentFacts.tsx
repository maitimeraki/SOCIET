import { NOT_AVAILABLE, detailParagraphs } from '../../run/agentDisplay'

/** Details as plain paragraphs; an empty text reads "not available". */
export function Details({ text, className = '' }: { text: string; className?: string }) {
  const paragraphs = detailParagraphs(text)
  if (paragraphs.length === 0) return <p className={className}>{NOT_AVAILABLE}</p>
  return (
    <div className={className}>
      {paragraphs.map((paragraph, index) => (
        <p key={index}>{paragraph}</p>
      ))}
    </div>
  )
}

/** Confidence: a number, labelled as an estimate, never a probability. "model" is banned copy (§13). */
export function Estimate({ value }: { value: number }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="text-micro text-ink-3">estimate</span>
      <span className="tnum font-mono text-micro text-ink-2">{value.toFixed(2)}</span>
    </span>
  )
}
