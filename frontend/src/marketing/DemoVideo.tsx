import RuledBlock from '../components/ui/RuledBlock'
import { sections } from './copy'

/**
 * The field recording (DSPEC §7.1 §2, plan §5). The owner-supplied recording does not exist yet, so
 * the honest state is a labelled poster — never a broken player and never an invented mp4.
 *
 * The real element is wired and takes over the moment `DEMO_SRC` names the asset at
 * `/demo/societas-demo.mp4`: `<video controls preload="metadata" poster>` with the captions track
 * and the transcript disclosure. Until then the poster branch renders and no `<video>` is emitted,
 * so nothing can 404 or stall.
 */
const DEMO_SRC: string | null = null
const DEMO_POSTER = '/demo/poster.jpg'

export default function DemoVideo() {
  const demo = sections.demo
  return (
    <section>
      <h2 className="text-title text-ink">{demo.heading}</h2>
      <RuledBlock className="mt-4">
        {DEMO_SRC ? (
          <video controls preload="metadata" poster={DEMO_POSTER} className="w-full">
            <source src={DEMO_SRC} type="video/mp4" />
            <track kind="captions" src="/demo/captions.vtt" default />
          </video>
        ) : (
          // The plate sits between the block's own rules — no enclosing card (DSPEC §6).
          <div className="flex aspect-video items-center justify-center bg-survey-paper-2">
            <p className="font-measurement text-mono text-ink-3">{demo.poster}</p>
          </div>
        )}
        <p className="mt-3 max-w-[68ch] text-micro text-ink-3">{demo.note}</p>
        <details className="mt-2">
          <summary className="text-micro text-ink-3">Transcript</summary>
          <p className="mt-1 max-w-[68ch] text-micro text-ink-3">{demo.transcript}</p>
        </details>
      </RuledBlock>
    </section>
  )
}
