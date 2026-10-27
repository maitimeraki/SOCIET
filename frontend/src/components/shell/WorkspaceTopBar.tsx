import { Link } from 'react-router-dom'

/** §9 The workspace's own top bar — the wordmark, what is being worked on, and the way out. */
export default function WorkspaceTopBar({ title }: { title: string }) {
  return (
    <header className="flex h-16 shrink-0 items-center gap-4 border-b border-rule/60 bg-ground px-4">
      <Link to="/runs" className="inline-flex min-h-11 items-center gap-2 text-ink">
        <span aria-hidden="true" className="font-titling text-title leading-none">◆</span>
        <span className="sr-only font-titling text-heading font-semibold lg:not-sr-only">Societas</span>
      </Link>
      <p className="min-w-0 flex-1 truncate text-body text-ink-2">{title}</p>
      <Link to="/runs" className="inline-flex min-h-11 items-center text-body text-ink-3 hover:text-ink">
        Exit
      </Link>
    </header>
  )
}
