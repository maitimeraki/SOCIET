import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const read = (path: string) => readFileSync(path, 'utf8')

describe('the target keeps the round pair graph wired in', () => {
  it('keeps ChamberFloor and ConvergenceTape in the run flow', () => {
    const flowView = read('src/components/run/FlowView.tsx')
    expect(flowView).toContain('ChamberFloor')
    expect(flowView).toContain('ConvergenceTape')
  })

  it('keeps the pass scrubber in the run flow', () => {
    expect(read('src/components/run/FlowView.tsx')).toContain('pass ')
  })

  it('draws pair arcs in the floor', () => {
    const floor = read('src/components/chamber/ChamberFloor.tsx')
    expect(floor).toContain('PairArc')
    expect(floor).toContain('Seat')
  })

  it('keeps the four window variants', () => {
    const store = read('src/run/runStore.ts')
    expect(store).toContain('seedMap')
    expect(store).toContain('loadAndConnect')
  })
})
