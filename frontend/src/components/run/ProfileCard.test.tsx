import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { sampleView } from '../../run/__fixtures__/run-sample'
import { renderedText } from '../../test/copyLaw'
import ProfileCard from './ProfileCard'

const draw = (profile: ReturnType<typeof sampleView>) => renderToStaticMarkup(<ProfileCard profile={profile} />)

describe('ProfileCard', () => {
  it('shows role, bio, strength bar, confidence number and details', () => {
    const html = draw(sampleView())
    const text = renderedText(html)
    expect(text).toContain('trade analyst')
    expect(text).toContain('D. Weber reads the record as a trade analyst.')
    expect(html).toContain('width:65%')
    expect(text).toContain('0.70')
    expect(text).toContain('The tariff record favours an early entry.')
    expect(text).toContain('The entry cost is the open question.')
  })

  it('shows "not available" for a missing value and never "unknown"', () => {
    const text = renderedText(draw(sampleView({ role: '' })))
    expect(text).toContain('not available')
    expect(text).not.toMatch(/unknown/i)
  })

  it('shows "not available" for a type placeholder from the server and keeps the rest of the view', () => {
    const html = draw(sampleView({ type: 'type unknown' }))
    const text = renderedText(html)
    expect(text).toContain('not available')
    expect(text).not.toMatch(/unknown/i)
    expect(text).toContain('D. Weber reads the record as a trade analyst.')
    expect(text).toContain('0.70')
    expect(text).toContain('The entry cost is the open question.')
  })

  it('shows no rank, score, provenance or document title', () => {
    expect(renderedText(draw(sampleView()))).not.toMatch(/score|rank|provenance|chunk|source_count|participant/i)
  })

  it('renders confidence as an estimate, not a probability', () => {
    const text = renderedText(draw(sampleView()))
    expect(text.match(/estimate/gi)).toHaveLength(1)
    expect(text).not.toMatch(/probab/i)
  })
})
