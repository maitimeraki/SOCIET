// The one locale each format is authored in (i18n prep, FE §6): a future runtime i18n threads a
// locale here rather than touching every call site. No i18n runtime is added — the formats stay
// fixed English; only the seam exists.
const INT = new Intl.NumberFormat('en-US')
const MONTH = new Intl.DateTimeFormat('en-GB', { month: 'short' })
const pad = (n: number): string => String(n).padStart(2, '0')

export const fmtInt = (n: number): string => INT.format(Math.round(n))

export const fmtPct = (n: number, digits = 0): string => `${(n * 100).toFixed(digits)}%`

export const fmtScore = (n: number, digits = 2): string => n.toFixed(digits)

export const fmtDate = (iso: string): string => {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return `${d.getDate()} ${MONTH.format(d)} ${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export const fmtElapsed = (totalSeconds: number): string => {
  const s = Math.max(0, Math.floor(totalSeconds))
  const m = Math.floor(s / 60)
  return `${String(m).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

export const truncateId = (id: string, head = 4, tail = 2): string =>
  id.length > head + tail + 1 ? `${id.slice(0, head)}…${id.slice(-tail)}` : id
