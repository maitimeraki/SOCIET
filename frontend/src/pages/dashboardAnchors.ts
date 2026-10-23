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

/** The four retired routes and where each now lands. `/runs/:runId` stays a deep view. */
export const LEGACY_SECTION_REDIRECTS: { path: string; anchor: DashboardAnchor }[] = [
  { path: '/documents', anchor: DASHBOARD_ANCHORS.material },
  { path: '/runs', anchor: DASHBOARD_ANCHORS.decisions },
  { path: '/results', anchor: DASHBOARD_ANCHORS.lastAnswer },
  { path: '/panel', anchor: DASHBOARD_ANCHORS.panel },
]
