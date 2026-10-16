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
  // The hue each stance's symbol owns (DSPEC §3.1) — the symbol colour, never the word's.
  const HUE: Record<string, string> = {
    positive: 'var(--color-stance-pos)',
    neutral: 'var(--color-stance-neu)',
    ambivalent: 'var(--color-stance-amb)',
    negative: 'var(--color-stance-neg)',
  }

  it('pairs every stance hue with its own word in one legend entry', () => {
    // The stations emit the same hues, so a bare page-level `toContain` proves nothing about the
    // legend. Scope to the legend block and check each word against the hue in its OWN entry (R52).
    const marker = `aria-label="${hero.legendTitle}"`
    const start = html.indexOf(marker)
    const legend = html.slice(start, html.indexOf('</section>', start))
    const entries = legend.split('<li').slice(1)
    for (const [word, hue] of Object.entries(HUE)) {
      const entry = entries.find((chunk) => chunk.includes(word))
      expect(entry, `a legend entry for "${word}"`).toBeDefined()
      expect(entry).toContain(hue)
    }
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

describe('the sheet composes in the spec order', () => {
  it('renders the six sections in DSPEC §7.1 order', () => {
    const order = [
      sections.demo.heading,
      sections.howItWorks.heading,
      sections.comparison.heading,
      sections.trust.heading,
      sections.record.heading,
      sections.faq.heading,
    ]
    const positions = order.map((heading) => html.indexOf(heading))
    expect(positions.every((position) => position >= 0)).toBe(true)
    expect([...positions].sort((a, b) => a - b)).toEqual(positions)
  })

  it('leaves no unresolved value in the markup', () => {
    expect(html).not.toContain('undefined')
    expect(html).not.toContain('NaN')
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
