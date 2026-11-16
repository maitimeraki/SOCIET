/**
 * The report markdown, read as blocks. The backend validates the shape (`# title`, `## sections`,
 * point lines tagged `(from the documents)` or `(judgement)`), so this is a line reader and not a
 * markdown parser: no dependency, and nothing is added that the markdown does not say. The reading
 * view and the HTML export both read these blocks, so they cannot disagree about the structure.
 */

export type ReportBlock =
  | { kind: 'title'; text: string }
  | { kind: 'heading'; text: string }
  | { kind: 'paragraph'; text: string; judgement: boolean }
  | { kind: 'list'; items: string[] }

/** A run of text, a `**bold**` span, or a citation marker `[n]` (digits only). */
export type InlinePart =
  | { kind: 'text'; text: string }
  | { kind: 'bold'; text: string }
  | { kind: 'source'; n: string; raw: string }

const JUDGEMENT_TAG = /\(judgement\)\s*$/
const INLINE = /\*\*([^*]+)\*\*|\[(\d+)\]/g

export function reportBlocks(markdown: string): ReportBlock[] {
  const blocks: ReportBlock[] = []
  let items: string[] | null = null
  const endList = () => {
    if (items) blocks.push({ kind: 'list', items })
    items = null
  }
  for (const raw of markdown.split('\n')) {
    const line = raw.trim()
    if (line === '') {
      endList()
    } else if (line.startsWith('# ')) {
      endList()
      blocks.push({ kind: 'title', text: line.slice(2).trim() })
    } else if (line.startsWith('## ')) {
      endList()
      blocks.push({ kind: 'heading', text: line.slice(3).trim() })
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      items = [...(items ?? []), line.slice(2).trim()]
    } else {
      endList()
      blocks.push({ kind: 'paragraph', text: line, judgement: JUDGEMENT_TAG.test(line) })
    }
  }
  endList()
  return blocks
}

/** Splits a line into text, bold and citation parts, in order. Unknown numbers are the caller's to read. */
export function inlineParts(text: string): InlinePart[] {
  const parts: InlinePart[] = []
  let last = 0
  for (const match of text.matchAll(INLINE)) {
    const at = match.index ?? 0
    if (at > last) parts.push({ kind: 'text', text: text.slice(last, at) })
    if (match[1] !== undefined) parts.push({ kind: 'bold', text: match[1] })
    else parts.push({ kind: 'source', n: match[2], raw: match[0] })
    last = at + match[0].length
  }
  if (last < text.length) parts.push({ kind: 'text', text: text.slice(last) })
  return parts
}
