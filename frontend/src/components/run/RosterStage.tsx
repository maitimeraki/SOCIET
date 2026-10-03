import type { ReactNode } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { CheckCircle } from '@phosphor-icons/react'
import type { AgentProfile, QueryIntent, SelectionRow } from '../../run/events'
import type { RosterProgress } from '../../run/selectors'
import IntentCard from './IntentCard'
import SelectionTable from './SelectionTable'
import ProfileCard from './ProfileCard'
import Button from '../ui/Button'

function Beat({
  number,
  title,
  meta,
  state,
  children,
}: {
  number: string
  title: string
  meta: string
  state: 'running' | 'done' | 'pending'
  children: ReactNode
}) {
  const glyph =
    state === 'done' ? (
      <CheckCircle size={16} className="text-good" aria-hidden="true" />
    ) : state === 'running' ? (
      <span aria-hidden="true" className="h-2.5 w-2.5 animate-pulse rounded-full bg-accent" />
    ) : (
      <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full border border-paper-faint" />
    )
  return (
    <section>
      <header className="mb-3 flex items-center gap-2.5">
        <span className="font-serif text-title text-paper">{number}</span>
        <h2 className="text-label uppercase text-paper">{title}</h2>
        {meta && <span className="tnum font-mono text-micro text-paper-mute">{meta}</span>}
        {glyph}
      </header>
      {children}
    </section>
  )
}

export default function RosterStage({
  question,
  intent,
  selection,
  profiles,
  progress,
  onSkip,
  floorSlot,
}: {
  question: string
  intent: QueryIntent | null
  selection: SelectionRow[]
  profiles: AgentProfile[]
  progress: RosterProgress
  onSkip: () => void
  floorSlot?: ReactNode
}) {
  const reduced = useReducedMotion()
  const cardMotion = reduced
    ? {}
    : { initial: { opacity: 0, y: 12 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.25, ease: [0.2, 0, 0, 1] as const } }

  return (
    <div className="space-y-8">
      <p className="text-label uppercase text-brass">Building the society</p>

      <Beat number="①" title="Reading the question" meta="S3 · intent" state={intent ? 'done' : 'running'}>
        {intent ? (
          <IntentCard intent={intent} question={question} />
        ) : (
          <p className="animate-pulse text-body text-paper-mute">Reading the question…</p>
        )}
      </Beat>

      <Beat
        number="②"
        title="Choosing who speaks"
        meta={selection.length > 0 ? `S4 · selection — ${selection.length} candidates` : 'S4 · selection'}
        state={selection.length > 0 ? 'done' : intent ? 'running' : 'pending'}
      >
        {selection.length > 0 ? (
          <SelectionTable rows={selection} />
        ) : (
          <p className={`text-body ${intent ? 'animate-pulse text-paper-mute' : 'text-paper-faint'}`}>
            Choosing who speaks…
          </p>
        )}
      </Beat>

      <Beat
        number="③"
        title="Building profiles"
        meta={progress.total !== null ? `S5 · synthesis — ${progress.built} of ${progress.total}` : 'S5 · synthesis'}
        state={progress.phase === 'seated' ? 'done' : selection.length > 0 ? 'running' : 'pending'}
      >
        {progress.phase === 'empty' ? (
          <div className="rounded-[6px] border border-ink-600 bg-ink-900 p-5">
            <p className="max-w-[60ch] text-body text-paper-dim">
              Nothing to convene. "{question}" didn't connect to enough of the corpus. Try a broader question, or add
              documents to this corpus.
            </p>
            <div className="mt-4 flex gap-3">
              <Button size={32} onClick={() => window.history.back()}>
                Ask a broader question
              </Button>
            </div>
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {profiles.map((profile) => (
              <motion.div key={profile.agent_id} {...cardMotion}>
                <ProfileCard profile={profile} />
              </motion.div>
            ))}
          </div>
        )}
      </Beat>

      <Beat
        number="④"
        title="The floor is seated"
        meta={progress.phase === 'seated' ? `${profiles.length} seated` : ''}
        state={progress.phase === 'seated' ? 'done' : 'pending'}
      >
        {floorSlot}
        {progress.phase === 'seated' ? (
          <div className="mt-3 flex items-center gap-3">
            <p className="text-body text-paper">The floor is seated — round 1 begins.</p>
            <Button variant="primary" size={32} onClick={onSkip}>
              Watch the floor →
            </Button>
          </div>
        ) : (
          <p className="text-body text-paper-faint">Seats rise as profiles build.</p>
        )}
      </Beat>
    </div>
  )
}
