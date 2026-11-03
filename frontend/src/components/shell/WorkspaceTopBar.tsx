import { Link } from 'react-router-dom'
import { STEP_LABELS } from '../../pages/workspaceSteps'
import { inlineLinkClasses } from '../ui/Button'

/**
 * §7.7 The workspace top bar: the wordmark, the question in one line, the three-step
 * indicator, and the way out. The bar is 64px, bone, one hairline under it.
 */
export default function WorkspaceTopBar({ title }: { title: string }) {
  return (
    <>
      {/* Standing, not dismissible: AI Act Art. 50(1). Visible on every workspace step. */}
      <div className="flex min-h-11 shrink-0 items-center border-b border-hairline bg-bone px-6">
        <p className="font-mono text-micro text-ink-3">These are AI-generated perspectives, not human advisors.</p>
      </div>

      <header className="flex min-h-16 shrink-0 items-center gap-4 border-b border-hairline bg-bone px-6">
        <Link to="/overview" className="flex min-h-11 items-center gap-2 text-ink">
          <span aria-hidden="true" className="font-display text-title leading-none">◆</span>
          <span className="sr-only font-ui text-heading font-semibold">Societas</span>
        </Link>
        <p className="min-w-0 flex-1 truncate font-ui text-body-sm text-ink-2">{title}</p>
        <nav aria-label="The steps" className="flex items-center gap-2">
          {(['material', 'question', 'panel'] as const).map((step) => (
            <span key={step} className="inline-flex items-center gap-1.5 font-ui text-[10px] uppercase tracking-[0.06em] text-ink-3">
              <i className="h-2 w-2 rounded-full bg-sand ring-1 ring-rule" />
              {STEP_LABELS[step]}
            </span>
          ))}
        </nav>
        <Link
          to="/runs"
          className={`${inlineLinkClasses} font-ui text-body-sm text-ink-2 underline underline-offset-4 hover:text-ink`}
        >
          Exit
        </Link>
      </header>
    </>
  )
}
