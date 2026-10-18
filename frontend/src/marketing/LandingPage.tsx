import { Link } from 'react-router-dom'
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

      {/* The close — wordmark, the real edition line, the two real actions. */}
      <footer className="sheet-gutters mt-24 flex flex-wrap items-end justify-between gap-x-8 gap-y-4 border-t border-border pt-6">
        <div>
          <p className="font-titling text-title font-semibold text-ink">{meta.wordmark}</p>
          <p className="mt-1 text-micro text-ink-3">
            {footer.edition} · v{meta.version} · {meta.descriptor.toLowerCase()}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Link to={footer.primary.to} className="action">
            {footer.primary.label}
          </Link>
          <a
            href={footer.contact.href}
            className="inline-flex h-10 items-center rounded-md px-4 text-body text-ink-2 transition-colors duration-150 hover:bg-ground-2 hover:text-ink"
          >
            {footer.contact.label}
          </a>
        </div>
      </footer>
    </div>
  )
}
