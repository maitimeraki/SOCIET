import { describe, expect, it } from 'vitest'
// No jsdom / no testing-library in this repo (see AppErrorBoundary.test.tsx): static markup in Node.
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { JobStatus, User } from '../api/types'
import { BANNED_TERMS, renderedText } from '../test/copyLaw'
import { AccountPageView, deleteMatches, exportTick, type AccountPageViewProps } from './AccountPage'

const USER: User = {
  id: 'u1',
  email: 'ada@example.com',
  created_at: '2026-01-01T00:00:00Z',
  role: 'user',
  plan: 'free',
  entitlements: {
    max_agents: 10,
    max_rounds: 3,
    units_remaining: 12,
    period_end: '2026-12-01T00:00:00Z',
  },
}

const render = (props: Partial<AccountPageViewProps> = {}) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <AccountPageView
        user={USER}
        exporting={false}
        exportProgress={null}
        exportError={null}
        onExport={() => {}}
        confirm=""
        onConfirmChange={() => {}}
        deleting={false}
        deleteError={null}
        onDelete={() => {}}
        {...props}
      />
    </MemoryRouter>,
  )

const job = (
  patch: Partial<JobStatus<{ object_key?: string }>> = {},
): JobStatus<{ object_key?: string }> => ({
  job_id: 'j1',
  status: 'running',
  stage: 'export',
  progress: 0,
  ...patch,
})

/** The delete control's opening tag, and its `disabled` ATTRIBUTE (the classes mention `disabled:`). */
const deleteButton = (html: string) => html.match(/<button[^>]*>Delete my account<\/button>/)?.[0] ?? ''
const disabled = (button: string) => /\sdisabled(?:="")?(?=[\s>])/.test(button.slice(0, button.indexOf('>')))

describe('AccountPageView — the account record', () => {
  it('shows the email, plan, role and the plan caps', () => {
    const html = render()
    expect(html).toContain('ada@example.com')
    expect(html).toContain('Free')
    expect(html).toContain('Member')
    expect(html).toContain('Up to 10')
    expect(html).toContain('Up to 3')
    expect(html).toContain('1 Dec 2026')
  })

  it('renders both the export and the delete panels', () => {
    const html = render()
    expect(html).toContain('Download my data')
    expect(html).toContain('Delete my account')
  })
})

describe('AccountPageView — delete needs the typed email', () => {
  it('keeps the delete button disabled until the address matches', () => {
    expect(disabled(deleteButton(render({ confirm: '' })))).toBe(true)
    expect(disabled(deleteButton(render({ confirm: 'ada@wrong.com' })))).toBe(true)
  })

  it('enables it once the account email is typed, case-insensitively', () => {
    const html = render({ confirm: 'ADA@EXAMPLE.COM' })
    expect(deleteMatches(USER.email, 'ADA@EXAMPLE.COM')).toBe(true)
    expect(disabled(deleteButton(html))).toBe(false)
  })
})

describe('AccountPageView — honest failure states', () => {
  it('shows the server’s export error with a retry', () => {
    const html = render({ exportError: 'Your export could not be prepared.' })
    expect(html).toContain('Your export could not be prepared.')
    expect(html).toContain('Try again')
  })

  it('shows the server’s delete error in place, never a silent success', () => {
    expect(render({ deleteError: 'That confirmation did not match.' })).toContain(
      'That confirmation did not match.',
    )
  })

  it('reads the poll tick fraction as a percentage', () => {
    expect(exportTick(job({ progress: 0.4 })).percent).toBe(40)
    expect(exportTick(job({ progress: 0.01 })).percent).toBe(1)
    expect(exportTick(job({ progress: 1 })).percent).toBe(100)
  })

  it('clamps a malformed tick into 0–100', () => {
    expect(exportTick(job({ progress: -1 })).percent).toBe(0)
    expect(exportTick(job({ progress: 3 })).percent).toBe(100)
  })

  it('reads the signed URL from the job doc’s top level, not result', () => {
    const tick = job({ status: 'completed', progress: 1, download_url: 'https://signed.example/x' })
    expect(exportTick(tick).url).toBe('https://signed.example/x')
    expect(exportTick(job({})).url).toBeNull()
  })

  it('announces progress while the export is prepared', () => {
    const html = render({ exporting: true, exportProgress: exportTick(job({ progress: 0.4 })).percent })
    expect(html).toContain('role="status"')
    expect(html).toContain('Preparing your download — 40%')
  })
})

describe('AccountPageView — the copy law', () => {
  it('renders no banned word on the whole page', () => {
    expect(renderedText(render({ confirm: 'ADA@EXAMPLE.COM' }))).not.toMatch(BANNED_TERMS)
  })
})
