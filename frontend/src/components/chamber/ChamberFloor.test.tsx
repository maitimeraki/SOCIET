import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { sampleView } from '../../run/__fixtures__/run-sample'
import { renderedText } from '../../test/copyLaw'
import { SeatPopover } from './ChamberFloor'

describe('SeatPopover', () => {
  it('shows "not available" for a blank name and keeps the role and estimate', () => {
    const html = renderToStaticMarkup(
      <SeatPopover profile={sampleView({ name: '  ' })} onClose={() => {}} />,
    )
    const text = renderedText(html)
    expect(text).toContain('not available')
    expect(text).toContain('Trade analyst')
    expect(text).toContain('0.70')
  })
})
