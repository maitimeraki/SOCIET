import { meta, sections } from './copy'

/**
 * The field recording (DSPEC §7.1 §2, §8; plan §5). Framed as a survey title block over a brass
 * bumper rule — the cold-open mark, colour as a mark and never as text (R35).
 *
 * The owner-supplied recording does not exist yet, so the honest state is a labelled poster: never a
 * broken player and never an invented mp4. The real element is wired and takes over the moment
 * `DEMO_SRC` names the asset at `/demo/societas-demo.mp4` — `<video controls preload="metadata"
 * poster>` with the captions track and the transcript disclosure. Until then the poster branch
 * renders and no `<video>` (and so no 404) is emitted.
 */
const DEMO_SRC: string | null = null
const DEMO_POSTER = '/demo/poster.jpg'

export default function DemoVideo() {
  const demo = sections.demo
  return (
    <section>
      <h2 className="text-title text-ink">{demo.heading}</h2>
      <p className="mt-2 max-w-[68ch] text-body-lg text-ink-2">{demo.note}</p>

      <figure className="mt-4">
        {/* The survey frame: a title block, then the brass bumper (the cold-open rule). */}
        <div className="border-t-2 border-brass pt-2">
          <p className="font-titling text-label uppercase tracking-[0.14em] text-ink">
            {meta.wordmark}
            <span className="text-ink-3"> · {demo.frameLabel}</span>
          </p>
        </div>

        {DEMO_SRC ? (
          <video controls preload="metadata" poster={DEMO_POSTER} className="mt-3 w-full">
            <source src={DEMO_SRC} type="video/mp4" />
            <track kind="captions" src="/demo/captions.vtt" default />
          </video>
        ) : (
          // The plate sits between the frame's rules — no enclosing card (DSPEC §6).
          <div className="mt-3 flex aspect-video items-center justify-center border border-ink-4 bg-survey-paper-2">
            <p className="font-measurement text-mono text-ink-3">{demo.poster}</p>
          </div>
        )}
        <figcaption className="mt-2 font-measurement text-mono text-ink-3">{demo.plateCaption}</figcaption>
      </figure>

      <details className="mt-3 border-y border-ink-4 py-2">
        <summary className="text-label uppercase text-ink-3">{demo.transcriptLabel}</summary>
        <p className="mt-2 max-w-[68ch] text-body text-ink-2">{demo.transcript}</p>
      </details>
    </section>
  )
}
