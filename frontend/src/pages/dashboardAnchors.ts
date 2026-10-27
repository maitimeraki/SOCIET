/**
 * The dashboard's four anchors and the legacy routes that redirect to them (D1). The ids live here
 * so the page, the redirect table and the tests read one list — a renamed anchor cannot leave a
 * redirect pointing at nothing.
 */
export const DASHBOARD_ANCHORS = {
  material: 'material',
  decisions: 'decisions',
  lastAnswer: 'last-answer',
  panel: 'panel',
} as const

export type DashboardAnchor = (typeof DASHBOARD_ANCHORS)[keyof typeof DASHBOARD_ANCHORS]

/** The href a legacy route redirects to: the dashboard, with its section's anchor. */
export const dashboardHref = (anchor: DashboardAnchor): string => `/dashboard#${anchor}`

/**
 * The anchor id a location hash names. A malformed escape (`#%`) is "no anchor", never a throw —
 * a URL the customer was handed must not take the page down (I3).
 */
export function anchorIdFromHash(hash: string): string | null {
  const raw = hash.replace(/^#/, '')
  if (raw.length === 0) return null
  try {
    return decodeURIComponent(raw)
  } catch {
    return null
  }
}

/**
 * The remaining retired route and where it lands. Documents, Runs and Verdicts are real pages again
 * (the three sections of the dashboard plan); only the panel is still folded into the dashboard.
 * `/runs/:runId` stays a deep view.
 */
export const LEGACY_SECTION_REDIRECTS: { path: string; anchor: DashboardAnchor }[] = [
  { path: '/panel', anchor: DASHBOARD_ANCHORS.panel },
]
