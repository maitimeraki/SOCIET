/**
 * Every word the marketing surface says lives here — the layout components carry no literals
 * (plan §6, the cheap i18n prep). Two laws bind this file:
 *
 *  1. **The honesty law** (task-17 addendum): no fabricated commercial claims, customers,
 *     testimonials, benchmarks, logos, or media. Where an asset is absent, the copy says so.
 *  2. **The copy law** (§13): no customer-visible string carries banned machinery words — the
 *     vocabulary is the world's: the material, the map, the panel, the argument, the verdict.
 */

export const meta = {
  wordmark: 'Societas',
  descriptor: 'Decision panel',
  /**
   * Mirrors `package.json` "version" — the footer's edition stamp. The build has no version
   * define yet (no `resolveJsonModule`), so this is the one hand-kept mirror; wire a build define
   * when the version starts moving.
   */
  version: '0.0.0',
} as const

export const hero = {
  /** The account bar's accessible name. */
  navLabel: 'Account',
  signIn: { label: 'Sign in', to: '/auth/signin' },
  startFree: { label: 'Start free', to: '/auth/signup?next=/new' },
  /** The fixed claim — a feeling, not a topic. */
  headline: "A decision you can't look up.",
  support:
    'A panel of experts reads your documents, argues the question, and files a verdict — with the confidence and the case against.',
  /** The one primary action in the first viewport. `next` lands a new owner where the work begins:
      `/new`, the step where the first document is added. */
  primary: { label: 'Start your first decision', to: '/auth/signup?next=/new' },
} as const

/**
 * The section bodies are Task 6.2's. Each `note` is the section's honest, minimal state — real
 * product truth, never a promise the tool cannot keep.
 */
export const sections = {
  demo: {
    heading: 'The recording',
    note: 'The demo recording is not published yet. This frame is wired for it: a real, unedited capture of a decision, with captions and a transcript.',
    poster: 'recording coming',
    frameLabel: 'Recording',
    /** The honest caption under the plate — the frame is real, the recording is not. */
    plateCaption: 'No recording yet — this frame is wired for a real, unedited capture.',
    transcriptLabel: 'Transcript',
    transcript: 'The transcript lands with the recording.',
  },
  howItWorks: {
    heading: 'How it works',
    note: 'The mechanism in four steps — the material → the panel → the argument → the verdict. Each step keys to its legend.',
    traverseLegendTitle: 'The order',
    /** The four steps. Each body is a claim the product actually keeps. */
    steps: [
      {
        key: 'A',
        title: 'The material',
        body: 'You bring the documents your experts would have read. Every piece is read into a map of your material. No documents, no map; no map, no panel.',
      },
      {
        key: 'B',
        title: 'The panel',
        body: 'The panel is drawn from your map, never pre-set: candidates are ranked against your question, and each selected one is written up into an expert with a position, a confidence, and a conviction.',
      },
      {
        key: 'C',
        title: 'The argument',
        body: 'Each pass pairs experts over what they share — a query against the map, not a script — and the pairs argue. Every turn is written back to the map before the next pass reads it.',
      },
      {
        key: 'D',
        title: 'The verdict',
        body: 'Every turn is weighted by confidence × conviction × CIOR, and the verdict is the weighted share per position. Dissent is kept, not averaged: a plurality is filed as a plurality.',
      },
    ],
    /** The legend of what you get: five keyed lines, symbol + word. */
    gainsTitle: 'What you get',
    gains: [
      { key: '1', label: 'verdict', body: 'The position the weighted panel settles on, filed as a document.' },
      { key: '2', label: 'confidence', body: 'A weighted confidence, not a vibe: the share behind the verdict, with the figures it came from.' },
      { key: '3', label: 'dissent', body: 'The case against, kept whole — the minority readings, never averaged away.' },
      { key: '4', label: 'provenance', body: 'A contents map back to your material: every claim traceable to the section it was read from.' },
      { key: '5', label: 'replay', body: 'The whole decision, kept — reopen a finished one and the map redraws exactly as it ended.' },
    ],
  },
  comparison: {
    heading: 'How it differs',
    note: 'Societas against a single chatbot and a scripted assistant — on structure, provenance, dissent, and verdict confidence.',
    approachColumn: 'Approach',
    columns: ['Structure', 'Provenance', 'Dissent', 'Verdict confidence'],
    /** Truthful structural differences only — no invented competitor capability, no benchmark. */
    rows: [
      {
        label: 'Single chatbot',
        cells: [
          'One assistant, one context window — a single answer, no panel.',
          'None recorded; the answer cites nothing.',
          'None — one voice.',
          'None measured.',
        ],
      },
      {
        label: 'Scripted assistant',
        cells: [
          'A fixed sequence of steps; the steps are authored, not drawn from your material.',
          'Whatever the chain passes along — nothing kept, nothing to trace.',
          'Dropped between steps.',
          'None measured.',
        ],
      },
      {
        label: 'Societas',
        cells: [
          'A panel drawn from your own material; experts paired over what they share, pass after pass.',
          'Every turn written back to the map it was drawn from, with a contents map to the source.',
          'Kept and shown — the minority readings, never averaged away.',
          'A CIOR-weighted share per position.',
        ],
      },
    ],
    reconciliation:
      'The difference is structural, not a matter of quality: where the debaters come from, what each turn leaves behind, and whether the case against survives.',
  },
  trust: {
    heading: 'Your record stays yours',
    note: 'Documents stay in your map. Your data is never used for training. Your history stays yours.',
    /** Each line is a claim the tool can keep — no certification it does not hold. */
    lines: [
      {
        label: 'Documents stay in your map',
        body: 'The documents, the map, and every decision stay on the machine running the tool.',
      },
      {
        label: 'No training on your data',
        body: 'Your data is never used to train anything. The text your experts read is sent only to the provider you configure.',
      },
      {
        label: 'Your history is yours',
        body: 'Every decision is kept and reopens exactly as it ended, pass by pass — export the whole thing as JSON whenever you want it.',
      },
      {
        label: 'You choose the provider',
        body: 'Over 100 providers through LiteLLM, or Ollama on your own machine — point it there and nothing leaves.',
      },
    ],
    /** May appear only in this form, marked unverified — never implied complete. */
    soc2: 'SOC 2 in progress — not yet certified.',
    soc2Marker: 'unverified',
  },
  record: {
    heading: 'The record',
    note: 'A finished decision shown as a document — the verdict, the confidence, the dissent kept, and the contents map back to the material.',
    /** The sample decision is scripted, like any authored example — labelled wherever it is shown. */
    syntheticLabel: 'Sample decision — a scripted example, not a live one',
    filedLabel: 'Decision · filed',
    fixLabel: 'The verdict',
    confidenceLabel: 'Confidence',
    closureLabel: 'closure',
    verdictWord: 'POSITIVE',
    confidence: 0.82,
    closure: 0.82,
    dissentLabel: 'Dissent, kept',
    dissent: 'NEGATIVE — margin erosion in the first two years outruns the tariff gain.',
    contentsLabel: 'Contents map',
    contents: [
      { entity: 'tariff alignment', source: 'EU Trade Brief 2026 · §3.2' },
      { entity: 'demand depth', source: 'Market Sizing Workbook · Demand' },
      { entity: 'compliance risk', source: 'Data-Readiness Note · §1' },
    ],
    /** The plate holds the figure's aspect until the real capture replaces it. */
    captureLabel: 'The map and the verdict',
    captureNote: 'No capture yet — this space is held for the real thing.',
  },
  faq: {
    heading: 'Questions owners ask',
    note: 'The questions owners actually ask, answered from how the product behaves — no more, no less.',
    items: [
      {
        q: 'What is Societas?',
        a: 'A local tool that reads the documents your experts would have read, maps what is in them, and convenes a panel of experts drawn from that material to argue one question to a weighted verdict.',
      },
      {
        q: 'Do I need my own documents?',
        a: 'Yes. The panel is built from your material: no documents, no map; no map, no panel. Add PDFs, Word files, Markdown, text, or a web page to begin.',
      },
      {
        q: 'What happens when I start a decision?',
        a: 'Your question is read for what it is asking; candidates are ranked against your map; each selected one is written up into an expert; then passes begin — experts are paired over what they share, answer with a position and a confidence, and every turn is written to the map before the next pass reads it.',
      },
      {
        q: 'How is the verdict decided?',
        a: 'Every turn is weighted by the expert’s confidence, conviction, and CIOR; the verdict is the weighted share per position. If the dominant share stays under the convergence threshold, the answer says so plainly: a plurality, not a consensus.',
      },
      {
        q: 'Can experts change their minds?',
        a: 'Yes, and you can watch it happen: later passes read what earlier passes wrote, and each expert’s final position is simply its last turn.',
      },
      {
        q: 'Where does my data live?',
        a: 'This is a local tool: the documents, the map, and every decision stay on the machine running it. The text your experts read and write goes to the provider you configure — point it at a local one if you want everything to stay home.',
      },
      {
        q: 'Which providers work?',
        a: 'Over 100, through LiteLLM: OpenAI, Anthropic, Azure, Bedrock, or Ollama on your own machine. Configure one and the decision runs against it.',
      },
      {
        q: 'How long does a decision take?',
        a: 'Reading your material takes about a minute per ten documents; the argument is a few minutes. Both show live progress — nothing is a black box.',
      },
      {
        q: 'Can I see what happens inside?',
        a: 'That is the point of the tool: the panel shows your question becoming experts, the floor shows pairings and turns live, and the details expose the selection scores, pairs, turns, warnings, and the raw event log.',
      },
      {
        q: 'What happens to finished decisions?',
        a: 'They are kept: reopen one and it renders exactly as it ended, pass by pass, with its verdict, warnings, and final positions — or export the whole thing as JSON.',
      },
    ],
  },
} as const

export const footer = {
  /**
   * The owner-supplied contact address. `.example` is IANA-reserved and can never resolve, so the
   * link cannot quietly reach a real, wrong inbox while the real address is unwritten.
   */
  // TODO(owner): replace with the real contact address before launch.
  contact: { label: 'Talk to us', href: 'mailto:hello@societas.example' },
  primary: { label: 'Start a decision', to: '/auth/signup?next=/new' },
  edition: 'Local-first',
} as const
