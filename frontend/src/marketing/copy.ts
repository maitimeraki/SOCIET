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
    transcriptLabel: 'Transcript',
    transcript: 'The transcript lands with the recording.',
  },
  howItWorks: {
    heading: 'How it works',
    note: 'The mechanism in four ruled steps — record → stations → lines of sight → the fix. Each step keys to the legend.',
  },
  comparison: {
    heading: 'How it differs',
    note: 'Societas against a single chatbot and prompt-chained agents — on structure, provenance, dissent, and verdict confidence.',
  },
  trust: {
    heading: 'Your record stays yours',
    note: 'Documents stay in your graph. Your data is never used for training. Run history is yours.',
    /** May appear only in this form, marked unverified — never implied complete. */
    soc2: 'SOC 2 in progress — not yet certified.',
    soc2Marker: 'unverified',
  },
  record: {
    heading: 'The record',
    note: 'A finished survey shown as a sheet — the fix, the closure, the dissent hatched, and the contents map back to the record.',
  },
  faq: {
    heading: 'Questions owners ask',
    note: 'The questions owners actually ask, answered from how the product behaves — no more, no less.',
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
