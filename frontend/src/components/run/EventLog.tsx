import type { RunEvent } from '../../run/events'

export default function EventLog({ events }: { events: RunEvent[] }) {
  return (
    <div className="max-h-[420px] overflow-auto rounded-[6px] border border-ink-700 bg-ink-900 p-3">
      {events.length === 0 && <p className="text-body text-paper-mute">No events yet.</p>}
      {events.map((event, index) => (
        <div key={index} className="tnum whitespace-pre-wrap break-all font-mono text-mono leading-[18px] text-paper-dim">
          {String(index).padStart(4, '0')} {event.type} {JSON.stringify(event)}
        </div>
      ))}
    </div>
  )
}
