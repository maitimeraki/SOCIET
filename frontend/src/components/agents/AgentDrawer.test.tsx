import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { sampleView } from '../../run/__fixtures__/run-sample'
import { renderedText } from '../../test/copyLaw'
import AgentDrawer from './AgentDrawer'

const draw = (details: string) =>
  renderToStaticMarkup(<AgentDrawer profile={sampleView({ details })} open onClose={() => {}} />)

describe('AgentDrawer', () => {
  it('renders details as plain paragraphs', () => {
    const html = draw('The tariff record favours an early entry.\n\nThe entry cost is the open question.')
    expect(html).toContain('<p>The tariff record favours an early entry.</p>')
    expect(html).toContain('<p>The entry cost is the open question.</p>')
  })

  it('shows "not available" when the details are empty', () => {
    expect(renderedText(draw(''))).toContain('not available')
  })
})
