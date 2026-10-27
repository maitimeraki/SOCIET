import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { fold } from '../../run/reducer'
import { RUN_SAMPLE } from '../../run/__fixtures__/run-sample'
import FlowView from './FlowView'

const run = fold(RUN_SAMPLE)

describe('FlowView keeps the round pair graph', () => {
  it('renders the floor, the pass scrubber and a turn', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <FlowView run={run} activeRound={1} latestRound={2} onScrub={() => {}} onNavigate={() => {}} />
      </MemoryRouter>,
    )
    expect(html).toContain('The panel&#x27;s debate')
    expect(html).toContain('pass 1')
    expect(html).toContain('Tariff alignment favours early expansion.')
  })
})
