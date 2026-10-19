import { Link } from 'react-router-dom'
import './marketing.css'
import ComparisonTable from './ComparisonTable'
import { footer, meta } from './copy'
import Faq from './Faq'
import Hero from './Hero'
import HowItWorks from './HowItWorks'
import ProofSection from './ProofSection'
import RecordSheet from './RecordSheet'
import TrustSection from './TrustSection'

/**
 * `/` — the homepage (DSPEC §7.1, Persuade). The first viewport makes the claim and reserves the
 * capture region; the sections below it prove the mechanism, because no recording, customer proof
 * or benchmark exists to borrow; the footer closes on the wordmark and the two real actions.
 */
export default function LandingPage() {
  return (
    <div className="pb-10">
      <Hero />

      <div className="sheet-gutters space-y-16 pt-16">
        <div id="in-the-open">
          <ProofSection />
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
          <Link
            to={footer.primary.to}
            className="inline-flex h-10 items-center rounded-md px-4 font-titling text-body text-ink-2 transition-colors duration-150 hover:bg-ground-2 hover:text-ink"
          >
            {footer.primary.label}
          </Link>
          <a
            href={footer.contact.href}
            className="inline-flex h-10 items-center rounded-md px-4 font-titling text-body text-ink-2 transition-colors duration-150 hover:bg-ground-2 hover:text-ink"
          >
            {footer.contact.label}
          </a>
        </div>
      </footer>
    </div>
  )
}
