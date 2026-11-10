export interface MapEntry {
  key: string
  label: string
  name: string
}

/**
 * §8.7 — the map's text alternative, made visible. The map is a view of stored truth, so the
 * truth has to be readable without the picture: this list says what the map holds.
 *
 * It is also the scroll half of the split — the pane's plot stays put while this list moves
 * with the output.
 */
export default function MapEntries({ entries, connections }: { entries: MapEntry[]; connections: number }) {
  return (
    <div className="flex min-h-0 flex-col border-t border-map-rule pt-3">
      <p className="font-ui text-[10px] uppercase tracking-[0.1em] text-map-ink-2">
        The map &middot; <span className="font-mono tnum">{entries.length}</span>
      </p>
      {entries.length === 0 ? (
        <p className="mt-2 font-mono text-[10.5px] leading-[15px] text-map-ink-2">
          Nothing yet. The map fills as each document is read.
        </p>
      ) : (
        <ul className="mt-2">
          {entries.map((entry) => (
            <li key={entry.key} className="flex items-baseline justify-between gap-3 py-1 font-mono text-[10.5px] leading-[15px] text-map-ink-2">
              <span className="flex items-baseline gap-2">
                <i className="h-1.5 w-1.5 shrink-0 rounded-full bg-map-accent" />
                <span className="text-map-ink">{entry.name}</span>
              </span>
              <span className="shrink-0 opacity-70">{entry.label}</span>
            </li>
          ))}
          <li className="flex items-baseline justify-between gap-3 border-t border-map-rule pt-2 font-mono text-[10.5px] leading-[15px] text-map-ink-2">
            <span className="text-map-ink">Connections</span>
            <span className="shrink-0 opacity-70">{connections}</span>
          </li>
        </ul>
      )}
    </div>
  )
}
