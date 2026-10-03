import { useEffect, useRef, useState } from 'react'
import { Warning } from '@phosphor-icons/react'
import type { StreamItem } from '../../run/selectors'
import TurnCard from './TurnCard'
import CommitLine from './CommitLine'
import ActivationNote from './ActivationNote'

const MAX_ROWS = 2000

function Announcements({ items }: { items: StreamItem[] }) {
  const lastHeader = [...items].reverse().find((item) => item.kind === 'round-header')
  const lastWarning = [...items].reverse().find((item) => item.kind === 'warning')
  return (
    <div aria-live="polite" className="sr-only">
      {lastHeader ? `Round ${lastHeader.round} begins. ` : ''}
      {lastWarning ? lastWarning.text : ''}
    </div>
  )
}

export default function EventStream({ items, live }: { items: StreamItem[]; live: boolean }) {
  const container = useRef<HTMLDivElement>(null)
  const [paused, setPaused] = useState(false)
  const visible = items.length > MAX_ROWS ? items.slice(-MAX_ROWS) : items

  useEffect(() => {
    if (paused || !container.current) return
    container.current.scrollTop = container.current.scrollHeight
  }, [visible.length, paused])

  const onScroll = () => {
    const node = container.current
    if (!node) return
    setPaused(node.scrollHeight - node.scrollTop - node.clientHeight >= 48)
  }

  return (
    <div className="relative">
      <Announcements items={items} />
      <div ref={container} onScroll={onScroll} className="max-h-[70vh] space-y-3 overflow-y-auto pr-1">
        {visible.map((item, index) => {
          switch (item.kind) {
            case 'round-header':
              return (
                <h3 key={index} className="pt-2 text-heading text-paper">
                  Round {item.round}{' '}
                  <span className="tnum font-mono text-micro text-paper-mute">{item.pairs} pairs</span>
                </h3>
              )
            case 'turn':
              return <TurnCard key={index} turn={item.turn} round={item.round} />
            case 'pending':
              return (
                <p key={item.pairId} className="animate-pulse text-micro text-paper-mute">
                  {item.a} is preparing a reply…
                </p>
              )
            case 'commit':
              return <CommitLine key={index} round={item.round} opinions={item.opinions} edges={item.edges} failed={item.failed} />
            case 'activation':
              return <ActivationNote key={index} round={item.round} agents={item.agents} reasons={item.reasons} />
            case 'warning':
              return (
                <p key={index} className="flex items-start gap-2 text-micro text-brass">
                  <Warning size={14} className="mt-0.5 shrink-0" aria-hidden="true" /> {item.text}
                </p>
              )
          }
        })}
        {items.length === 0 && <p className="text-body text-paper-mute">Waiting for the floor…</p>}
        {items.length > MAX_ROWS && (
          <p className="text-micro text-paper-mute">Showing the last {MAX_ROWS} rows — the full record is in Artifacts.</p>
        )}
      </div>
      {paused && live && (
        <button
          type="button"
          onClick={() => {
            setPaused(false)
            container.current?.scrollTo({ top: container.current.scrollHeight })
          }}
          className="sticky bottom-2 left-1/2 mt-2 -translate-x-1/2 rounded-[4px] border border-ink-600 bg-ink-800 px-3 py-1.5 text-micro text-paper"
        >
          Jump to live ↓
        </button>
      )}
    </div>
  )
}
