import type { VerdictSheetProps } from '../components/ui/VerdictSheet'

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

/** §7.2 — the one promise the page makes about the material, under the form on both doors. */
export const TRUST_LINE = 'Your documents are used only to answer your questions; export or delete them anytime.'

/** The sign-in form's own words. */
export const SIGN_IN = {
  heading: 'Welcome back',
  action: 'Sign in',
  /** The success stamp: the mark the account is now open. */
  stamp: 'Signed in',
  /** The one recovery affordance — no reset flow is built, so it reaches the operator. */
  forgot: 'Forgot password?',
  forgotHref: 'mailto:hello@societas.app?subject=Password%20reset',
  crossQuestion: 'No account yet?',
  crossAction: 'Create an account',
} as const

/** The sign-up form's own words. */
export const SIGN_UP = {
  heading: 'Start your first decision',
  action: 'Create account',
  /** The success stamp: the mark the account is now open. */
  stamp: 'Signed up',
  /** The cost, stated once, on this form only (D2). */
  cost: 'Free to start · No card',
  crossQuestion: 'Already have an account?',
  crossAction: 'Sign in',
} as const

/**
 * §7.2's evidence panel — the product's own filed decision, cropped to the fragment that proves
 * what an account is for. It is the same Ridgeline Coffee example the homepage tells, labelled a
 * worked example in the surrounding copy: no customer, no logo and no figure is invented, and the
 * share is the example's recorded 0.82.
 */
export const EVIDENCE_LABEL = 'A filed decision · example'

export const EVIDENCE_CAPTION = 'A worked example, prepared to show what a filed answer looks like.'

export const EXAMPLE_VERDICT: VerdictSheetProps = {
  question: 'Should Ridgeline Coffee open a second location on Mill Street this spring?',
  filed: '22 Oct 2026',
  position: 'NEGATIVE',
  share: 0.82,
  caseAgainst: 'If the grease-trap work lands on time, the Mill Street economics hold.',
  // The panel is cropped to the fragment; the reasoning and the view split are not shown here.
  reasoning: [],
  whoHeldWhichView: [],
  sources: [
    { document: 'Mill Street lease.pdf', reference: 'p.4' },
    { document: 'Demand study', reference: 'p.11' },
  ],
}
