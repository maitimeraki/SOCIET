// Build-time environment, validated once and runtime-safe: nothing here throws, so a
// misconfigured build still mounts and can show a recoverable error instead of white-screening.
//
// `''` is a VALID configured value, not "unset": dev serves the API through the Vite proxy, so the
// app is same-origin and the base URL is the empty prefix. Only `undefined` (unset) collapses to
// null — hence the `=== null` check below rather than a truthiness test.
export const apiBase: string | null =
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') ?? null

export const apiBaseError = apiBase === null ? 'VITE_API_BASE is not configured.' : null
