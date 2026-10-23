import type { FiledDecision } from '../components/ui/FiledSheet'

/* ── the auth surface's copy ─────────────────────────────────────────────────────────────────────
   Every customer-visible word on the sign-in and sign-up pages lives here, so a line is written
   once and never drifts between the two forms. The frame (`AuthLayout`) and the two pages read
   the same module.

   Every string below passes §12.5's copy law: the panel is a panel of **experts**, the material
   is **documents**, and the answer is **filed** — never an agent, a graph, a node, a round, a
   chunk or a job. The slots §14.2 marks *finalisable* are finalisable here. */

/** The wordmark's descriptor — §12.4 Wave A: what this product is, in two words. */
export const DESCRIPTOR = 'Decision panel'

/** The right column's thesis — the shape of the answer, not a feature list. */
export const THESIS = 'A panel of experts reads your documents, argues the question, and files an answer.'

/** The sign-in form's own words. */
export const SIGN_IN = {
  heading: 'Sign in',
  /** Names the act of **returning** — where the visitor was when they left. */
  lead: 'Come back and pick up where you left off.',
  action: 'Sign in',
  /** The success stamp: the mark the account is now open. */
  stamp: 'Signed in',
  crossQuestion: 'No account yet?',
  crossAction: 'Start free',
} as const

/** The sign-up form's own words. */
export const SIGN_UP = {
  /** Names the act of **opening an account** — not a place and not a form. */
  heading: 'Create your account',
  lead: 'An email and a password — no more is asked.',
  action: 'Start free',
  /** The success stamp: the mark the account is now open. */
  stamp: 'Signed up',
  /** The cost, stated once, on this form only (D2). */
  cost: 'Free to use. No account card, no trial, no tier.',
  crossQuestion: 'Already have an account?',
  crossAction: 'Sign in',
} as const

/**
 * The worked example — the product's own filed decision, the same one the homepage's comparison
 * panel shows, so the two surfaces rhyme by construction rather than by discipline. The values are
 * copied here rather than imported: `marketing/**` is another task's, and the boundary forbids it.
 *
 * It is labelled a worked example wherever it is rendered (house style rule 9 — nothing is claimed
 * that the product does not do), so it is never read as the visitor's own answer.
 */
export const WORKED_EXAMPLE: FiledDecision = {
  question: 'Should Ridgeline Coffee open a second location on Mill Street this spring?',
  position: 'NEGATIVE',
  share: 0.82,
  caseAgainst: 'If the grease-trap work lands on time, the Mill Street economics hold.',
  sources: 'Mill Street lease · economics · grease-trap certification · Alder Lane lease',
}
