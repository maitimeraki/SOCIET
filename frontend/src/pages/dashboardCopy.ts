/**
 * The dashboard's copy, in one place (§14.3's copy shape). Every string here is customer-visible,
 * so the copy law (§12.5) applies to it and the rendered-string tests scan it. The four section
 * headings are fixed by D1; the rest is the surface's own voice.
 */
export const DASHBOARD_COPY = {
  title: 'Your account',
  lead: 'Your material, your decisions, the last answer, your panel.',
  trust: 'Your panel is drawn from your own material.',
  /** D2: the door's label is fixed. */
  startFree: 'Start free',
  sections: {
    material: {
      title: 'Your material',
      lead: 'Everything your panel argues from.',
    },
    decisions: {
      title: 'Your decisions',
      lead: 'Every question you have brought, newest first.',
    },
    lastAnswer: {
      title: 'The last answer',
      lead: 'The newest decision that has filed an answer.',
    },
    panel: {
      title: 'Your panel',
      lead: 'The experts who argued your last answer.',
    },
  },
  empty: {
    account: 'Start with your material — everything else follows from it.',
    material: 'Add your first document. Everything your panel argues from comes from here.',
    decisions: 'No decisions yet. Every question you bring is listed here, with how it ended.',
    lastAnswer: 'Your first answer appears here when a decision files one.',
    panel: 'No panel yet. Your panel is convened when your first decision starts.',
    notAnswered: 'This decision has not filed an answer yet.',
  },
  actions: {
    upload: 'Upload documents',
    openDecision: 'Open this decision',
    loadMore: 'Load more',
    retry: 'Try again',
  },
  error: {
    title: "Couldn't reach the server",
    material: 'Your material loads when the server is back.',
    decisions: 'Your decisions load when the server is back.',
    lastAnswer: 'Your last answer loads when the server is back.',
    panel: 'Your panel loads when the server is back.',
  },
} as const
