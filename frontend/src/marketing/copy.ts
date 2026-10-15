import type { Stance } from '../run/events'

/**
 * Every word the marketing surface says lives here — the layout components carry no literals
 * (plan §6, the cheap i18n prep). Two laws bind this file:
 *
 *  1. **The honesty law** (task-17 addendum): no fabricated commercial claims, customers,
 *     testimonials, benchmarks, logos, or media. Where an asset is absent, the copy says so.
 *  2. **The legend law** (DSPEC §3.1/§9): a hue has a symbol and the word is ink — so a station's
 *     stance is never spelled in its own colour.
 *
 * The sample survey is **synthetic and labelled as such** wherever a visitor could mistake it for a
 * real run: the geometry, the nine stations, and the closure figure are scripted, not measured.
 */

export const meta = {
  wordmark: 'Societas',
  descriptor: 'Survey & Deliberation',
  /**
   * Mirrors `package.json` "version" — the title block's edition stamp. The build has no version
   * define yet (no `resolveJsonModule`), so this is the one hand-kept mirror; wire a build define
   * when the version starts moving.
   */
  version: '0.0.0',
} as const

export const sheet = {
  /** The sheet's section nav — its accessible name. */
  navLabel: 'Sheet sections',
  nav: [
    { label: 'how it works', href: '#how-it-works' },
    { label: 'the record', href: '#the-record' },
    { label: 'questions', href: '#questions' },
  ],
} as const

export const hero = {
  /** The question IS the sheet's title — a real, honest example of what an owner brings. */
  question: 'Should you expand into Europe in 2027?',
  deck: 'A society of specialists, drawn from your own record, argues your decision and files a weighted verdict — with the confidence and the case against.',
  syntheticLabel: 'Synthetic sample survey — nine stations, scripted, not a live run',
  legendTitle: 'Legend',
  /** The plot's accessible name — the SVG `<title>`, with the closure figure interpolated. */
  plotTitle: (closure: number) =>
    `A scripted sample survey: nine stations on the sheet, the lines of sight traced between them, and the fix with a closure of ${closure}. Synthetic — not a live run.`,
  /** A station's accessible name — the hue carries the symbol; the word is ink, and lives only here. */
  stationTitle: (stance: Stance, entity: string) =>
    `${stance.toLowerCase()} station — ${entity} (synthetic)`,
  /** The closure figure the scripted fix settles on. */
  closure: 0.82,
  primary: { label: 'Begin a survey', to: '/auth/signup?next=/dashboard' },
  secondary: { label: 'See it run', href: '#field-recording' },
} as const

export interface HeroStation {
  readonly id: string
  readonly x: number
  readonly y: number
  readonly stance: Stance
  /** The synthetic shared entity the station stands on — carried in the accessible name only. */
  readonly entity: string
}

/** Nine scripted stations: three positive, two neutral, two ambivalent, two negative. */
export const heroStations: readonly HeroStation[] = [
  { id: 's1', x: 120, y: 130, stance: 'POSITIVE', entity: 'tariff alignment' },
  { id: 's2', x: 330, y: 300, stance: 'POSITIVE', entity: 'demand depth' },
  { id: 's3', x: 500, y: 150, stance: 'POSITIVE', entity: 'channel reach' },
  { id: 's4', x: 640, y: 300, stance: 'NEUTRAL', entity: 'regulatory load' },
  { id: 's5', x: 250, y: 420, stance: 'NEUTRAL', entity: 'currency drift' },
  { id: 's6', x: 790, y: 140, stance: 'AMBIVALENT', entity: 'localisation cost' },
  { id: 's7', x: 430, y: 430, stance: 'AMBIVALENT', entity: 'talent supply' },
  { id: 's8', x: 690, y: 440, stance: 'NEGATIVE', entity: 'margin erosion' },
  { id: 's9', x: 880, y: 300, stance: 'NEGATIVE', entity: 'compliance risk' },
]

/** Index pairs into `heroStations` — the sightlines the scripted plot traces between them. */
export const heroSightlines: readonly (readonly [number, number])[] = [
  [0, 2],
  [2, 1],
  [1, 0],
  [2, 3],
  [3, 6],
  [3, 8],
  [1, 6],
  [6, 7],
  [4, 1],
  [7, 8],
]

/**
 * The section bodies are Task 17b's. Each `note` is the section's honest, minimal state — real
 * product truth, never a promise the tool cannot keep.
 */
export const sections = {
  demo: {
    heading: 'The field recording',
    note: 'The demo recording is not published yet. This frame is wired for it: a real, unedited capture of a run, with captions and a transcript.',
    poster: 'demo video coming',
    frameLabel: 'Field recording',
    /** The honest caption under the plate — the frame is real, the recording is not. */
    plateCaption: 'No recording yet — this frame is wired for a real, unedited capture.',
    transcriptLabel: 'Transcript',
    transcript: 'The transcript lands with the recording.',
  },
  howItWorks: {
    heading: 'How it works',
    note: 'The mechanism in four ruled steps — record → stations → lines of sight → the fix. Each step keys to the legend.',
    traverseLegendTitle: 'The traverse',
    /** §7.1 §3 — the four ruled steps. Each body is a claim the product actually keeps. */
    steps: [
      {
        key: 'A',
        title: 'Record',
        body: 'You bring the documents your experts would have read. The tool reads them and grows a knowledge graph — the survey’s record. No documents, no graph; no graph, no stations.',
      },
      {
        key: 'B',
        title: 'Stations',
        body: 'Stations are drawn from your graph, never pre-set: candidates are ranked against your question, and each selected one is synthesised from its cluster into a specialist with a stance, a confidence, and a conviction.',
      },
      {
        key: 'C',
        title: 'Lines of sight',
        body: 'Each sweep pairs stations over the entities they share — a graph query, not a script — and the pairs deliberate. Every turn is written back to the graph before the next sweep reads it.',
      },
      {
        key: 'D',
        title: 'The fix',
        body: 'Every turn is weighted by confidence × conviction × CIOR, and the fix is the weighted share per stance. Dissent is kept, not averaged: a plurality is filed as a plurality.',
      },
    ],
    /** §7.1 §4 — the legend of what you get: five ruled lines, symbol + word, keyed. */
    gainsTitle: 'The legend of what you get',
    gains: [
      { key: '1', label: 'verdict', body: 'The fix — the stance the weighted society settles on, filed as a sheet.' },
      { key: '2', label: 'confidence', body: 'A weighted confidence, not a vibe: the share behind the fix, with the figures it came from.' },
      { key: '3', label: 'dissent', body: 'The case against, kept hatched — the minority readings, never averaged away.' },
      { key: '4', label: 'provenance', body: 'A contents map back to your record: every claim traceable to the chunk it was read from.' },
      { key: '5', label: 'replay', body: 'The whole survey, kept — reopen a finished run and it redraws exactly as it ended.' },
    ],
  },
  comparison: {
    heading: 'How it differs',
    note: 'Societas against a single chatbot and prompt-chained agents — on structure, provenance, dissent, and verdict confidence.',
    approachColumn: 'Approach',
    columns: ['Structure', 'Provenance', 'Dissent', 'Verdict confidence'],
    /** Truthful structural differences only — no invented competitor capability, no benchmark. */
    rows: [
      {
        label: 'Single chatbot',
        cells: [
          'One model, one context window — a single pass, no society.',
          'None recorded; the answer cites nothing.',
          'None — one voice.',
          'None measured.',
        ],
      },
      {
        label: 'Prompt-chained agents',
        cells: [
          'A fixed script of prompts run in sequence; the steps are authored, not drawn from a graph.',
          'Whatever the chain passes along — no graph, no committed record.',
          'Dropped between steps.',
          'None measured.',
        ],
      },
      {
        label: 'Societas',
        cells: [
          'A society drawn from your own graph; stations paired over shared entities, sweep after sweep.',
          'Every turn committed to the graph it was drawn from, with a contents map back to the source.',
          'Kept and shown — the minority readings, hatched.',
          'A CIOR-weighted share per stance.',
        ],
      },
    ],
    reconciliation:
      'The difference is structural, not a matter of quality: where the debaters come from, what each turn leaves behind, and whether the case against survives.',
  },
  trust: {
    heading: 'Your record stays yours',
    note: 'Documents stay in your graph. Your data is never used for training. Run history is yours.',
    /** Each line is a claim the tool can keep — no certification it does not hold. */
    lines: [
      {
        label: 'Documents stay in your graph',
        body: 'The corpus, the graph, and every run stay on the machine running the survey.',
      },
      {
        label: 'No training on your data',
        body: 'Your data is never used to train a model. The text agents read is sent to the provider you configure to answer your question.',
      },
      {
        label: 'Run history is yours',
        body: 'Every survey is kept and reopens exactly as it ended, sweep by sweep — export the whole run as JSON whenever you want it.',
      },
      {
        label: 'You choose the provider',
        body: 'Over 100 providers through LiteLLM, or a local model over Ollama — point it at a local model and nothing leaves the machine.',
      },
    ],
    /** May appear only in this form, marked unverified — never implied complete. */
    soc2: 'SOC 2 in progress — not yet certified.',
    soc2Marker: 'unverified',
  },
  record: {
    heading: 'The record',
    note: 'A finished survey shown as a sheet — the fix, the closure, the dissent hatched, and the contents map back to the record.',
    /** The sample run is scripted, like the hero's — labelled synthetic wherever it is shown. */
    syntheticLabel: 'Synthetic sample survey — a scripted run, not a live one',
    filedLabel: 'Survey · filed',
    fixLabel: 'The fix',
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
    /** Task 19 replaces the plate with a real capture; the slot keeps its aspect until then. */
    captureLabel: 'Capture lands in Task 19',
    captureNote: 'The plotting table mid-survey — a real capture, not a mock.',
  },
  faq: {
    heading: 'Questions owners ask',
    note: 'The questions owners actually ask, answered from how the product behaves — no more, no less.',
    /** Answers verified against the product in the retired HomePage FAQ; wording adapted to the sheet. */
    items: [
      {
        q: 'What is Societas?',
        a: 'A local tool that reads the documents your experts would have read, grows a knowledge graph from them, and convenes a society of AI specialists drawn from that graph to debate one question to a weighted verdict.',
      },
      {
        q: 'Do I need my own documents?',
        a: 'Yes. The society is built from your record: no documents, no graph; no graph, no stations. Add PDFs, Word files, Markdown, text, or a web page to begin.',
      },
      {
        q: 'What happens when I begin a survey?',
        a: 'Your question is read into intent terms; candidates are ranked against the graph; each selected specialist is synthesised from its cluster into a station; then sweeps begin — stations are paired over shared entities, answer with a stance and a confidence, and every sweep is written to the graph before the next one reads it.',
      },
      {
        q: 'How is the verdict decided?',
        a: 'Every turn is weighted by the specialist’s confidence, conviction, and CIOR; the fix is the weighted share per stance. If the dominant share stays under the convergence threshold, the sheet says so plainly: a plurality, not a consensus.',
      },
      {
        q: 'Can specialists change their minds?',
        a: 'Yes, and you can watch it happen: later sweeps read what earlier sweeps committed, and each specialist’s final stance is simply its last turn.',
      },
      {
        q: 'Where does my data live?',
        a: 'This is a local tool: the corpus, the graph, and every run stay on the machine running it. The text specialists read and write goes to the model provider you configure — point it at a local model if you want everything to stay home.',
      },
      {
        q: 'Which model providers work?',
        a: 'Over 100, through LiteLLM: OpenAI, Anthropic, Azure, Bedrock, or a local model over Ollama. Configure one and the survey runs against it.',
      },
      {
        q: 'How long does a survey take?',
        a: 'Graph discovery runs about a minute per ten documents; a debate is a few minutes. Both show live progress — nothing is a black box.',
      },
      {
        q: 'Can I see what happens inside?',
        a: 'That is the point of the tool: the roster shows your question becoming stations, the floor shows pairings and turns live, and the artifacts expose the selection scores, pairs, commits, warnings, and the raw event log.',
      },
      {
        q: 'What happens to finished surveys?',
        a: 'They are kept: reopen one and it renders exactly as it ended, sweep by sweep, with its fix, warnings, and final stances — or export the whole run as JSON.',
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
  primary: { label: 'Begin a survey', to: '/auth/signup?next=/dashboard' },
  edition: 'Sheet 1/1',
} as const
