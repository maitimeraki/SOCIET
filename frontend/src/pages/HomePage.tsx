import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listRuns } from '../api/rest'
import type { RunSummary } from '../api/types'
import IdleFloor from '../components/chamber/IdleFloor'
import RunTable from '../components/common/RunTable'
import { buttonClasses } from '../components/ui/Button'
import Disclosure from '../components/ui/Disclosure'

const STEPS: { label: string; line: string; to: string }[] = [
  { label: 'Ingest', line: 'Add the documents your experts would have read.', to: '/new/ingest' },
  { label: 'Graph', line: 'Grow the knowledge graph from your record.', to: '/new/graph' },
  { label: 'Question', line: 'Set the question the society debates.', to: '/new/society' },
  { label: 'Roster', line: 'Watch your question become a seated society.', to: '/new/society' },
  { label: 'Debate', line: 'Follow every round on the chamber floor.', to: '/new/society' },
  { label: 'Verdict', line: 'Read the weighted division, honestly split.', to: '/new/society' },
]

const WHY: { title: string; line: string }[] = [
  {
    title: 'Hear the case against',
    line: 'the society argues the decision you are about to make, while changing it is still cheap',
  },
  {
    title: 'Every voice has receipts',
    line: 'each profile cites the graph chunks it grew from (provenance links + confidence breakdown)',
  },
  {
    title: 'Watch it think',
    line: 'pairings, turns, commits, and stance changes are live on the floor; the raw log is one click away',
  },
]

const FAQ: { q: string; a: string }[] = [
  {
    q: 'What is Simulation World?',
    a: 'A local tool that reads the documents your experts would have read, grows a knowledge graph from them, and convenes a society of AI agents drawn from that graph to debate one question to a weighted verdict.',
  },
  {
    q: 'Do I need my own documents?',
    a: 'Yes. The society is built from your corpus: no documents, no graph; no graph, no agents. Add PDFs, Word files, Markdown, text, or a web page to start.',
  },
  {
    q: 'What happens when I convene?',
    a: 'Your question is read into intent terms; candidates are ranked against the graph; each selected agent is synthesized from its cluster and seats on the floor; then rounds begin — agents are paired over shared entities, answer with a stance and confidence, and every round is written to the graph before the next round reads it.',
  },
  {
    q: 'How is the verdict decided?',
    a: "Every turn is weighted by the agent's confidence, conviction, and CIOR; the verdict is the weighted share per stance. If the dominant share stays under the convergence threshold, the page says so plainly: a plurality, not a consensus.",
  },
  {
    q: 'Can agents change their minds?',
    a: "Yes, and you can watch it happen: later rounds read what earlier rounds committed, and each agent's final stance is simply its last turn.",
  },
  {
    q: 'Where does my data live?',
    a: 'This is a local tool: the corpus, the graph, and every run stay on the machine running it. The text agents read and write goes to the LLM provider you configure — point it at a local model if you want everything to stay home.',
  },
  {
    q: 'Which LLM providers work?',
    a: 'Over 100, through LiteLLM: OpenAI, Anthropic, Azure, Bedrock, or a local model over Ollama. Configure one in `.env`.',
  },
  {
    q: 'How long does a run take?',
    a: 'Graph discovery runs about a minute per ten documents; a debate is a few minutes. Both show live progress — nothing is a black box.',
  },
  {
    q: 'Can I see what happens inside?',
    a: 'That is the point of the tool: the roster shows your question becoming agents, the floor shows pairings and turns live, and Artifacts exposes the selection scores, pairs, commits, warnings, and the raw event log.',
  },
  {
    q: 'What happens to finished runs?',
    a: 'They are kept: reopen one and it renders exactly as it ended, round by round, with its verdict, warnings, and final stances — or export the whole run as JSON.',
  },
]

export default function HomePage() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listRuns()
      .then(setRuns)
      .catch(() => setRuns([])) // endpoint lands in Task 20; offline is also an empty list
      .finally(() => setLoading(false))
  }, [])

  const recent = runs.slice(0, 5)

  return (
    <div className="space-y-16">
      <section>
        <p className="text-label uppercase text-brass">Multi-agent deliberation</p>
        <h1 className="mt-3 max-w-[20ch] font-serif text-display-xl text-paper">
          Convene a society of experts. Watch it deliberate.
        </h1>
        <p className="mt-5 max-w-[60ch] text-body text-paper-dim">
          Simulation World reads the documents your experts would have read, grows a panel from your knowledge graph,
          and debates your question to a weighted verdict — every round, every voice, visible.
        </p>
        <div className="mt-7 flex items-center gap-3">
          <Link to="/new/ingest" className={buttonClasses('primary', 40)}>
            Convene a society
          </Link>
          <Link to="/runs" className={buttonClasses('ghost', 40)}>
            Reopen a run
          </Link>
        </div>
        <div className="mt-10">
          <IdleFloor />
        </div>
      </section>

      <section id="how-it-works">
        <h2 className="mb-4 text-heading text-paper">What happens when you convene</h2>
        <ol className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
          {STEPS.map((step, index) => (
            <li key={step.label}>
              <Link
                to={step.to}
                className="block h-full rounded-[6px] border border-ink-700 bg-ink-900 p-4 transition-colors hover:border-ink-600"
              >
                <span className="tnum font-mono text-mono text-paper-mute">{String(index + 1).padStart(2, '0')}</span>
                <span className="mt-2 block text-label uppercase text-paper">{step.label}</span>
                <span className="mt-1 block text-micro text-paper-dim">{step.line}</span>
              </Link>
            </li>
          ))}
        </ol>
      </section>

      <section>
        <h2 className="mb-4 text-heading text-paper">Why run it</h2>
        <div className="grid gap-4 md:grid-cols-3">
          {WHY.map((tile) => (
            <div key={tile.title} className="rounded-[6px] border border-ink-700 bg-ink-900 p-4">
              <span className="block text-heading text-paper">{tile.title}</span>
              <p className="mt-2 text-body text-paper-dim">{tile.line}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="faq">
        <h2 className="mb-4 text-heading text-paper">Questions people ask</h2>
        <div>
          {FAQ.map((item) => (
            <Disclosure key={item.q} summary={item.q}>
              <p className="text-body text-paper-dim">{item.a}</p>
            </Disclosure>
          ))}
        </div>
      </section>

      <section>
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="text-heading text-paper">Recent runs</h2>
          <Link to="/runs" className="text-body text-paper-dim hover:text-accent">
            All runs →
          </Link>
        </div>
        {recent.length === 0 && !loading ? (
          <p className="text-body text-paper-mute">No runs yet. Your conventions will be kept here.</p>
        ) : (
          <RunTable runs={recent} loading={loading} />
        )}
      </section>

      <footer className="flex flex-wrap items-center gap-x-5 gap-y-2 text-micro text-paper-mute">
        <span>◠ Simulation World</span>
        <a href="#how-it-works" className="transition-colors hover:text-paper">
          How it works
        </a>
        <a href="#faq" className="transition-colors hover:text-paper">
          FAQ
        </a>
        <Link to="/runs" className="transition-colors hover:text-paper">
          Runs
        </Link>
        <Link to="/agents" className="transition-colors hover:text-paper">
          Agents
        </Link>
      </footer>
    </div>
  )
}
