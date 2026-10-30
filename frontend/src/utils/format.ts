// The one locale each format is authored in (i18n prep, FE §6): a future runtime i18n threads a
// locale here rather than touching every call site. No i18n runtime is added — the formats stay
// fixed English; only the seam exists.
const INT = new Intl.NumberFormat('en-US')
const MONTH = new Intl.DateTimeFormat('en-GB', { month: 'short' })
const pad = (n: number): string => String(n).padStart(2, '0')

export const fmtInt = (n: number): string => INT.format(Math.round(n))

/**
 * A material figure for a customer: whole bytes, KB and MB below 1 GB, then GB (one decimal below
 * 10 GB). Units use decimal 1000 thresholds, and a rounded 1000 promotes to the next unit, so no
 * figure ever reads `1000 KB` or `1000 MB` — and no small file reads as `0 MB`.
 */
export const fmtBytes = (bytes: number): string => {
  const KB = 1_000
  const MB = 1_000_000
  const GB = 1_000_000_000
  if (bytes < KB) return `${Math.round(bytes)} B`
  if (bytes < MB) {
    const kb = Math.round(bytes / KB)
    return kb < 1000 ? `${kb} KB` : '1 MB'
  }
  if (bytes < GB) {
    const mb = Math.round(bytes / MB)
    return mb < 1000 ? `${mb} MB` : '1 GB'
  }
  const gb = bytes / GB
  return `${gb < 10 ? Number(gb.toFixed(1)) : Math.round(gb)} GB`
}

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
