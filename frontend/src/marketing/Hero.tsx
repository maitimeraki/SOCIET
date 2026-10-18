import { Link } from 'react-router-dom'
import { hero, meta } from './copy'

/**
 * The first viewport — the whole Persuade surface in one screen. A stranger reads, in order:
 * the wordmark; the account bar (Sign in / Start free); the headline "A decision you can't look
 * up."; one supporting line; one action, "Start your first decision"; then the proof region.
 *
 * The proof region is RESERVED, not drawn. Task 6.3 fills it with a real capture — a dark map
 * beside a white verdict card — taken from the running product. Nothing here imitates that
 * capture: no synthetic plot, no mock, no placeholder that reads as a claim. The two surfaces
 * are the world's own materials (the one dark map, the white card) holding the space.
 *
 * There is exactly one primary action: the secondary that used to sit beside it is gone from the
 * first viewport, and the action carries `next` so a new owner lands where the work begins.
 */
export default function Hero() {
  return (
    <section aria-labelledby="hero-headline" className="sheet">
      <header className="flex items-center justify-between gap-6">
        <p className="font-titling text-[18px] font-semibold tracking-[-0.01em] text-ink">{meta.wordmark}</p>
        <nav aria-label={hero.navLabel} className="flex items-center gap-2">
          <Link
            to={hero.signIn.to}
            className="inline-flex h-10 items-center rounded-md px-4 text-body text-ink-2 transition-colors duration-150 hover:bg-ground-2 hover:text-ink"
          >
            {hero.signIn.label}
          </Link>
          <Link
            to={hero.startFree.to}
            className="inline-flex h-10 items-center rounded-md border border-border bg-canvas px-4 text-body font-medium text-ink shadow-raised transition-colors duration-150 hover:border-border-strong hover:bg-ground-2"
          >
            {hero.startFree.label}
          </Link>
        </nav>
      </header>

      <div className="mt-16 grid items-center gap-12 lg:mt-24 lg:grid-cols-[1.05fr_0.95fr] lg:gap-16">
        <div>
          <h1 id="hero-headline" className="max-w-[16ch] font-titling text-hero text-ink">
            {hero.headline}
          </h1>
          <p className="mt-6 max-w-[52ch] text-body-lg text-ink-2">{hero.support}</p>
          <div className="mt-8">
            <Link to={hero.primary.to} data-action="primary" className="action">
              {hero.primary.label}
            </Link>
          </div>
        </div>

        {/* The proof region — reserved for Task 6.3's real capture. Decorative until then. */}
        <figure className="hero-capture" data-capture="region" aria-hidden="true">
          <div className="hero-capture__map" data-capture="map" />
          <div className="hero-capture__verdict" data-capture="verdict" />
        </figure>
      </div>
    </section>
  )
}
