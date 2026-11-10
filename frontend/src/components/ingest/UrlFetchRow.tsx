import { useState } from 'react'
import type { FormEvent } from 'react'
import { LinkSimple } from '@phosphor-icons/react'
import Button from '../ui/Button'
import { ruleClasses } from '../ui/Rule'

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
    <form onSubmit={submit} className={`flex items-center gap-2 ${ruleClasses('top')} pt-2`}>
      <LinkSimple size={16} className="shrink-0 text-ink-3" aria-hidden="true" />
      <input
        type="url"
        aria-label="URL to fetch"
        value={url}
        onChange={(event) => setUrl(event.target.value)}
        placeholder="https://example.com/report — paste a URL to fetch"
        className="h-8 flex-1 bg-transparent text-body text-ink placeholder:text-ink-3"
      />
      <Button type="submit" size={32} loading={busy} disabled={!url.trim()}>
        Fetch
      </Button>
    </form>
  )
}
