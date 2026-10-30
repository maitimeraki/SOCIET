import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): render to static
// markup in Node instead.
import { renderToStaticMarkup } from 'react-dom/server'
import Field from './Field'
import Input from './Input'
import NumberField from './NumberField'

describe('the field notebook', () => {
  // Regression guard: a bare control must carry the Quiet Room box itself, and a shrink-wrapped
  // one (society/ConfigPanel.tsx, a w-24 NumberField) must keep the box on the control rather
  // than on the grid cell.
  it('sets the control on the Quiet Room box — 48px, paper, one record rule, the 8px corner', () => {
    const input = renderToStaticMarkup(<Input />)
    expect(input).toContain('h-12')
    expect(input).toContain('bg-paper')
    expect(input).toContain('border-rule')
    expect(input).toContain('rounded-sm')
    expect(renderToStaticMarkup(<NumberField value={3} min={1} max={9} onChange={() => {}} />)).toContain('h-12')
    expect(renderToStaticMarkup(<Input prefix="N51°" />)).toContain('h-12')
  })

  it('keeps the box on the control, not on the Field row, which stretches past it', () => {
    const html = renderToStaticMarkup(
      <Field label="Corpus name">
        <Input />
      </Field>,
    )
    const rowTag = html.slice(0, html.indexOf('>') + 1) // the row's opening tag (F4: a <div>, the
    // note having moved out of the <label> so it is described, not named)
    expect(rowTag).toContain('<div')
    expect(rowTag).not.toContain('h-12')
    expect(html).toContain('<input class="h-12') // …and the control does carry the box
  })

  it('reserves the margin unconditionally, so an error never moves the control', () => {
    const plain = renderToStaticMarkup(<Field label="Name" hint="2–60 characters"><Input /></Field>)
    const invalid = renderToStaticMarkup(<Field label="Name" error="That name is taken."><Input /></Field>)
    expect(plain).toContain('pl-2.5')
    expect(invalid).toContain('pl-2.5')
    expect(invalid).toContain('field-invalid')
    expect(plain).not.toContain('field-invalid')
  })

  it('announces the error and sets the message in the danger hue', () => {
    const html = renderToStaticMarkup(<Field label="Name" error="That name is taken."><Input /></Field>)
    expect(html).toContain('role="alert"')
    expect(html).toContain('That name is taken.')
    expect(html).toContain('text-danger')
  })

  it('keeps the note out of the label, so it describes the control rather than naming it (F4)', () => {
    const html = renderToStaticMarkup(<Field label="Name" error="That name is taken."><Input /></Field>)
    const label = html.slice(html.indexOf('<label'), html.indexOf('</label>'))
    expect(label).toContain('Name')
    expect(label).not.toContain('That name is taken.')
  })

  it('references the note from the control by id, as a description (F4)', () => {
    const html = renderToStaticMarkup(<Field label="Name" error="That name is taken."><Input /></Field>)
    const noteId = html.match(/<span id="([^"]+)" role="alert"/)?.[1]
    expect(noteId).toBeTruthy()
    expect(html).toContain(`aria-describedby="${noteId}"`)
    expect(html).toContain(`aria-errormessage="${noteId}"`)
  })

  it('forwards ARIA description onto the number control (F5)', () => {
    const html = renderToStaticMarkup(
      <NumberField value={3} min={1} max={9} onChange={() => {}} aria-describedby="note" aria-invalid />,
    )
    expect(html).toContain('aria-describedby="note"')
    expect(html).toContain('aria-invalid="true"')
  })
})
