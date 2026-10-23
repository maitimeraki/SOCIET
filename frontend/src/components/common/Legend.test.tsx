import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import { STANCE_ORDER } from '../../run/selectors'
import { PositionGlyph } from '../ui/PositionMark'
import Legend from './Legend'

describe('Legend', () => {
  it('renders a symbol beside every word, so a colour is never the only carrier', () => {
    const html = renderToStaticMarkup(
      <Legend
        title="Stance"
        entries={STANCE_ORDER.map((stance) => ({
          symbol: <PositionGlyph position={stance} ground="light" />,
          label: stance,
        }))}
      />,
    )
    expect((html.match(/<svg/g) ?? []).length).toBe(STANCE_ORDER.length)
    for (const stance of STANCE_ORDER) expect(html).toContain(stance)
  })

  it('renders nothing when there is nothing to key', () => {
    expect(renderToStaticMarkup(<Legend entries={[]} />)).toBe('')
  })
})
