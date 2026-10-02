export const fmtInt = (n: number): string => Math.round(n).toLocaleString('en-US')

export const fmtPct = (n: number, digits = 0): string => `${(n * 100).toFixed(digits)}%`

export const fmtScore = (n: number, digits = 2): string => n.toFixed(digits)

export const fmtDate = (iso: string): string => {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const month = d.toLocaleString('en-GB', { month: 'short' })
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${d.getDate()} ${month} ${d.getFullYear()} ${hh}:${mm}`
}

export const fmtElapsed = (totalSeconds: number): string => {
  const s = Math.max(0, Math.floor(totalSeconds))
  const m = Math.floor(s / 60)
  return `${String(m).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

export const truncateId = (id: string, head = 4, tail = 2): string =>
  id.length > head + tail + 1 ? `${id.slice(0, head)}…${id.slice(-tail)}` : id
