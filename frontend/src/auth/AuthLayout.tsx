import { Link, Outlet } from 'react-router-dom'
import Legend, { type LegendEntry } from '../components/common/Legend'
import { PositionGlyph } from '../components/ui/PositionMark'

/* ── the auth surface's frame ─────────────────────────────────────────────────────────────────────
   A layout is structure: the sheet, the ruled half-sheet and its sample, `<main>` and the wordmark.
   The form's own rules — the `safeNext` security boundary, the validators, the error copy and the
   §7.2 state marks — live in `authForm.tsx`, not here (R38). */

/** The legend law (§3/§9): the three stations in the sample are keyed, symbol + word, so the hue is
 *  never the only carrier. Reuses the surface's own glyphs rather than redrawing them. */
const SAMPLE_LEGEND: LegendEntry[] = [
  { key: 'POS', symbol: <PositionGlyph position="POSITIVE" ground="light" />, label: 'positive' },
  { key: 'NEU', symbol: <PositionGlyph position="NEUTRAL" ground="light" />, label: 'neutral' },
  { key: 'NEG', symbol: <PositionGlyph position="NEGATIVE" ground="light" />, label: 'negative' },
]

/**
 * §7.2's "small honest sample of the sheet": three stations, their lines of sight, and the fix, drawn
 * in the sheet's own geometry (a graticule, station marks matching `PositionGlyph`'s stroke weights, a
 * warn-ringed fix). It is captioned as a sample, never a run — no fabricated result. The `fix` ring
 * is drawn here, not imported from `FixMark`, whose one-mark-owns-the-word law reserves it for verdict
 * surfaces; this is a labelled illustration, and it is `aria-hidden` behind its caption.
 */
function SampleSheet() {
  return (
    <figure className="mt-10">
      <svg viewBox="0 0 260 150" className="w-full" aria-hidden="true" focusable="false">
        {/* graticule — the sheet's own rule hairlines */}
        <g stroke="var(--color-border)" strokeWidth="0.5" opacity="0.45">
          <line x1="0" y1="38" x2="260" y2="38" />
          <line x1="0" y1="76" x2="260" y2="76" />
          <line x1="0" y1="114" x2="260" y2="114" />
          <line x1="65" y1="0" x2="65" y2="150" />
          <line x1="130" y1="0" x2="130" y2="150" />
          <line x1="195" y1="0" x2="195" y2="150" />
        </g>
        {/* lines of sight between the stations */}
        <g stroke="var(--color-ink-4)" strokeWidth="0.9">
          <line x1="64" y1="44" x2="176" y2="96" />
          <line x1="176" y1="96" x2="104" y2="122" />
          <line x1="104" y1="122" x2="64" y2="44" />
        </g>
        {/* three stations — the same drawn forms as the legend key */}
        <polygon points="64,35 74,52 54,52" fill="var(--color-pos-light)" />
        <g fill="none" stroke="var(--color-neu-light)" strokeWidth="1.5">
          <rect x="169" y="89" width="14" height="14" />
          <path d="M169 96h14M176 89v14" />
        </g>
        <path
          d="M97 115 111 129M111 115 97 129"
          fill="none"
          stroke="var(--color-neg-light)"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
        {/* the fix — an ink ring, a warn centre, the plotted point */}
        <circle cx="124" cy="70" r="12" fill="none" stroke="var(--color-ink)" strokeWidth="1.5" />
        <circle cx="124" cy="70" r="3.8" fill="var(--color-warn)" />
        <circle cx="133" cy="61" r="2.4" fill="var(--color-ink-2)" />
      </svg>
      <figcaption className="mt-3 font-measurement text-mono text-ink-3">
        A sample sheet, not a run — three stations, their lines of sight, and the fix.
      </figcaption>
      <Legend className="mt-3" entries={SAMPLE_LEGEND} title="Stations" />
    </figure>
  )
}

/**
 * §7.2 Authentication — the survey office's front door. A single intake form on the sheet (left) and a
 * quiet ruled half-sheet (right) stating the thesis once and showing a sample of the sheet, so the
 * page belongs to the world. `<main>` landmark, the wordmark in Archivo caps, and **no shell chrome**:
 * a visitor who has not signed in gets no app navigation.
 *
 * It is a layout route: the form itself is the `<Outlet/>` (SignInPage / SignUpPage), so the frame is
 * built once and the two pages differ only in their fields.
 */
export default function AuthLayout() {
  return (
    <main className="min-h-screen bg-ground">
      <div className="mx-auto grid min-h-screen w-full max-w-6xl grid-cols-1 lg:grid-cols-2">
        <div className="flex flex-col px-6 py-10 sm:px-10 lg:px-14">
          <Link to="/" className="inline-flex items-baseline gap-2.5 self-start">
            <span className="font-titling text-[18px] uppercase leading-none tracking-[0.08em] text-ink">Societas</span>
            <span className="hidden font-measurement text-mono uppercase tracking-[0.06em] text-ink-3 sm:inline">
              Survey &amp; deliberation
            </span>
          </Link>
          <div className="mt-14 w-full max-w-sm">
            <Outlet />
          </div>
        </div>

        {/* Stacks below the form under `lg` rather than disappearing: the sheet is how the page
            belongs to the world (§7.2), and §9 keeps the hierarchy while it drops columns. */}
        <aside className="border-t border-ink-4 px-6 py-12 sm:px-10 lg:flex lg:flex-col lg:justify-center lg:border-l lg:border-t-0 lg:px-14 lg:py-16">
          <p className="max-w-[26ch] font-titling text-title text-ink">
            A panel of specialists measures a decision into a publishable sheet.
          </p>
          <SampleSheet />
        </aside>
      </div>
    </main>
  )
}
