import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const read = (path: string) => readFileSync(path, 'utf8')

describe('the target keeps the round pair graph wired in', () => {
  it('keeps ChamberFloor and ConvergenceTape in the run flow', () => {
    const runPage = read('src/pages/RunPage.tsx')
    expect(runPage).toContain('ChamberFloor')
    expect(runPage).toContain('ConvergenceTape')
  })

  it('draws pair arcs in the floor', () => {
    expect(read('src/components/chamber/ChamberFloor.tsx')).toContain('PairArc')
  })

  it('keeps the four window variants', () => {
    const store = read('src/run/runStore.ts')
    expect(store).toContain('seedMap')
    expect(store).toContain('loadAndConnect')
  })
})
