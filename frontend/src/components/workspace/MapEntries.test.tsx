import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import MapEntries from './MapEntries'

describe("the map's entries list", () => {
  it('names the entries and their kinds', () => {
    const html = renderToStaticMarkup(
      <MapEntries
        entries={[
          { key: 'lease', label: 'lease', name: 'Mill Street lease.pdf' },
          { key: 'cond', label: 'condition', name: 'Condition of premises' },
        ]}
        connections={12}
      />,
    )
    expect(html).toContain('Mill Street lease.pdf')
    expect(html).toContain('lease')
    expect(html).toContain('Condition of premises')
    expect(html).toContain('12')
  })

  it('says plainly when the map holds nothing', () => {
    const html = renderToStaticMarkup(<MapEntries entries={[]} connections={0} />)
    expect(html).toContain('Nothing yet')
  })
})
