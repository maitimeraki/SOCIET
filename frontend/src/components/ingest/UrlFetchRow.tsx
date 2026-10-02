import { useState } from 'react'
import type { FormEvent } from 'react'
import { LinkSimple } from '@phosphor-icons/react'
import Button from '../ui/Button'

export default function UrlFetchRow({ onFetch, busy = false }: { onFetch: (url: string) => void; busy?: boolean }) {
  const [url, setUrl] = useState('')

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const trimmed = url.trim()
    if (!trimmed) return
    onFetch(trimmed)
    setUrl('')
  }

  return (
    <form onSubmit={submit} className="flex items-center gap-2 rounded-[6px] border border-ink-700 bg-ink-800 px-3 py-2">
      <LinkSimple size={16} className="shrink-0 text-paper-mute" aria-hidden="true" />
      <input
        type="url"
        value={url}
        onChange={(event) => setUrl(event.target.value)}
        placeholder="https://example.com/report — paste a URL to fetch"
        className="h-8 flex-1 bg-transparent text-body text-paper placeholder:text-paper-mute focus:outline-none"
      />
      <Button type="submit" size={32} loading={busy} disabled={!url.trim()}>
        Fetch
      </Button>
    </form>
  )
}
