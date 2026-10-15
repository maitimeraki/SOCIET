import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import Field from './Field'
import Input from './Input'
import NumberField from './NumberField'

describe('the field notebook', () => {
  // Regression guard for the two live failures: a bare control (pages/RunsPage.tsx) must carry the
  // focus affordance itself, and a shrink-wrapped one (society/ConfigPanel.tsx, a w-24 NumberField)
  // must register the mark on the control rather than on the grid cell.
  it('paints the registration tick on the control itself, bare or wrapped', () => {
    expect(renderToStaticMarkup(<Input />)).toContain('corner-tick')
    expect(renderToStaticMarkup(<NumberField value={3} min={1} max={9} onChange={() => {}} />)).toContain('corner-tick')
    expect(renderToStaticMarkup(<Input prefix="N51°" />)).toContain('corner-tick')
  })

  it('does not put the tick on the Field row, which stretches past the control', () => {
    const html = renderToStaticMarkup(
      <Field label="Corpus name">
        <Input />
      </Field>,
    )
    const rowTag = html.slice(0, html.indexOf('>') + 1) // the <label …> opening tag
    expect(rowTag).toContain('<label')
    expect(rowTag).not.toContain('corner-tick')
    expect(html).toContain('<input class="corner-tick') // …and the control does carry it
  })

  it('reserves the margin unconditionally, so an error never moves the control', () => {
    const plain = renderToStaticMarkup(<Field label="Name" hint="2–60 characters"><Input /></Field>)
    const invalid = renderToStaticMarkup(<Field label="Name" error="That name is taken."><Input /></Field>)
    expect(plain).toContain('pl-2.5')
    expect(invalid).toContain('pl-2.5')
    expect(invalid).toContain('field-invalid')
    expect(plain).not.toContain('field-invalid')
  })

  it('announces the error and keeps the message in ink, not in the route hue', () => {
    const html = renderToStaticMarkup(<Field label="Name" error="That name is taken."><Input /></Field>)
    expect(html).toContain('role="alert"')
    expect(html).toContain('That name is taken.')
    expect(html).toContain('text-ink-2')
    expect(html).not.toContain('text-route')
  })
})
