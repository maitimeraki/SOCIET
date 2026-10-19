/**
 * §13 — the copy law, in ONE place. Every rendered-string test imports this so there is a single
 * banned list; the marketing suite imports it too. The matcher is anchored on word boundaries and
 * tolerates the common inflections, not just the plural (`round` → rounds/rounded/rounding,
 * `chunk` → chunks/chunked/chunking, `society` → societies), so a rendered "Rounds" or "chunked"
 * cannot slip past a singular-only pattern.
 *
 * The law governs RENDERED TEXT only: identifiers, route paths, API field names, `data-*`
 * attributes and log lines are exempt. `renderedText` strips the tags (and their attributes) first,
 * so a class like `bg-ground` can never trip `\bround\b`.
 */
export const BANNED = [
  'agent', 'graph', 'node', 'edge', 'round', 'retrieval', 'ontology', 'model',
  'society', 'chunk', 'embedding', 'vector', 'llm', 'prompt', 'token', 'pipeline', 'job',
] as const

/** The word and its common inflections — stems, not just `s?`. `retrieval`/`llm` take no inflection. */
const STEMS: Record<(typeof BANNED)[number], string> = {
  agent: 'agents?',
  graph: 'graphs?',
  node: 'nodes?',
  edge: 'edges?',
  round: 'round(?:s|ed|ing)?',
  retrieval: 'retrieval',
  ontology: 'ontolog(?:y|ies)',
  model: 'models?',
  society: 'societ(?:y|ies)',
  chunk: 'chunk(?:s|ed|ing)?',
  embedding: 'embeddings?',
  vector: 'vectors?',
  llm: 'llms?',
  prompt: 'prompt(?:s|ed|ing)?',
  token: 'tokens?',
  pipeline: 'pipelines?',
  job: 'jobs?',
}

export const BANNED_WORD = new RegExp(`\\b(?:${BANNED.map((word) => STEMS[word]).join('|')})\\b`, 'i')

/** Rendered text with tags (and the attributes inside them) removed — identifiers never trip the law. */
export const renderedText = (markup: string): string => markup.replace(/<[^>]*>/g, ' ')
