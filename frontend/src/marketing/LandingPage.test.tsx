import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import LandingPage from './LandingPage'
import { hero, heroStations, meta, sections } from './copy'

const html = renderToStaticMarkup(
  <MemoryRouter>
    <LandingPage />
  </MemoryRouter>,
)

const count = (needle: string) => html.split(needle).length - 1

describe('the sheet — the first viewport', () => {
  it('carries the question as the sheet title', () => {
    expect(html).toContain(hero.question)
  })

  it('offers both calls to action with their real targets', () => {
    expect(html).toContain('Begin a survey')
    expect(html).toContain('href="/auth/signup?next=/dashboard"')
    expect(html).toContain('See it run')
    expect(html).toContain('href="#field-recording"')
  })

  it('labels the plot synthetic, so a scripted survey is never read as a live run', () => {
    expect(html).toContain(hero.syntheticLabel)
  })
})

describe('the legend law', () => {
  it('pairs every stance hue with a drawn symbol and an ink word', () => {
    for (const word of ['positive', 'neutral', 'ambivalent', 'negative']) {
      expect(html).toContain(word)
    }
    expect(html).toContain('var(--color-stance-pos)')
    expect(html).toContain('var(--color-stance-neg)')
  })
})

describe('the sections compose from copy.ts', () => {
  it('renders every section heading', () => {
    for (const section of Object.values(sections)) {
      expect(html).toContain(section.heading)
    }
  })

  it('keeps the SOC 2 line in its one legal form — in progress, marked unverified', () => {
    expect(html).toContain('SOC 2 in progress — not yet certified')
    expect(html).toContain('unverified')
  })

  it('closes on the title block with the wordmark and the real actions', () => {
    expect(html).toContain(meta.wordmark)
    expect(html).toContain('Talk to us')
    expect(html).toContain('mailto:hello@societas.example')
  })
})

describe('the plotting hand — reduced motion', () => {
  it('renders the sheet complete: every station, the fix, and the closure figure', () => {
    expect(count('data-station')).toBe(heroStations.length)
    expect(heroStations).toHaveLength(9)
    expect(html).toContain(`closure ${hero.closure}`)
  })

  it('marks the animated plot so the reduced-motion rule has its hook', () => {
    // `marketing.css` targets `.hero-plot [data-plot]` under prefers-reduced-motion, settling each
    // move to its finished figure — so these markers are what makes the static sheet provable.
    expect(html).toContain('hero-plot')
    expect(count('data-plot="draw"')).toBeGreaterThan(0)
    expect(count('data-plot="fix"')).toBe(1)
  })
})
