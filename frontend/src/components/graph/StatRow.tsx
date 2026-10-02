import StatTile from '../ui/StatTile'

export default function StatRow({ items }: { items: { label: string; value: string }[] }) {
  return (
    <div className="flex flex-wrap gap-10">
      {items.map((item) => (
        <StatTile key={item.label} label={item.label} value={item.value} />
      ))}
    </div>
  )
}
