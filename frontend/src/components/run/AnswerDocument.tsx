import type { AgentProfile, DissentingView, EvidenceItem, Stance } from '../../run/events'
import type { VerdictView } from '../../run/selectors'
import { fmtScore } from '../../utils/format'
import { NARRATIVE_FALLBACK_COPY } from '../verdict/NarrativeFallbackNotice'
import { splitSections } from '../verdict/narrative'
import EntityChips from '../verdict/EntityChips'
import PositionMark from '../ui/PositionMark'
import FiledSheet from '../ui/FiledSheet'
import type { FiledDecision } from '../ui/FiledSheet'
import Emphasis from '../common/Emphasis'
import WarningList from '../common/WarningList'
import Button from '../ui/Button'

/* ── the document, derived once ────────────────────────────────────────────────────────────────────
   The brief's core design — "what is read and what leaves are the same document" — is a construction,
   not a promise: `answerSections` is the ONLY place the document's content is decided. The reading
   view maps those sections to markup; the export maps the same sections to text. There is no second
   list of headings or values to drift, because there is no second list at all. (§8.5) */

const ANSWER_HEADING = 'The answer'
const OUTCOME_HEADING = 'The outcome'

/** One piece of a section. `text` is a paragraph, the rest are lists the two renderers read the same way. */
export type AnswerBlock =
  | { kind: 'text'; text: string }
  | { kind: 'listing'; items: string[] }
  | { kind: 'stances'; rows: { name: string; stance: Stance }[] }
  | { kind: 'entities'; supporting: string[]; opposing: string[] }
  | { kind: 'warnings'; items: string[] }

export interface AnswerSection {
  heading: string
  blocks: AnswerBlock[]
}

export interface AnswerInput {
  /** The decision the document answers — the export's own title, so the file reads alone. */
  question: string
  view: VerdictView
  /** The distinct source titles the run read from; empty is stated, never shown blank. */
  sources: string[]
  /** The material behind the run is gone — the export must say so, never omit the section silently. */
  corpusMissing: boolean
}

/**
 * The distinct source titles a run's experts read from, in first-seen order — read off the roster's
 * `summary_provenance` (the payload's own source links, D7). Pure, so the two callers share it.
 */
// eslint-disable-next-line react-refresh/only-export-components -- the source reader is the pure helper the document and its callers share
export function sourceTitles(profiles: AgentProfile[]): string[] {
  const seen = new Set<string>()
  const titles: string[] = []
  for (const profile of profiles) {
    for (const link of profile.summary_provenance) {
      if (link.title && !seen.has(link.title)) {
        seen.add(link.title)
        titles.push(link.title)
      }
    }
  }
  return titles
}

/** The document's sections — derived once, rendered twice. */
// eslint-disable-next-line react-refresh/only-export-components -- the section builder is the document's single source, read by the view, the export and the test
export function answerSections({ view, sources, corpusMissing }: AnswerInput): AnswerSection[] {
  const sections: AnswerSection[] = [...answerParts(view), confidenceSection(view), caseAgainst(view)]

  if (view.evidence.length > 0) {
    sections.push({ heading: 'Evidence', blocks: [{ kind: 'listing', items: view.evidence.map(evidenceLine) }] })
  }

  sections.push({
    heading: 'On the record',
    blocks:
      view.supporting.length > 0 || view.opposing.length > 0
        ? [{ kind: 'entities', supporting: view.supporting, opposing: view.opposing }]
        : [{ kind: 'text', text: 'No entities were recorded.' }],
  })

  sections.push({
    heading: 'Final stances',
    blocks:
      view.finalStances.length > 0
        ? [{ kind: 'stances', rows: view.finalStances.map((row) => ({ name: row.agent, stance: row.stance })) }]
        : [{ kind: 'text', text: 'No final positions were recorded.' }],
  })

  sections.push({ heading: 'Sources', blocks: sourceBlocks(sources, corpusMissing) })

  if (view.warnings.length > 0) {
    sections.push({ heading: 'Warnings', blocks: [{ kind: 'warnings', items: view.warnings }] })
  }

  return sections
}

/** A written answer when there is one; when the payload marks a fallback, the aggregates and the notice. */
function answerParts(view: VerdictView): AnswerSection[] {
  if (view.narrative.trim() && view.narrativeStatus !== 'fallback') {
    return splitSections(view.narrative).map((section) => ({
      heading: section.heading || ANSWER_HEADING,
      blocks: [{ kind: 'text', text: section.body }],
    }))
  }
  if (view.narrativeStatus === 'fallback') {
    return [
      {
        heading: OUTCOME_HEADING,
        blocks: [{ kind: 'text', text: NARRATIVE_FALLBACK_COPY }, { kind: 'text', text: view.summary }],
      },
    ]
  }
  return [{ heading: OUTCOME_HEADING, blocks: [{ kind: 'text', text: view.summary }] }]
}

function confidenceSection(view: VerdictView): AnswerSection {
  const text =
    view.confidence === null
      ? 'Not recorded for this decision.'
      : `${fmtScore(view.confidence)} — ${view.converged ? 'the reading converged.' : 'a plurality, not a consensus.'}`
  return { heading: 'Weighted confidence', blocks: [{ kind: 'text', text }] }
}

function caseAgainst(view: VerdictView): AnswerSection {
  return {
    heading: 'The case against',
    blocks:
      view.dissentingViews.length > 0
        ? [{ kind: 'listing', items: view.dissentingViews.map(dissentLine) }]
        : [{ kind: 'text', text: 'No dissent was recorded.' }],
  }
}

function sourceBlocks(sources: string[], corpusMissing: boolean): AnswerBlock[] {
  const blocks: AnswerBlock[] = []
  if (corpusMissing) blocks.push({ kind: 'text', text: 'The material behind this decision is no longer available.' })
  if (sources.length > 0) blocks.push({ kind: 'listing', items: sources })
  else if (!corpusMissing) blocks.push({ kind: 'text', text: 'No sources were recorded for this decision.' })
  return blocks
}

const dissentLine = (view: DissentingView): string => `${view.stance} — ${view.view}`
const evidenceLine = (item: EvidenceItem): string => `${item.entity} — ${item.claim}`

/** The section list, serialized as a self-contained markdown file — the same content, in text. */
// eslint-disable-next-line react-refresh/only-export-components -- the serializer is the export half of the document, tested beside it
export function answerText(input: AnswerInput): string {
  const lines: string[] = [`# ${input.question}`, '']
  for (const section of answerSections(input)) {
    lines.push(`## ${section.heading}`, '')
    for (const block of section.blocks) lines.push(...blockLines(block), '')
  }
  return `${lines.join('\n').trimEnd()}\n`
}

// eslint-disable-next-line react-refresh/only-export-components -- the block serializer is the export's own half of the document, asserted against the reading view by the test
export function blockLines(block: AnswerBlock): string[] {
  switch (block.kind) {
    case 'text':
      return block.text.split('\n')
    case 'listing':
      return block.items.map((item) => `- ${item}`)
    case 'stances':
      return block.rows.map((row) => `- ${row.name} — ${row.stance}`)
    case 'warnings':
      return block.items.map((item) => `- ${item}`)
    case 'entities': {
      const lines: string[] = []
      if (block.supporting.length > 0) lines.push(`- For: ${block.supporting.join(', ')}`)
      if (block.opposing.length > 0) lines.push(`- Against: ${block.opposing.join(', ')}`)
      return lines
    }
  }
}

export interface AnswerDocumentProps extends AnswerInput {
  runId: string
}

/**
 * The reading view and the export in one component: the sections are built once and either mapped to
 * markup or serialized to a file. Static by construction — no motion, no interaction but the export
 * affordance — because this is the surface an analyst prints. (§8.5)
 */
export default function AnswerDocument({ runId, question, view, sources, corpusMissing }: AnswerDocumentProps) {
  const sections = answerSections({ question, view, sources, corpusMissing })
  // The outcome header is the kit's FiledSheet — the same sheet the homepage's comparison panel
  // and the auth page's right column render — so the three surfaces rhyme by construction (§14.3).
  const filed: FiledDecision = {
    question,
    position: view.stance,
    share: view.confidence,
    caseAgainst: view.dissentingViews[0]?.view ?? 'No dissent was recorded.',
    sources:
      sources.length > 0 ? sources.join(' · ') : 'No sources were recorded for this decision.',
  }

  const download = () => {
    const blob = new Blob([answerText({ question, view, sources, corpusMissing })], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${runId || 'verdict'}_verdict.md`
    anchor.click()
    // Deferred: revoking synchronously after click() is racy in Firefox.
    setTimeout(() => URL.revokeObjectURL(url), 0)
  }

  return (
    <article className="space-y-8">
      <FiledSheet decision={filed} />
      {sections.map((section, index) => (
        <section key={index}>
          <h3 className="mb-3 text-heading text-ink">{section.heading}</h3>
          <div className="max-w-[60ch] space-y-3">
            {section.blocks.map((block, index) => (
              <Block key={index} block={block} />
            ))}
          </div>
        </section>
      ))}
      <div className="print:hidden">
        <Button type="button" variant="secondary" onClick={download} className="min-h-11">
          Export this verdict
        </Button>
      </div>
    </article>
  )
}

function Block({ block }: { block: AnswerBlock }) {
  switch (block.kind) {
    case 'text':
      // The reading view renders the emphasis; the export keeps its markdown markers, because the
      // export is a markdown file. Same content, two mediums.
      return <Emphasis text={block.text} className="whitespace-pre-line font-record text-body-lg text-ink-2" />
    case 'listing':
      return (
        <ul className="space-y-1 text-body text-ink-2">
          {block.items.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      )
    case 'stances':
      return (
        <ul className="space-y-1">
          {block.rows.map((row) => (
            <li key={row.name} className="flex items-baseline gap-2 text-body text-ink-2">
              <span className="text-ink">{row.name}</span>
              <PositionMark position={row.stance} size="sm" ground="light" />
            </li>
          ))}
        </ul>
      )
    case 'entities':
      return <EntityChips supporting={block.supporting} opposing={block.opposing} />
    case 'warnings':
      return <WarningList warnings={block.items} />
  }
}
