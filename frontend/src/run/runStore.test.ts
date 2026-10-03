import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { RunDoc } from '../api/types'
import { initialState } from './reducer'
import { useRunStore } from './runStore'

const { connectRun, getRun } = vi.hoisted(() => ({ connectRun: vi.fn(), getRun: vi.fn() }))

vi.mock('../api/ws', () => ({ connectRun }))
vi.mock('../api/rest', () => ({ getRun }))

const doc = (patch: Partial<RunDoc> = {}): RunDoc => ({
  run_id: 'run-1',
  created_at: '2026-10-03T00:00:00Z',
  query: 'Should we expand?',
  dataset_id: 'ds-1',
  config: {} as RunDoc['config'],
  status: 'running',
  events: [],
  ...patch,
})

beforeEach(() => {
  connectRun.mockReset()
  connectRun.mockReturnValue({ close: vi.fn() })
  getRun.mockReset()
  useRunStore.setState({ run: initialState, events: [], connection: 'idle', socket: null })
})

describe('runStore.loadAndConnect supersession', () => {
  it('two concurrent loads connect exactly once (StrictMode double-invoke)', async () => {
    getRun.mockResolvedValue(doc())
    await Promise.all([useRunStore.getState().loadAndConnect('run-1'), useRunStore.getState().loadAndConnect('run-1')])
    expect(connectRun).toHaveBeenCalledTimes(1)
    expect(connectRun).toHaveBeenCalledWith('run-1', expect.any(Object))
  })

  it('disconnect() during an in-flight load cancels it', async () => {
    let release!: (value: RunDoc) => void
    getRun.mockImplementation(() => new Promise<RunDoc>((resolve) => (release = resolve)))
    const pending = useRunStore.getState().loadAndConnect('run-1')
    useRunStore.getState().disconnect()
    release(doc())
    await pending
    expect(connectRun).not.toHaveBeenCalled()
  })
})
