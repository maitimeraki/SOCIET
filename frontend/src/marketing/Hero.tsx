import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import Legend from '../components/common/Legend'
import StanceSymbol from '../components/common/StanceSymbol'
import { buttonClasses } from '../components/ui/Button'
import { hero, heroSightlines, heroStations, meta, sheet } from './copy'

/**
 * The sheet — the first viewport (DSPEC §7.1). The hero IS the product's own instrument: the
 * question sits as the sheet's title, and the territory plots itself below it, scripted and
 * labelled synthetic. The primary action sits at the foot of the sheet, where the surveyor signs.
 *
 * The plot is a deterministic scripted SVG — no measurement, no live run. Its motion is the
 * plotting hand's own two moves (`draw`, `fix`, both from `index.css`) and nothing else; under
 * `prefers-reduced-motion` `marketing.css` renders it complete and static.
 *
 * Colour never carries meaning alone: the stations are symbol + hue, and the words live in the
 * legend at the foot — the sheet's own map convention, and the legend law's requirement.
 */

const VIEW = { w: 960, h: 520 }
const GRID_STEP = 60
const STATION_SIZE = 20

/** The fix, and the closure ring that tightens around it. */
const FIX = { x: 330, y: 190 }
const CLOSURE_RING = 52

/** The hatched relief — the dissent, honestly uncertain. */
const RELIEF = '640,360 900,250 940,470 690,500'

const gridLines = (span: number) =>
  Array.from({ length: Math.floor(span / GRID_STEP) }, (_, index) => (index + 1) * GRID_STEP)

const GRID_X = gridLines(VIEW.w)
const GRID_Y = gridLines(VIEW.h)

const legendEntries = (['POSITIVE', 'NEUTRAL', 'AMBIVALENT', 'NEGATIVE'] as const).map((stance) => ({
  symbol: <StanceSymbol stance={stance} />,
  label: stance.toLowerCase(),
}))

export default function Hero() {
  return (
    <article className="sheet">
      {/* The sheet's title block — the document's own frame, not a marketing header. */}
      <header className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 border-y border-ink-4 py-2">
        <p className="font-titling text-label uppercase tracking-[0.14em] text-ink">
          {meta.wordmark}
          <span className="text-ink-3"> · {meta.descriptor}</span>
        </p>
        <nav aria-label={sheet.navLabel} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-micro text-ink-3">
          {sheet.nav.map((item) => (
            <a key={item.href} href={item.href} className="transition-colors hover:text-ink">
              {item.label}
            </a>
          ))}
        </nav>
      </header>

      <h1 className="mt-8 max-w-[22ch] font-titling text-marketing-hero uppercase text-ink">{hero.question}</h1>
      <p className="mt-5 max-w-[68ch] text-body-lg text-ink-2">{hero.deck}</p>

      <figure className="hero-plot mt-8">
        <svg viewBox={`0 0 ${VIEW.w} ${VIEW.h}`} role="img" aria-labelledby="territory-title">
          <title id="territory-title">{hero.plotTitle(hero.closure)}</title>

          <defs>
            <pattern
              id="marketing-hachure"
              width="6"
              height="6"
              patternUnits="userSpaceOnUse"
              patternTransform="rotate(45)"
            >
              <line x1="0" y1="0" x2="0" y2="6" stroke="var(--color-ink-4)" strokeWidth="1" />
            </pattern>
          </defs>

          {/* the graticule — the sheet's own measuring grid */}
          <g aria-hidden="true" stroke="var(--color-datum-dim)" strokeWidth="1" opacity="0.35">
            {GRID_X.map((x) => (
              <line key={`x${x}`} x1={x} y1="0" x2={x} y2={VIEW.h} />
            ))}
            {GRID_Y.map((y) => (
              <line key={`y${y}`} x1="0" y1={y} x2={VIEW.w} y2={y} />
            ))}
          </g>

          {/* relief uncertain — the dissent, hatched rather than smoothed away */}
          <polygon points={RELIEF} fill="url(#marketing-hachure)" stroke="var(--color-ink-4)" strokeWidth="1" aria-hidden="true" />

          {/* lines of sight — the draw: each strokes on between a computed pair */}
          <g fill="none" stroke="var(--color-datum-dim)" strokeWidth="1.25">
            {heroSightlines.map(([from, to], index) => {
              const a = heroStations[from]
              const b = heroStations[to]
              return (
                <path
                  key={`${a.id}-${b.id}`}
                  d={`M${a.x} ${a.y} L${b.x} ${b.y}`}
                  pathLength={1}
                  data-plot="draw"
                  className="draw"
                  style={{ '--draw-length': 1, animationDelay: `${index * 110}ms` } as CSSProperties}
                />
              )
            })}
          </g>

          {/* the fix — the closure ring tightens, then the plotted point blooms once and settles */}
          <g transform={`translate(${FIX.x} ${FIX.y})`} aria-hidden="true">
            <circle r={CLOSURE_RING} fill="none" stroke="var(--color-datum-dim)" strokeWidth="1" strokeDasharray="5 5" />
            <circle r="16" fill="none" stroke="var(--color-ink)" strokeWidth="1.5" />
            <circle r="5.5" fill="var(--color-brass)" />
            <circle
              r="3.6"
              fill="var(--color-route)"
              data-plot="fix"
              className="fix"
              style={{ animationDelay: '1150ms' } as CSSProperties}
            />
          </g>
          <text
            x={FIX.x + CLOSURE_RING + 10}
            y={FIX.y + 4}
            className="font-measurement text-mono text-ink-3"
            fill="currentColor"
          >
            closure {hero.closure}
          </text>

          {/* the stations — symbol + hue; the word is the legend's, at the foot */}
          {heroStations.map((station) => (
            <g
              key={station.id}
              data-station="true"
              transform={`translate(${station.x - STATION_SIZE / 2} ${station.y - STATION_SIZE / 2})`}
            >
              <title>{hero.stationTitle(station.stance, station.entity)}</title>
              <StanceSymbol stance={station.stance} size={STATION_SIZE} />
            </g>
          ))}

          {/* the neatline — the map's own frame, not a card */}
          <rect
            x="0.5"
            y="0.5"
            width={VIEW.w - 1}
            height={VIEW.h - 1}
            fill="none"
            stroke="var(--color-ink-4)"
            strokeWidth="1"
            aria-hidden="true"
          />
        </svg>
        <figcaption className="mt-2 font-measurement text-mono text-ink-3">{hero.syntheticLabel}</figcaption>
      </figure>

      <Legend entries={legendEntries} title={hero.legendTitle} className="mt-4" />

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <Link to={hero.primary.to} className={buttonClasses('primary', 40)}>
          {hero.primary.label}
        </Link>
        <a href={hero.secondary.href} className={buttonClasses('secondary', 40)}>
          {hero.secondary.label}
        </a>
      </div>
    </article>
  )
}
