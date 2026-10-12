import { useEffect, useState } from 'react'
import { animate, useReducedMotion } from 'framer-motion'
import type { DissentingView, EvidenceItem, Stance } from '../../run/events'
import { splitSections } from './narrative'
import Button from '../ui/Button'

const UNDERLINE: Record<Stance, string> = {
  POSITIVE: 'border-stance-pos',
  NEUTRAL: 'border-stance-neu',
  AMBIVALENT: 'border-stance-amb',
  NEGATIVE: 'border-stance-neg',
}

export default function VerdictHero({
  stance,
  confidence,
  converged,
  summary,
  narrative,
  dissentingViews,
  evidence,
  onReplay,
  onExport,
  onNew,
}: {
  stance: Stance
  confidence: number | null
  converged: boolean
  summary: string
  narrative: string
  dissentingViews: DissentingView[]
  evidence: EvidenceItem[]
  onReplay: () => void
  onExport: () => void
  onNew: () => void
}) {
  const reduced = useReducedMotion()
  const target = confidence ?? 0
  const [animated, setAnimated] = useState(0)
  const display = reduced || confidence === null ? target : animated
  const sections = narrative.trim() ? splitSections(narrative) : []

  useEffect(() => {
    if (reduced || confidence === null) return
    const controls = animate(0, target, {
      duration: 0.6,
      ease: [0.2, 0, 0, 1],
      onUpdate: setAnimated,
    })
    return () => controls.stop()
  }, [target, reduced, confidence])

  return (
    <section>
      <p className="text-label uppercase text-brass">{converged ? 'The verdict' : 'No convergence'}</p>
      <h1 className={`mt-3 inline-block border-b-[3px] pb-1 font-serif text-display text-paper ${UNDERLINE[stance]}`}>
        {stance}
      </h1>
      <div className="mt-5 flex items-baseline gap-3">
        <span className="tnum font-serif text-numeral text-paper">{display.toFixed(2)}</span>
        <span className="text-label uppercase text-paper-mute">weighted confidence</span>
      </div>
      {sections.length > 0 ? (
        <div className="mt-5 max-w-[60ch] space-y-4">
          {sections.map((section, i) => (
            <div key={i}>
              {section.heading && (
                <h2 className="font-serif text-heading text-paper">{section.heading}</h2>
              )}
              {section.body && (
                <p className="mt-1 whitespace-pre-line font-serif text-body text-paper-dim">
                  {section.body}
                </p>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-5 max-w-[60ch] font-serif text-title text-paper">{summary}</p>
      )}
      {dissentingViews.length > 0 && (
        <div className="mt-6 max-w-[60ch]">
          <h2 className="text-label uppercase text-brass">Dissenting views</h2>
          <ul className="mt-2 space-y-1">
            {dissentingViews.map((view, i) => (
              <li key={i} className="text-body text-paper-dim">
                <span className="text-paper">{view.stance}</span> — {view.view}
              </li>
            ))}
          </ul>
        </div>
      )}
      {evidence.length > 0 && (
        <div className="mt-6 max-w-[60ch]">
          <h2 className="text-label uppercase text-brass">Evidence</h2>
          <ul className="mt-2 space-y-1">
            {evidence.map((item, i) => (
              <li key={i} className="text-body text-paper-dim">
                <span className="text-paper">{item.entity}</span> — {item.claim}
              </li>
            ))}
          </ul>
        </div>
      )}
      {!converged && (
        <p className="mt-3 text-body text-paper-dim">
          The chamber did not converge — this verdict is a plurality, not a consensus.
        </p>
      )}
      <div className="mt-6 flex items-center gap-3">
        <Button onClick={onReplay}>Replay this run</Button>
        <Button onClick={onExport}>Export JSON</Button>
        <Button variant="ghost" onClick={onNew}>
          Start a new run
        </Button>
      </div>
    </section>
  )
}
