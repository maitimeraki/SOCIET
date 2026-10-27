import Graph from 'graphology'
import { EXPERT_TYPE, expertKey } from '../graph/graphStore'
import type { GraphEdge, GraphNode, GraphSnapshot } from '../graph/graphStore'
import { asStance } from './events'
import type { Stance, WrittenLink } from './events'
import type { RunState } from './reducer'

/** A connection's identity in the map's terms — the store's edge key, reproduced. */
const edgeKey = (source: string, target: string, label: string): string => `${source}|${target}|${label}`

type Attributes = Record<string, unknown>

/** A store entry as node attributes — identity is the graph key, so `id` is dropped. */
function nodeAttributes({ label, type, kind, stance, properties }: GraphNode): Attributes {
  const attributes: Attributes = { label, type }
  if (kind !== undefined) attributes.kind = kind
  if (stance !== undefined) attributes.stance = stance
  if (properties !== undefined) attributes.properties = properties
  return attributes
}

/** A store connection as edge attributes — the endpoints are the graph's, so only the kind rides here. */
function edgeAttributes({ label, properties }: GraphEdge): Attributes {
  const attributes: Attributes = { label }
  if (properties !== undefined) attributes.properties = properties
  return attributes
}

/** A person's name behind the backend's Persona key (`{dataset_id}:{name}`; names may hold colons). */
const personName = (key: string): string => key.slice(key.indexOf(':') + 1)

/**
 * The position each entry a commit wrote is coloured by, keyed as the backend keyed it (§9.2).
 *
 * The backend stores an opinion's stance as the holder's LAST turn in that pass — `society_memory.
 * commit_round` reads `last = turns[-1]` and MERGEs the opinion with `last.stance` — so that is what
 * the map mirrors. The holder is read off the `STATED` connection the same commit reported writing,
 * never parsed out of the entry's label. An opinion whose holder or turn the stored events do not
 * carry is left out of the map, so it draws in the unpositioned neutral rather than a guessed hue
 * (D7). The one function serves both producers, so a reopened run resolves exactly what the live
 * fold resolved.
 */
export function opinionStances(run: RunState, round: number, links: readonly WrittenLink[]): Record<string, Stance> {
  const turns = run.rounds.find((entry) => entry.round === round)?.turns ?? []
  const stances: Record<string, Stance> = {}
  for (const link of links) {
    if (link.kind !== 'STATED') continue
    const holder = personName(link.from)
    const turn = turns.filter((spun) => spun.agent_name === holder).pop()
    if (turn) stances[link.to] = asStance(turn.stance)
  }
  return stances
}

/** An entry a commit wrote, as the map holds it — verbatim, plus the position resolved for it. */
function opinionEntry(written: { key: string; label: string; name: string }, stances: Record<string, Stance>): GraphNode {
  const entry: GraphNode = { id: written.key, label: written.name, type: written.label }
  const stance = stances[written.key]
  if (stance !== undefined) entry.stance = stance
  return entry
}

/**
 * Compose the run's map from the run's own events (D7, D14). Pure: folded state in, a graph out — no
 * I/O, no store, no render state.
 *
 * It rebuilds exactly what the live path folds into `useGraphStore`: the corpus entries the snapshot
 * read returned, one expert per seated profile keyed as the backend keys the stored person, and the
 * entries and connections each `commit` reports the transaction wrote, verbatim (D7). A reopened run
 * therefore composes the identical map — replay = live. The rebuild is meant to key on `RunState.version`
 * so a frame that folds a burst of events rebuilds once, not once per event.
 *
 * The one reconciliation over the live fold: a written connection lands only when both its endpoints
 * are seated. `mergeOpinions` keeps a connection whose endpoint entry is absent (a dangling edge the
 * renderer then drops); a graphology edge needs both nodes, so the composer leaves it unseated and the
 * graph stays self-consistent.
 *
 * @param corpus the Task 1.3 corpus read, or null when no snapshot is available — the caller owns the fetch.
 * @param maxRound the pass to replay up to — commits after it are left out; null mirrors every pass.
 */
export function composeRunGraph(run: RunState, corpus: GraphSnapshot | null, maxRound: number | null = null): Graph {
  // Last write wins per key, exactly as the store's `upsertNodes`/`upsertEdges` fold — so the map holds
  // one entry per identity however many passes write it.
  const nodes: Record<string, GraphNode> = {}
  const edges: Record<string, GraphEdge> = {}

  for (const node of corpus?.nodes ?? []) nodes[node.id] = node
  for (const edge of corpus?.edges ?? []) edges[edgeKey(edge.source, edge.target, edge.label)] = edge

  // Expert layer — one entry per agent, keyed as the backend keys the stored person (`{dataset_id}:{name}`).
  for (const profile of run.roster) {
    const datasetId = profile.graph_snapshot?.dataset_id
    // Without a dataset there is no Persona key to mirror: seat nothing rather than key a fabricated id.
    if (!datasetId) continue
    const id = expertKey({ datasetId, name: profile.identity.name })
    nodes[id] = { id, label: profile.identity.name, type: EXPERT_TYPE }
  }

  // Opinion layer — the entries and connections the commits report they wrote, taken verbatim (D7),
  // each entry carrying the position the pass recorded for its holder so the map can colour it (§9.2).
  for (const commit of run.commits) {
    if (maxRound !== null && commit.round > maxRound) continue
    const stances = opinionStances(run, commit.round, commit.writtenLinks)
    for (const written of commit.writtenNodes) nodes[written.key] = opinionEntry(written, stances)
    for (const link of commit.writtenLinks) edges[edgeKey(link.from, link.to, link.kind)] = { source: link.from, target: link.to, label: link.kind }
  }

  const graph = new Graph({ multi: true })
  for (const node of Object.values(nodes)) graph.addNode(node.id, nodeAttributes(node))
  for (const edge of Object.values(edges)) {
    if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) continue // an endpoint absent — leave it unseated
    graph.addEdgeWithKey(edgeKey(edge.source, edge.target, edge.label), edge.source, edge.target, edgeAttributes(edge))
  }
  return graph
}
