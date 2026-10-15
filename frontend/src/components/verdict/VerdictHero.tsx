import { useEffect, useState } from 'react'
import { animate, useReducedMotion } from 'framer-motion'
import type { DissentingView, EvidenceItem, Stance } from '../../run/events'
import { splitSections } from './narrative'
import NarrativeFallbackNotice from './NarrativeFallbackNotice'
import Button from '../ui/Button'

export default function VerdictHero({
  stance,
  confidence,
  converged,
  summary,
  narrative,
  narrativeStatus,
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
  narrativeStatus: string
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
      <p className="text-label uppercase text-ink-3">{converged ? 'The verdict' : 'No convergence'}</p>
      {/* The rule under the verdict word is ink, not a stance hue: DSPEC §6/§7.3 mandate no
          stance-coloured rule here, so §3's legend law governs — the stance meaning is the word
          itself (and the StanceChip symbol elsewhere), never a decorative hue. */}
      <h1 className="mt-3 inline-block border-b-[3px] border-ink pb-1 font-titling text-display text-ink">
        {stance}
      </h1>
      <div className="mt-5 flex items-baseline gap-3">
        <span className="tnum font-titling text-numeral text-ink">{display.toFixed(2)}</span>
        <span className="text-label uppercase text-ink-3">weighted confidence</span>
      </div>
      {/* §17.3 — the narrative degraded to `summary`: say so, so the one-line summary never
          masquerades as the written verdict. */}
      <NarrativeFallbackNotice status={narrativeStatus} />
      {sections.length > 0 ? (
        <div className="mt-5 max-w-[60ch] space-y-4">
          {sections.map((section, i) => (
            <div key={i}>
              {section.heading && (
                <h2 className="font-titling text-heading text-ink">{section.heading}</h2>
              )}
              {section.body && (
                <p className="mt-1 whitespace-pre-line font-titling text-body text-ink-2">
                  {section.body}
                </p>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-5 max-w-[60ch] font-titling text-title text-ink">{summary}</p>
      )}
      {dissentingViews.length > 0 && (
        <div className="mt-6 max-w-[60ch]">
          <h2 className="text-label uppercase text-ink-3">Dissenting views</h2>
          <ul className="mt-2 space-y-1">
            {dissentingViews.map((view, i) => (
              <li key={i} className="text-body text-ink-2">
                <span className="text-ink">{view.stance}</span> — {view.view}
              </li>
            ))}
          </ul>
        </div>
      )}
      {evidence.length > 0 && (
        <div className="mt-6 max-w-[60ch]">
          <h2 className="text-label uppercase text-ink-3">Evidence</h2>
          <ul className="mt-2 space-y-1">
            {evidence.map((item, i) => (
              <li key={i} className="text-body text-ink-2">
                <span className="text-ink">{item.entity}</span> — {item.claim}
              </li>
            ))}
          </ul>
        </div>
      )}
      {!converged && (
        <p className="mt-3 text-body text-ink-2">
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
