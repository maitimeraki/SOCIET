import type { DebateSource } from '../../api/rest'

/** What the source drawer shows: loading, the passage, or the calm unavailable state. */
export type SourceView = { phase: 'loading' } | { phase: 'ready'; source: DebateSource } | { phase: 'unavailable' }

export type FetchSource = (runId: string, n: string) => Promise<DebateSource>

/**
 * The drawer's one read, with the fetch injected so it is testable without a DOM. Any failure (the
 * server's flat 404, a network error, anything else) reads the same way: the source is unavailable.
 * The passage is returned as received; the drawer renders it as text, never as markup.
 */
export async function loadSourceView(fetchSource: FetchSource, runId: string, n: string): Promise<SourceView> {
  try {
    return { phase: 'ready', source: await fetchSource(runId, n) }
  } catch {
    return { phase: 'unavailable' }
  }
}
