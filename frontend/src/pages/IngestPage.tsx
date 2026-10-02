import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ArrowRight } from '@phosphor-icons/react'
import { ingestFiles, ingestUrl } from '../api/rest'
import FileDrop from '../components/ingest/FileDrop'
import DocCard from '../components/ingest/DocCard'
import UrlFetchRow from '../components/ingest/UrlFetchRow'
import StageRail from '../components/common/StageRail'
import Button from '../components/ui/Button'
import Input from '../components/ui/Input'
import Field from '../components/ui/Field'
import { toast } from '../components/ui/Toast'
import { useDraftStore } from '../wizard/draftStore'
import type { DraftDoc } from '../wizard/draftStore'

export default function IngestPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const note = (location.state as { note?: string } | null)?.note
  const { corpusName, docs, setCorpusName, addDocs, updateDoc, removeDoc, setDatasetId } = useDraftStore()
  const [fetchingUrl, setFetchingUrl] = useState(false)

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
    try {
      const response = await ingestFiles(files)
      for (const doc of response.documents) {
        const target = placeholders.find((placeholder) => placeholder.title === doc.title)
        if (target) updateDoc(target.document_id, { ...doc, document_id: target.document_id, status: 'ready' })
      }
      for (const failure of response.failures) {
        const target = placeholders.find((placeholder) => placeholder.title === failure.filename)
        if (target) updateDoc(target.document_id, { status: 'failed', error: failure.detail })
      }
    } catch (error) {
      const reason = error instanceof Error ? error.message : 'unknown error'
      for (const placeholder of placeholders) updateDoc(placeholder.document_id, { status: 'failed', error: reason })
      toast('error', `Upload failed: ${reason}. Nothing was saved — try again.`)
    }
  }

  const handleUrl = async (url: string) => {
    setFetchingUrl(true)
    try {
      const { document } = await ingestUrl(url)
      addDocs([{ ...document, status: 'ready' }])
    } catch (error) {
      toast('error', error instanceof Error ? error.message : 'Download failed')
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
    await handleFiles([doc.file])
  }

  const readyCount = docs.filter((doc) => doc.status === 'ready').length
  const canContinue = readyCount > 0 && corpusName.trim().length > 0

  const buildGraph = () => {
    setCorpusName(corpusName.trim())
    setDatasetId(crypto.randomUUID())
    navigate('/new/graph')
  }

  return (
    <div className="mx-auto max-w-[760px] space-y-8">
      <StageRail
        stages={[
          { key: 'ingest', label: 'Ingest', state: 'running' },
          { key: 'graph', label: 'Graph', state: 'pending' },
          { key: 'question', label: 'Question', state: 'pending' },
        ]}
      />
      <div>
        <p className="text-label uppercase text-paper-mute">Step 1 · Ingest</p>
        <h1 className="mt-2 font-serif text-display text-paper">Build the corpus</h1>
        <p className="mt-3 max-w-[60ch] text-body text-paper-dim">
          Add the documents your experts would have read — PDFs, Word files, Markdown, plain text, or a web page.
        </p>
      </div>

      {note && (
        <p className="rounded-[6px] border border-brass/40 bg-ink-800 px-4 py-3 text-body text-paper-dim">{note}</p>
      )}

      <FileDrop onFiles={handleFiles} />
      <UrlFetchRow onFetch={handleUrl} busy={fetchingUrl} />

      <section className="space-y-3">
        <h2 className="text-heading text-paper">Documents</h2>
        {docs.length === 0 ? (
          <p className="text-body text-paper-mute">Nothing yet. PDFs, Word files, Markdown, or text.</p>
        ) : (
          <div className="space-y-2">
            {docs.map((doc) => (
              <DocCard key={doc.document_id} doc={doc} onRemove={() => removeDoc(doc.document_id)} onRetry={() => retry(doc)} />
            ))}
          </div>
        )}
      </section>

      <div className="flex items-end justify-between gap-6">
        <Field label="Name this corpus">
          <Input value={corpusName} onChange={(event) => setCorpusName(event.target.value)} placeholder="Untitled corpus" />
        </Field>
        <div className="text-right">
          <Button variant="primary" disabled={!canContinue} onClick={buildGraph}>
            Build the graph
            <ArrowRight size={16} aria-hidden="true" />
          </Button>
          {!canContinue && <p className="mt-2 text-micro text-paper-mute">Add at least one document to continue</p>}
        </div>
      </div>
    </div>
  )
}
