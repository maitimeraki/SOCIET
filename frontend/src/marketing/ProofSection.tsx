import { sections } from './copy'

/**
 * The proof section — what used to be the recording. No recording exists and none may be mocked,
 * so the section proves the mechanism by showing it: the three moments a person can watch while a
 * decision runs. The honesty line says plainly that the recording is absent; no player and no frame
 * stand in for a capture (Task 6.3 adds the real captures).
 */
export default function ProofSection() {
  const proof = sections.open
  return (
    <section aria-labelledby="proof-heading">
      <h2 id="proof-heading" className="font-titling text-title text-ink">
        {proof.heading}
      </h2>
      <p className="mt-2 max-w-[68ch] text-body-lg text-ink-2">{proof.note}</p>

      <h3 className="mt-6 font-titling text-label uppercase text-ink-3">{proof.stagesTitle}</h3>
      <ol className="mt-3 grid gap-4 sm:grid-cols-3">
        {proof.stages.map((stage) => (
          <li key={stage.key} className="m-card p-5">
            <p className="font-measurement text-mono text-ink-3">{stage.key}</p>
            <h4 className="mt-2 font-titling text-heading text-ink">{stage.title}</h4>
            <p className="mt-2 text-body text-ink-2">{stage.body}</p>
          </li>
        ))}
      </ol>

      <p className="mt-4 border-t border-border pt-3 text-micro text-ink-3">{proof.honesty}</p>
    </section>
  )
}
