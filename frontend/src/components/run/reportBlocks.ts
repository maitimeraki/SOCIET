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

/** A run of text or a citation marker `[n]` (digits only), in bold or not. */
export type InlinePart =
  | { kind: 'text'; text: string; strong: boolean }
  | { kind: 'source'; n: string; raw: string; strong: boolean }

const JUDGEMENT_TAG = /\(judgement\)/
const BOLD = /\*\*([^*]+)\*\*/g
const CITATION = /\[(\d+)\]/g

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
      blocks.push({ kind: 'paragraph', text: line, judgement: line.startsWith('Point:') && JUDGEMENT_TAG.test(line) })
    }
  }
  endList()
  return blocks
}

/** Splits a line into text and citation parts, each marked bold or not, in order. A citation inside bold stays a citation. */
export function inlineParts(text: string): InlinePart[] {
  const parts: InlinePart[] = []
  const plain = (segment: string, strong: boolean) => {
    let at = 0
    for (const match of segment.matchAll(CITATION)) {
      const start = match.index ?? 0
      if (start > at) parts.push({ kind: 'text', text: segment.slice(at, start), strong })
      parts.push({ kind: 'source', n: match[1], raw: match[0], strong })
      at = start + match[0].length
    }
    if (at < segment.length) parts.push({ kind: 'text', text: segment.slice(at), strong })
  }
  let last = 0
  for (const match of text.matchAll(BOLD)) {
    const start = match.index ?? 0
    plain(text.slice(last, start), false)
    plain(match[1], true)
    last = start + match[0].length
  }
  plain(text.slice(last), false)
  return parts
}
