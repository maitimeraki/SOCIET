import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ArrowRight, Warning } from '@phosphor-icons/react'
import { runFileIngest, runUrlIngest } from '../api/ingestFlow'
import FileDrop from '../components/ingest/FileDrop'
import DocCard from '../components/ingest/DocCard'
import UrlFetchRow from '../components/ingest/UrlFetchRow'
import Button from '../components/ui/Button'
import Input from '../components/ui/Input'
import Field from '../components/ui/Field'
import { toast } from '../components/ui/Toast'
import { useDraftStore } from '../wizard/draftStore'
import type { DraftDoc } from '../wizard/draftStore'

/** The 429's `Retry-After` is delta-seconds; say it plainly. */
function retryLine(seconds: number | null): string {
  if (seconds === null) return 'Try again later.'
  if (seconds < 90) return `Try again in about ${Math.max(1, Math.round(seconds))} s.`
  if (seconds < 5400) return `Try again in about ${Math.round(seconds / 60)} min.`
  return `Try again in about ${Math.round(seconds / 3600)} h.`
}

export default function IngestPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const note = (location.state as { note?: string } | null)?.note
  const { corpusName, docs, setCorpusName, addDocs, updateDoc, removeDoc, setDatasetId } = useDraftStore()
  const [fetchingUrl, setFetchingUrl] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const [quota, setQuota] = useState<{ message: string; retryAfterSeconds: number | null } | null>(null)

  /** POST the batch, poll the extraction job, and reconcile the extracted payloads onto the existing
   *  cards — consume-matched by title, so a duplicate-name batch updates each card exactly once. */
  const submitFiles = async (placeholders: DraftDoc[], files: File[]) => {
    setFailure(null)
    setQuota(null)
    const outcome = await runFileIngest(files)
    if (outcome.kind === 'documents') {
      const pending = [...placeholders]
      for (const doc of outcome.documents) {
        const index = pending.findIndex((placeholder) => placeholder.title === doc.title)
        if (index === -1) continue
        const [target] = pending.splice(index, 1)
        updateDoc(target.document_id, { ...doc, document_id: target.document_id, status: 'ready' })
      }
      // A placeholder the job did not return is honestly marked, not left spinning.
      for (const leftover of pending) {
        updateDoc(leftover.document_id, { status: 'failed', error: 'the extractor returned no text for this file' })
      }
      return
    }
    const reason = outcome.kind === 'quota' ? 'the upload quota is full' : outcome.reason
    for (const placeholder of placeholders) updateDoc(placeholder.document_id, { status: 'failed', error: reason })
    if (outcome.kind === 'quota') {
      setQuota({ message: outcome.message, retryAfterSeconds: outcome.retryAfterSeconds })
      return
    }
    setFailure(outcome.reason)
  }

  const handleFiles = async (files: File[]) => {
    const placeholders: DraftDoc[] = files.map((file) => ({
      document_id: crypto.randomUUID(),
      title: file.name,
      text: '',
      word_count: 0,
      source_type: 'file',
      status: 'extracting',
      file,
    }))
    addDocs(placeholders)
    await submitFiles(placeholders, files)
  }

  const handleUrl = async (url: string) => {
    setFetchingUrl(true)
    setFailure(null)
    setQuota(null)
    try {
      const outcome = await runUrlIngest(url)
      if (outcome.kind === 'documents') {
        addDocs(outcome.documents.map((doc) => ({ ...doc, status: 'ready' as const })))
        return
      }
      if (outcome.kind === 'quota') {
        setQuota({ message: outcome.message, retryAfterSeconds: outcome.retryAfterSeconds })
        return
      }
      setFailure(outcome.reason)
    } finally {
      setFetchingUrl(false)
    }
  }

  const retry = async (doc: DraftDoc) => {
    if (!doc.file) {
      toast('neutral', 'This file is no longer in memory after a refresh — add it again.')
      return
    }
    updateDoc(doc.document_id, { status: 'extracting', error: undefined })
    await submitFiles([doc], [doc.file])
  }

  const readyCount = docs.filter((doc) => doc.status === 'ready').length
  const canContinue = readyCount > 0 && corpusName.trim().length > 0

  const buildGraph = () => {
    setCorpusName(corpusName.trim())
    setDatasetId(crypto.randomUUID())
    navigate('/new/graph')
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">Your material</p>
        <h1 className="mt-3 font-display text-display font-medium tracking-[-0.03em] text-ink">Add the material</h1>
        <p className="mt-3 max-w-[60ch] font-ui text-body text-ink-2">
          Add the documents your experts would have read — PDFs, Word files, Markdown, plain text, or a web page.
        </p>
      </div>

      {note && (
        <p className="border-t border-warn/40 pt-3 text-body text-ink-2">{note}</p>
      )}

      {/* R35: the mark may be the warn hue, the words are ink — a full quota is a distinct, recoverable state. */}
      {quota && (
        <div role="status" className="flex items-start gap-2 border-t border-warn/40 pt-3">
          <Warning size={16} className="mt-0.5 shrink-0 text-warn" aria-hidden="true" />
          <p className="text-body text-ink">
            {quota.message} {retryLine(quota.retryAfterSeconds)}
          </p>
        </div>
      )}

      {/* R46 m4: the failure surfaces *after* an action, so it is an assertive error — `role="alert"`
          (the quota banner is an informational, recoverable notice, so it stays `role="status"`). It is
          the single announcement: the duplicate error toasts below were removed so the same string is
          not read twice. */}
      {failure && (
        <div role="alert" className="border-t border-danger/40 pt-3">
          <p className="text-body text-ink">Extraction failed: {failure}. Nothing was saved — try again.</p>
        </div>
      )}

      <FileDrop onFiles={handleFiles} />
      <UrlFetchRow onFetch={handleUrl} busy={fetchingUrl} />

      <section className="space-y-3">
        <h2 className="font-display text-heading font-medium tracking-[-0.01em] text-ink">Documents</h2>
        {docs.length === 0 ? (
          <p className="text-body text-ink-3">Nothing yet. PDFs, Word files, Markdown, or text.</p>
        ) : (
          <div className="space-y-2">
            {docs.map((doc) => (
              <DocCard key={doc.document_id} doc={doc} onRemove={() => removeDoc(doc.document_id)} onRetry={() => retry(doc)} />
            ))}
          </div>
        )}
      </section>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between sm:gap-6">
        <Field label="Name this corpus">
          <Input value={corpusName} onChange={(event) => setCorpusName(event.target.value)} placeholder="Untitled corpus" />
        </Field>
        <div className="sm:text-right">
          <Button className="w-full sm:w-auto" variant="primary" disabled={!canContinue} onClick={buildGraph}>
            Build the map
            <ArrowRight size={16} aria-hidden="true" />
          </Button>
          {!canContinue && <p className="mt-2 text-micro text-ink-3">Add at least one document to continue</p>}
        </div>
      </div>
    </div>
  )
}
