export interface TabItem { key: string; label: string }

export default function Tabs({ items, active, onSelect }: { items: TabItem[]; active: string; onSelect: (key: string) => void }) {
  return (
    <div role="tablist" className="flex items-center gap-1 border-b border-ink-4">
      {items.map((item) => (
        <button
          key={item.key}
          role="tab"
          aria-selected={item.key === active}
          onClick={() => onSelect(item.key)}
          className={`px-3 py-2 text-body transition-colors ${
            item.key === active ? 'text-ink shadow-[inset_0_-2px_0_0_var(--color-datum)]' : 'text-ink-2 hover:text-ink'
          }`}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}
