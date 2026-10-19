import { Link } from 'react-router-dom'
import { captures, hero, meta } from './copy'

/**
 * The first viewport — the whole Persuade surface in one screen. A stranger reads, in order:
 * the wordmark; the account bar (Sign in / Start free); the headline "A decision you can't look
 * up."; one supporting line; one action, "Start your first decision"; then the proof region.
 *
 * The proof region is one capture of a filed answer, taken from the running product, held inside the
 * first viewport by a height cap (`marketing.css`). The same document's opposing case ships further
 * down, under the proof section's third stage. The map capture does not ship — the map surface does
 * not work in the shipped build — so no frame here imitates one.
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
            className="inline-flex h-10 items-center rounded-md px-4 font-titling text-body text-ink-2 transition-colors duration-150 hover:bg-ground-2 hover:text-ink"
          >
            {hero.signIn.label}
          </Link>
          <Link
            to={hero.startFree.to}
            className="inline-flex h-10 items-center rounded-md border border-border bg-canvas px-4 font-titling text-body font-medium text-ink shadow-raised transition-colors duration-150 hover:border-border-strong hover:bg-ground-2"
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

        {/* The proof region — one frame of the filed answer, taken from the running product. */}
        <figure className="hero-capture" data-capture="region">
          <img
            className="hero-capture__frame"
            data-capture="answer"
            src={captures.answer.src}
            alt={captures.answer.alt}
            width={captures.answer.width}
            height={captures.answer.height}
          />
        </figure>
      </div>
    </section>
  )
}
