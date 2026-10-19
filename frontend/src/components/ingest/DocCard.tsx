import { FileDoc, FileMd, FilePdf, FileTxt, X } from '@phosphor-icons/react'
import type { DraftDoc } from '../../wizard/draftStore'
import { fmtInt } from '../../utils/format'
import IconButton from '../ui/IconButton'

function DocIcon({ title }: { title: string }) {
  const lower = title.toLowerCase()
  if (lower.endsWith('.pdf')) return <FilePdf size={18} className="text-ink-2" aria-hidden="true" />
  if (lower.endsWith('.docx')) return <FileDoc size={18} className="text-ink-2" aria-hidden="true" />
  if (lower.endsWith('.md') || lower.endsWith('.markdown')) return <FileMd size={18} className="text-ink-2" aria-hidden="true" />
  if (lower.endsWith('.txt')) return <FileTxt size={18} className="text-ink-2" aria-hidden="true" />
  return <FileDoc size={18} className="text-ink-2" aria-hidden="true" />
}

export default function DocCard({
  doc,
  onRemove,
  onRetry,
}: {
  doc: DraftDoc
  onRemove: () => void
  onRetry: () => void
}) {
  return (
    <div className="flex items-center gap-3 border-t border-ink-4 pt-3">
      <DocIcon title={doc.title} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-body text-ink">{doc.title}</div>
        {doc.status === 'extracting' && <div className="mt-0.5 text-micro text-accent">Extracting…</div>}
        {doc.status === 'ready' && (
          <div className="tnum mt-0.5 font-measurement text-micro text-ink-3">Ready — {fmtInt(doc.word_count)} words</div>
        )}
        {doc.status === 'failed' && (
          <div className="mt-0.5 text-micro text-ink-2">
            Failed — {doc.error ?? 'unknown error'}{' '}
            <button type="button" onClick={onRetry} className="underline hover:text-ink">
              try again
            </button>
          </div>
        )}
      </div>
      <IconButton label={`Remove ${doc.title}`} onClick={onRemove}>
        <X size={14} aria-hidden="true" />
      </IconButton>
    </div>
  )
}
