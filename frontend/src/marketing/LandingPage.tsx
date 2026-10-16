import { Link } from 'react-router-dom'
import { buttonClasses } from '../components/ui/Button'
import './marketing.css'
import ComparisonTable from './ComparisonTable'
import { footer, meta } from './copy'
import DemoVideo from './DemoVideo'
import Faq from './Faq'
import Hero from './Hero'
import HowItWorks from './HowItWorks'
import RecordSheet from './RecordSheet'
import TrustSection from './TrustSection'

/**
 * `/` — the survey sheet (DSPEC §7.1, Persuade). The hero is the sheet itself; the sections that
 * follow are the sheet's own ruled pages, in the spec's order; the title block closes it.
 *
 * The section bodies are honest, minimal stubs seeded here for Task 17b (R49) — the page composes
 * and reads as a real page today, and 17b fills each body without touching this file.
 */
export default function LandingPage() {
  return (
    <div className="pb-10">
      <Hero />

      <div className="sheet-gutters space-y-16 pt-16">
        <div id="field-recording">
          <DemoVideo />
        </div>
        <div id="how-it-works">
          <HowItWorks />
        </div>
        <div id="comparison">
          <ComparisonTable />
        </div>
        <div id="trust">
          <TrustSection />
        </div>
        <div id="the-record">
          <RecordSheet />
        </div>
        <div id="questions">
          <Faq />
        </div>
      </div>

      {/* The title block close — wordmark, the sheet's own coordinates, the two real actions. */}
      <footer className="sheet-gutters mt-20 flex flex-wrap items-end justify-between gap-x-8 gap-y-4 border-t-2 border-ink pt-4">
        <div>
          <p className="font-titling text-title uppercase tracking-[0.08em] text-ink">{meta.wordmark}</p>
          <p className="mt-1 font-measurement text-mono text-ink-3">
            {footer.edition} · v{meta.version} · {meta.descriptor.toLowerCase()}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Link to={footer.primary.to} className={buttonClasses('primary', 40)}>
            {footer.primary.label}
          </Link>
          <a href={footer.contact.href} className={buttonClasses('secondary', 40)}>
            {footer.contact.label}
          </a>
        </div>
      </footer>
    </div>
  )
}
