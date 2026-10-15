import { Warning } from '@phosphor-icons/react'

/** §17.3 — the exact copy: the one-line summary must never masquerade as the written verdict. */
export const NARRATIVE_FALLBACK_COPY = 'The detailed verdict could not be written; showing aggregates only.'

/**
 * The narrative-degradation notice. Rendered only for `narrative_status === 'fallback'`; any other
 * value (including a missing one) is a normal verdict and renders nothing.
 *
 * R35: the mark may be brass, the words are ink — the rule and the icon carry the caution hue, the
 * sentence stays `--ink`.
 */
export default function NarrativeFallbackNotice({ status }: { status: string }) {
  if (status !== 'fallback') return null
  return (
    <div className="mt-5 flex items-start gap-2 border-l-2 border-brass pl-3">
      <Warning size={16} className="mt-0.5 shrink-0 text-brass" aria-hidden="true" />
      <p className="max-w-[60ch] text-body text-ink">{NARRATIVE_FALLBACK_COPY}</p>
    </div>
  )
}
