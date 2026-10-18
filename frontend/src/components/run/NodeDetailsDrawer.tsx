/* eslint-disable react-refresh/only-export-components -- this module deliberately exports its pure derivations (entryDetails, resolveSelection) so the no-DOM suite can read every kind of entry without a renderer. */
import type { ReactNode } from 'react'
import Drawer from '../ui/Drawer'
import IconButton from '../ui/IconButton'
import StanceChip from '../common/StanceChip'
import { useGraphStore } from '../../graph/graphStore'
import type { GraphEdge, GraphNode } from '../../graph/graphStore'
import { LAYER_GLYPHS, nodeLayer } from '../../graph/layers'
import { useSelectionStore } from '../../graph/selectionStore'
import type { MapSelection } from '../../graph/selectionStore'
import { asStance } from '../../run/events'
import type { ProvenanceLink, Stance, TurnInfo } from '../../run/events'
import { useRunStore } from '../../run/runStore'
import type { RunState } from '../../run/reducer'

/** One document an entry came from, with the places inside it the reading was taken from. */
export interface SourceDoc {
  title: string
  where: string[]
}

/** An expert who cited an entry, and the passes they cited it in. */
export interface ReferencingExpert {
  expert: string
  passes: number[]
}

/** The position an entry is argued as: the stance, the confidence behind it, and the view itself. */
export interface HeldView {
  stance: Stance
  confidence: number
  view: string
}

export interface EntryDetails {
  kind: 'entry'
  name: string
  /** The kind's glyph — the same mark the map pane's toggle for that layer carries. */
  glyph: string
  /** The kind, as a phrase a customer reads ("an entry from your material"). */
  kindLabel: string
  sources: SourceDoc[]
  referencedBy: ReferencingExpert[]
  held: HeldView | null
}

export interface ConnectionDetails {
  kind: 'connection'
  name: string
  glyph: string
  kindLabel: string
}

export type MapDetails = EntryDetails | ConnectionDetails

/** A person's name behind the backend's Persona key (`{dataset_id}:{name}`; names may hold colons). */
function personName(key: string, datasetId: string | null): string {
  const prefix = datasetId ? `${datasetId}:` : ''
  if (prefix && key.startsWith(prefix)) return key.slice(prefix.length)
  return key.split(':').slice(1).join(':')
}

/**
 * The expert who holds an opinion, and the pass they filed it in — read off the `STATED` connection
 * the commit reported writing, so the holder is structure, never a name parsed out of a label.
 */
function opinionSource(run: RunState, opinionId: string): { holder: string; round: number } | null {
  for (const commit of run.commits) {
    for (const link of commit.writtenLinks) {
      if (link.kind === 'STATED' && link.to === opinionId) {
        return { holder: personName(link.from, run.datasetId), round: commit.round }
      }
    }
  }
  return null
}

/** The last turn an expert spoke. */
function lastSpoken(run: RunState, expert: string): TurnInfo | null {
  for (let index = run.rounds.length - 1; index >= 0; index -= 1) {
    const turns = run.rounds[index].turns
    for (let at = turns.length - 1; at >= 0; at -= 1) if (turns[at].agent_name === expert) return turns[at]
  }
  return null
}

/** An expert's turn in one pass, falling back to their latest when that pass has no turn from them. */
function turnFor(run: RunState, expert: string, round: number | null): TurnInfo | null {
  if (round !== null) {
    const turns = run.rounds.find((entry) => entry.round === round)?.turns ?? []
    const inPass = turns.filter((turn) => turn.agent_name === expert).pop()
    if (inPass) return inPass
  }
  return lastSpoken(run, expert)
}

/**
 * What an entry is argued as. An expert is read from their last turn; an opinion from the turn they
 * filed in that pass. Before anyone has spoken, the profile's own position stands.
 */
function heldView(run: RunState, holder: string, round: number | null): HeldView | null {
  const turn = turnFor(run, holder, round)
  if (turn) return { stance: asStance(turn.stance), confidence: turn.confidence, view: turn.content }
  const profile = run.roster.find((entry) => entry.identity.name === holder)
  return profile ? { stance: profile.stance, confidence: profile.confidence, view: profile.detailed_perspective } : null
}

/** One row per source document, carrying the places inside it the reading was taken from. */
export function sourceDocs(links: ProvenanceLink[]): SourceDoc[] {
  const byTitle = new Map<string, string[]>()
  for (const link of links) {
    const where = byTitle.get(link.title) ?? []
    if (link.breadcrumb && !where.includes(link.breadcrumb)) where.push(link.breadcrumb)
    byTitle.set(link.title, where)
  }
  return [...byTitle].map(([title, where]) => ({ title, where }))
}

/** Every expert whose turns cited an entry, with the passes they cited it in, in first-cited order. */
export function referencingExperts(run: RunState, name: string): ReferencingExpert[] {
  const byExpert = new Map<string, number[]>()
  for (const round of run.rounds) {
    for (const turn of round.turns) {
      if (!turn.references.includes(name)) continue
      const passes = byExpert.get(turn.agent_name) ?? []
      if (!passes.includes(round.round)) passes.push(round.round)
      byExpert.set(turn.agent_name, passes)
    }
  }
  return [...byExpert].map(([expert, passes]) => ({ expert, passes }))
}

/**
 * §9.5 everything the drawer reads for one entry. An entry of the material carries no source
 * documents: the extraction stream strips document lineage from what it sends, so a material entry
 * has none to name and the drawer says so rather than inventing a source.
 */
export function entryDetails(run: RunState, node: GraphNode): EntryDetails {
  const layer = nodeLayer(node)
  if (layer === 'corpus') {
    return {
      kind: 'entry',
      name: node.label,
      glyph: LAYER_GLYPHS.corpus,
      kindLabel: 'an entry from your material',
      sources: [],
      referencedBy: referencingExperts(run, node.label),
      held: null,
    }
  }

  const opinion = layer === 'opinions' ? opinionSource(run, node.id) : null
  const holder = layer === 'experts' ? node.label : opinion?.holder ?? null
  const profile = holder ? run.roster.find((entry) => entry.identity.name === holder) : undefined
  return {
    kind: 'entry',
    name: node.label,
    glyph: LAYER_GLYPHS[layer],
    kindLabel: layer === 'experts' ? 'an expert in your panel' : holder ? `an opinion held by ${holder}` : 'an opinion',
    // An expert's own sources; an opinion's are its holder's — the material the position was read from.
    sources: sourceDocs(profile?.summary_provenance ?? []),
    referencedBy: referencingExperts(run, node.label),
    held: holder ? heldView(run, holder, opinion?.round ?? null) : null,
  }
}

/** Everything the drawer draws for what the map has selected, or nothing when it is no longer held. */
export function resolveSelection(
  run: RunState,
  nodes: Record<string, GraphNode>,
  edges: Record<string, GraphEdge>,
  selection: MapSelection,
): MapDetails | null {
  if (selection.kind === 'entry') {
    const node = nodes[selection.id]
    return node ? entryDetails(run, node) : null
  }
  const edge = edges[selection.id]
  if (!edge) return null
  const from = nodes[edge.source]?.label ?? edge.source
  const to = nodes[edge.target]?.label ?? edge.target
  return { kind: 'connection', name: `${from} —${edge.label}→ ${to}`, glyph: LAYER_GLYPHS.connections, kindLabel: 'a connection between two entries' }
}

/** `pass 1, 2` — the passes an expert cited an entry in, in the words the customer reads them in. */
const passes = (list: number[]): string => `pass ${list.join(', ')}`

function Reading({ heading, children }: { heading: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 text-label uppercase text-ink-2">{heading}</h3>
      {children}
    </section>
  )
}

/** §9.5 the entry-details panel, as static markup — every reading is a prop, so it renders with no DOM. */
export function NodeDetailsView({ details, onClose }: { details: MapDetails; onClose: () => void }) {
  return (
    <Drawer open onClose={onClose} title={details.name}>
      <div className="space-y-6">
        <div className="flex items-start justify-between gap-4">
          <p className="flex items-center gap-2 text-body text-ink-2">
            <span aria-hidden="true" className="text-heading">
              {details.glyph}
            </span>
            {details.kindLabel}
          </p>
          <IconButton label="Close" onClick={onClose}>
            <span aria-hidden="true" className="text-heading">
              ×
            </span>
          </IconButton>
        </div>

        {details.kind === 'entry' && (
          <>
            <Reading heading="From">
              {details.sources.length > 0 ? (
                <ul className="space-y-2">
                  {details.sources.map((doc) => (
                    <li key={doc.title} className="text-body text-ink-2">
                      <span className="flex items-center gap-2">
                        <span aria-hidden="true">▤</span>
                        {doc.title}
                      </span>
                      {doc.where.length > 0 && <p className="ml-6 text-micro text-ink-2">{doc.where.join(' · ')}</p>}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-body text-ink-2">No source documents were recorded for this entry.</p>
              )}
            </Reading>

            <Reading heading="Referenced by">
              {details.referencedBy.length > 0 ? (
                <ul className="space-y-1">
                  {details.referencedBy.map((row) => (
                    <li key={row.expert} className="flex items-baseline justify-between gap-4 text-body text-ink-2">
                      <span className="flex items-center gap-2">
                        <span aria-hidden="true">{LAYER_GLYPHS.experts}</span>
                        {row.expert}
                      </span>
                      <span className="tnum text-micro text-ink-2">{passes(row.passes)}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-body text-ink-2">No expert has cited this entry yet.</p>
              )}
            </Reading>

            {details.held && (
              <Reading heading="Argued as">
                <div className="flex items-baseline gap-3">
                  <StanceChip stance={details.held.stance} />
                  <span className="tnum font-measurement text-mono text-ink">{details.held.confidence.toFixed(2)}</span>
                </div>
                <p className="mt-2 text-body-lg text-ink-2">{details.held.view}</p>
              </Reading>
            )}
          </>
        )}

        <p className="text-micro text-ink-2">Esc closes · focus returns to the map</p>
      </div>
    </Drawer>
  )
}

/**
 * The open entry's details, read off the map's selection channel. It draws nothing until the
 * customer has opened something, and nothing for a selection the map no longer holds — a stale
 * selection closes rather than showing a blank panel.
 */
export default function NodeDetailsDrawer() {
  const selection = useSelectionStore((s) => s.selection)
  const close = useSelectionStore((s) => s.close)
  const run = useRunStore((s) => s.run)
  const nodes = useGraphStore((s) => s.nodes)
  const edges = useGraphStore((s) => s.edges)
  const details = selection ? resolveSelection(run, nodes, edges, selection) : null
  return details ? <NodeDetailsView details={details} onClose={close} /> : null
}
