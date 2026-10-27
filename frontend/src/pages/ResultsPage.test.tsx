import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { fold } from '../run/reducer'
import { verdictView } from '../run/selectors'
import { RUN_SAMPLE } from '../run/__fixtures__/run-sample'
import { BANNED_WORD, renderedText } from '../test/copyLaw'
import { VerdictsPageView, type VerdictsPageViewProps } from './ResultsPage'

const view = verdictView(fold(RUN_SAMPLE))

const render = (props: Partial<VerdictsPageViewProps> = {}) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <VerdictsPageView
        latest={null}
        earlier={[]}
        loading={false}
        failed={false}
        onRetry={() => {}}
        {...props}
      />
    </MemoryRouter>,
  )

describe('VerdictsPageView', () => {
  it('renders the latest answer and every earlier verdict', () => {
    const html = render({
      latest: {
        runId: 'r1',
        question: 'Should we expand into the European market in 2027?',
        view: view!,
        sources: ['eu-market-2027.pdf'],
        corpusMissing: false,
      },
      earlier: [{ runId: 'r0', question: 'Should we hire?', stance: 'POSITIVE', share: 0.74, date: '2026-10-09T10:00:00Z' }],
    })
    expect(html).toContain('Should we expand into the European market in 2027?')
    expect(html).toContain('Should we hire?')
    expect(html).toContain('0.74')
    expect(html).toContain('/runs/r0')
  })

  it('renders the empty state and the failure state', () => {
    expect(render({ latest: null, earlier: [] })).toContain('Your first answer appears here')
    const failed = render({ latest: null, earlier: [], failed: true })
    expect(failed).toContain('reach the server')
    expect(failed).toContain('Try again')
  })

  it('carries no banned word', () => {
    expect(renderedText(render())).not.toMatch(BANNED_WORD)
  })
})
