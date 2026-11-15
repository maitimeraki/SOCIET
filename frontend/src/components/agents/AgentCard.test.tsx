import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { sampleView } from '../../run/__fixtures__/run-sample'
import { renderedText } from '../../test/copyLaw'
import AgentCard from './AgentCard'

const draw = (profile: ReturnType<typeof sampleView>) =>
  renderToStaticMarkup(<AgentCard profile={profile} onOpen={() => {}} />)

describe('AgentCard', () => {
  it('shows the strength bar and the confidence as an estimate', () => {
    const html = draw(sampleView())
    expect(html).toContain('width:65%')
    expect(renderedText(html)).toContain('estimate')
    expect(renderedText(html)).toContain('0.70')
  })

  it('shows "not available" for a type placeholder from the server and keeps the rest of the card', () => {
    const text = renderedText(draw(sampleView({ type: 'type unknown' })))
    expect(text).toContain('not available')
    expect(text).not.toMatch(/unknown/i)
    expect(text).toContain('estimate')
    expect(text).toContain('D. Weber reads the record as a trade analyst.')
  })

  it('shows "not available" for a blank bio', () => {
    expect(renderedText(draw(sampleView({ bio: '   ' })))).toContain('not available')
  })
})
