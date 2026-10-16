import { Component, createRef, type ErrorInfo, type ReactNode, type Ref } from 'react'
import { buttonClasses } from './ui/Button'

/** Short, stack-free digest: the error name plus the first line of its message. */
// eslint-disable-next-line react-refresh/only-export-components -- errorDigest is the tested surface of this file
export function errorDigest(error: unknown): string {
  if (!(error instanceof Error)) return String(error)
  const firstLine = error.message.split('\n')[0].trim()
  return firstLine ? `${error.name}: ${firstLine}` : error.name
}

export function AppErrorFallback({
  error,
  onReload,
  onBack,
  containerRef,
}: {
  error: unknown
  onReload: () => void
  onBack: () => void
  containerRef?: Ref<HTMLDivElement>
}) {
  return (
    <div
      ref={containerRef}
      role="alert"
      tabIndex={-1}
      className="mx-auto max-w-[720px] border-t border-ink-4 pt-8 outline-none"
    >
      <p className="text-heading text-ink">Something went wrong</p>
      <p className="mt-2 max-w-[60ch] text-body text-ink-2">
        This view failed to render. Reload to pick your work back up, or head back to the dashboard.
      </p>
      <p className="mt-4 font-measurement text-mono text-ink-3">{errorDigest(error)}</p>
      <div className="mt-6 flex flex-wrap items-center gap-3">
        <button type="button" className={buttonClasses('primary')} onClick={onReload}>
          Reload
        </button>
        <button type="button" className={buttonClasses('secondary')} onClick={onBack}>
          Back to dashboard
        </button>
      </div>
    </div>
  )
}

export class AppErrorBoundary extends Component<{ children: ReactNode }, { error: unknown }> {
  state = { error: null as unknown }

  private readonly containerRef = createRef<HTMLDivElement>()

  static getDerivedStateFromError(error: unknown): { error: unknown } {
    // `?? new Error` because React hands over whatever was thrown, including null/undefined.
    return { error: error ?? new Error('Unknown error') }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (import.meta.env.DEV) console.error('AppErrorBoundary caught', error, info.componentStack)
    this.containerRef.current?.focus()
  }

  private reload = () => window.location.reload()

  // Hard navigation on purpose: after a render crash a full reload is the reliable reset, and it
  // works whether or not this boundary sits inside the router.
  private back = () => window.location.assign('/')

  render() {
    if (this.state.error !== null) {
      return (
        <AppErrorFallback
          error={this.state.error}
          onReload={this.reload}
          onBack={this.back}
          containerRef={this.containerRef}
        />
      )
    }
    return this.props.children
  }
}

export default AppErrorBoundary
