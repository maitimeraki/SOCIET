import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { sampleView } from '../../run/__fixtures__/run-sample'
import { renderedText } from '../../test/copyLaw'
import Seat from './Seat'

const draw = (confidence: number) =>
  renderToStaticMarkup(
    <svg>
      <Seat
        seat={{ profile: sampleView({ confidence }), x: 10, y: 10, voice: 'spoke', pulsing: false, onSelect: () => {} }}
        tabIndex={0}
        onKeyNav={() => {}}
      />
    </svg>,
  )

describe('Seat', () => {
  it('names the confidence as an estimate, not conf', () => {
    const text = renderedText(draw(0.7))
    expect(text).toContain('estimate 0.70')
    expect(text).not.toMatch(/\bconf\b/)
  })
})
