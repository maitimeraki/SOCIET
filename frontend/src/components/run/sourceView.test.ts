import { describe, expect, it, vi } from 'vitest'
import { ApiError, NetworkError } from '../../api/rest'
import type { DebateSource } from '../../api/rest'
import { loadSourceView } from './sourceView'

const PASSAGE: DebateSource = { document: 'EU market study 2026', section: 'Tariffs', text: 'Tariffs <b>rise</b> & fall.' }

describe('loadSourceView — the drawer’s one read, with the fetch injected', () => {
  it('reads the passage once, for the run and the number pressed', async () => {
    const fetchSource = vi.fn(async () => PASSAGE)
    await loadSourceView(fetchSource, 'run-1', '3')
    expect(fetchSource).toHaveBeenCalledTimes(1)
    expect(fetchSource).toHaveBeenCalledWith('run-1', '3')
  })

  it('shows the document, section and text it read', async () => {
    expect(await loadSourceView(async () => PASSAGE, 'run-1', '3')).toEqual({ phase: 'ready', source: PASSAGE })
  })

  it('keeps the text exactly as received, so it renders as plain text and never as markup', async () => {
    const view = await loadSourceView(async () => PASSAGE, 'run-1', '3')
    expect(view.phase === 'ready' && view.source.text).toBe('Tariffs <b>rise</b> & fall.')
  })

  it('reads the flat 404 as the source being unavailable', async () => {
    const view = await loadSourceView(async () => {
      throw new ApiError(404, 'Not found.')
    }, 'run-1', '3')
    expect(view).toEqual({ phase: 'unavailable' })
  })

  it('reads a network failure as the source being unavailable', async () => {
    const view = await loadSourceView(async () => {
      throw new NetworkError()
    }, 'run-1', '3')
    expect(view).toEqual({ phase: 'unavailable' })
  })

  it('reads any other failure the same calm way', async () => {
    const view = await loadSourceView(async () => {
      throw new ApiError(500, 'internal text')
    }, 'run-1', '3')
    expect(view).toEqual({ phase: 'unavailable' })
  })
})
