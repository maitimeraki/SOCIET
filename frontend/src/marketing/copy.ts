/**
 * Every word the marketing surface says lives here — the layout components carry no literals
 * (plan §6, the cheap i18n prep). Two laws bind this file:
 *
 *  1. **The honesty law** (task-17 addendum): no fabricated commercial claims, customers,
 *     testimonials, benchmarks, logos, or media. Where an asset is absent, the copy says so, and
 *     where proof is wanted the section proves the mechanism by showing the mechanism.
 *  2. **The copy law** (§13): no customer-visible string carries banned machinery words — the
 *     vocabulary is the customer's: decision, material/documents, experts/panel, position, pass,
 *     answer, opposing case, sources.
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

/**
 * The captures. Each is a screenshot of the running product, taken from one real decision and
 * served from `public/captures/` — never a mock, never an illustration. A capture that could not
 * be taken does not ship and the layout is built without it, so nothing here stands in for a
 * surface that does not work. `alt` says what the frame shows; `width`/`height` are the file's own
 * pixels, so the space is held before the image loads.
 */
export const captures = {
  /** The filed answer, from the decision it answers to the reasoning behind it. */
  answer: {
    src: '/captures/answer.png',
    alt: 'The filed answer on screen: the question the panel was asked, the answer it filed, and the reasoning behind it.',
    width: 1036,
    height: 1390,
  },
  /** The same document further down: the confidence, and the opposing case kept whole beside it. */
  opposingCase: {
    src: '/captures/opposing-case.png',
    alt: 'The same document further down: the confidence the panel reached and the opposing case, kept whole rather than averaged away.',
    width: 1036,
    height: 1372,
  },
  /** The workspace itself, at the step where the documents are added. */
  workspace: {
    src: '/captures/workspace-material.png',
    alt: 'The workspace: the rail of Documents, Decisions, Verdicts and Panel beside three documents that were added and read.',
    width: 2880,
    height: 1920,
  },
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
 * The lower sections. There are no recordings, captures, customers, logos, testimonials or
 * benchmarks to show, so every section proves the mechanism itself: what the product does, what it
 * leaves behind, and the limits that come with it. Nothing here imitates evidence.
 */
export const sections = {
  open: {
    heading: 'The decision, in the open',
    note: 'There is no recording on this page yet, and nothing here pretends to be one. What the product does is visible while it runs, so the work is shown rather than described after the fact.',
    stagesTitle: 'While a decision runs',
    /** Three moments a person can watch. Each is product behaviour, not a re-enactment. */
    stages: [
      {
        key: '1',
        title: 'Your material, being read',
        body: 'Add the documents the decision turns on. As each one is read, what it contains appears on the map — the same map you will use to judge the answer.',
      },
      {
        key: '2',
        title: 'The panel, arguing in passes',
        body: 'The experts who argue are drawn from your documents, not from a fixed cast. Each pass pairs them over what their material shares; you watch the pairings, the turns, and the positions change.',
      },
      {
        key: '3',
        title: 'The answer, filed with its case',
        body: 'The decision closes on an answer, the opposing case, the position each expert took, and the sources each argued from. Nothing is summarised away to make the answer look tidier.',
      },
    ],
    /** The opposing-case frame's caption — the same filed answer, further down the same document. */
    caseCaption:
      'The same decision further down: the confidence the panel reached, with the opposing case kept whole beside it.',
    /** The workspace capture's caption — what the frame is, in the order the reader sees it. */
    captureCaption: 'The workspace, with three documents already read — the rail on the left, the material beside it.',
    /** The recording is absent. Saying so is the honest state — never a player or a frame. */
    honesty:
      'No recording yet. When one exists it will be an unedited capture of a real decision, not a re-enactment.',
  },
  howItWorks: {
    heading: 'How it works',
    note: 'Four movements, always in the same order: add your material, convene the panel, let it argue in passes, file the answer.',
    orderTitle: 'The order',
    /** The four movements. Each body is a claim the product actually keeps. */
    steps: [
      {
        key: 'A',
        title: 'The material',
        body: 'You add your own documents. They are read into one map of your material, which stays visible from the first document to the filed answer.',
      },
      {
        key: 'B',
        title: 'The panel',
        body: 'The experts are drawn from that material, never from a fixed cast. Each one is written up with the position it takes, its confidence, and its conviction.',
      },
      {
        key: 'C',
        title: 'The passes',
        body: 'Experts are paired over what their documents share and argue in passes. Every turn is written back to the map before the next pass reads it, so a later view can answer an earlier one.',
      },
      {
        key: 'D',
        title: 'The answer',
        body: 'The panel’s views are weighted by confidence and conviction, and the answer is the weighted share behind each position. A split panel is filed as a split, with the opposing case kept whole.',
      },
    ],
    /** The five things a finished decision leaves behind. */
    gainsTitle: 'What you get',
    gains: [
      { key: '1', label: 'the answer', body: 'The position the weighted panel settles on, filed as a document.' },
      { key: '2', label: 'the opposing case', body: 'The strongest case against the answer, kept whole rather than averaged away.' },
      { key: '3', label: 'the positions', body: 'The position each expert took, and how the panel divided behind the answer.' },
      { key: '4', label: 'the sources', body: 'The material each expert argued from, traceable to the section it was read from.' },
      { key: '5', label: 'the record', body: 'Every decision is kept; reopen one and it renders exactly as it ended, pass by pass.' },
    ],
  },
  comparison: {
    heading: 'How it differs',
    note: 'A comparison of mechanisms, not of vendors: one answer from one voice, against a panel decision drawn from your material.',
    approachColumn: 'What a decision needs',
    columns: ['A single answer', 'A panel decision'],
    /** Defensible structural differences only — no named third party, no invented capability. */
    rows: [
      {
        label: 'Who forms the view',
        cells: [
          'One voice, answering once.',
          'Experts drawn from your own documents, each with a position.',
        ],
      },
      {
        label: 'What a claim rests on',
        cells: [
          'The answer, as written.',
          'The source in your material that the expert argued from.',
        ],
      },
      {
        label: 'What happens to disagreement',
        cells: [
          'One voice, one answer.',
          'The opposing case is kept whole and shown beside the answer.',
        ],
      },
      {
        label: 'What confidence means',
        cells: [
          'Whatever the answer says about itself.',
          'The weighted share of the panel behind the position, with the figures it came from.',
        ],
      },
      {
        label: 'What you keep',
        cells: [
          'The answer.',
          'A filed decision — the answer, opposing case, positions and sources — that reopens as it ended.',
        ],
      },
    ],
    reconciliation:
      'This contrasts how two mechanisms are built, not what any other product does. No third-party capability is claimed or measured.',
  },
  trust: {
    heading: 'What this tool does — and does not',
    note: 'No badges, testimonials or certifications are shown, because none exist. These are properties built into how the product works — and the limits that come with them.',
    doesTitle: 'What it does',
    does: [
      {
        label: 'It runs on your machine',
        body: 'The documents, the map and every decision stay on the machine running the tool.',
      },
      {
        label: 'Every claim has a source',
        body: 'Each answer names the material each expert argued from, traceable to the section it was read from.',
      },
      {
        label: 'Every decision is kept',
        body: 'A finished decision reopens and renders exactly as it ended, pass by pass.',
      },
    ],
    doesNotTitle: 'What it does not do',
    doesNot: [
      {
        label: 'It cannot invent a panel',
        body: 'The experts are drawn only from what you add. With no documents there is no panel and no answer.',
      },
      {
        label: 'It does not guarantee the answer',
        body: 'Confidence is the weighted share behind the position. It measures the panel, not the truth; a split is filed as a split.',
      },
      {
        label: 'It does not keep the text from your provider',
        body: 'The text your experts read and write goes to the provider you configure. Point it at a provider on your own machine if it must not leave.',
      },
    ],
  },
  record: {
    heading: 'The record',
    note: 'Every decision is filed as a document. This is the shape of that document, not a sample decision — no invented answer, no borrowed source.',
    filedLabel: 'Decision · filed',
    shapeLabel: 'What the document holds',
    /** The fields of a filed decision. Labelled as structure, never populated with invented content. */
    fields: [
      { key: 'answer', label: 'The answer', body: 'The position the panel settled on.' },
      { key: 'case', label: 'The opposing case', body: 'The strongest case against it, kept whole.' },
      { key: 'positions', label: 'The positions', body: 'The position each expert took, and how the panel divided.' },
      { key: 'sources', label: 'The sources', body: 'The material each expert argued from, with the section it came from.' },
      { key: 'passes', label: 'The passes', body: 'Every turn in order, so reopening the decision shows exactly what was argued.' },
    ],
    keepLabel: 'Kept, not summarised',
    keepNote: 'The record is the same document on screen and when it leaves the app. A finished decision reopens as it ended.',
  },
  faq: {
    heading: 'Questions owners ask',
    note: 'The questions owners actually ask, answered from how the product behaves — no more, no less.',
    items: [
      {
        q: 'What is Societas?',
        a: 'A local tool that reads the documents your experts would have read, maps what is in them, and convenes a panel of experts drawn from that material to argue one question to an answer.',
      },
      {
        q: 'Do I need my own documents?',
        a: 'Yes. The panel is built from your material: no documents, no panel. Add the documents the decision turns on to begin.',
      },
      {
        q: 'What happens when I start a decision?',
        a: 'Your question is read for what it is asking. Possible experts are weighed against your material; each selected one is written up with a position and a confidence; then the passes begin — experts are paired over what they share, argue, and every turn is written back to the map before the next pass reads it.',
      },
      {
        q: 'How is the answer decided?',
        a: 'Each expert’s view is weighted by its confidence and conviction, and the answer is the weighted share behind each position. If no position has a clear majority, the answer says so plainly: a split, not a verdict.',
      },
      {
        q: 'Can experts change their minds?',
        a: 'Yes, and you can watch it happen: later passes read what earlier passes wrote, and each expert’s final position is its last turn.',
      },
      {
        q: 'Where does my data live?',
        a: 'The documents, the map and every decision stay on the machine running the tool. The text your experts read and write goes to the provider you configure — point it at a provider on your own machine if you want it to stay home.',
      },
      {
        q: 'Which providers work?',
        a: 'The one you configure. The product is not tied to a single provider, and a local provider keeps the text on your machine.',
      },
      {
        q: 'How long does a decision take?',
        a: 'It runs while you watch, and progress is shown as it happens; the time depends on how much material you add and the provider you choose. Nothing is hidden until the end.',
      },
      {
        q: 'Can I see what happens inside?',
        a: 'That is the point of the tool: you can see why each expert was chosen, who argued with whom, what each one said, and the sources behind the answer.',
      },
      {
        q: 'What happens to finished decisions?',
        a: 'They are kept. Reopen one and it renders exactly as it ended, pass by pass, with its answer, opposing case, positions and sources — or take the document away.',
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
