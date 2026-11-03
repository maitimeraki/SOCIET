/* eslint-disable react-refresh/only-export-components -- this module deliberately exports its pure request builder so the no-DOM suite can assert the gate and the label without a renderer. */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, startDebate } from '../api/rest'
import { DEBATE_CONFIG_DEFAULTS } from '../api/types'
import type { DebateConfig, DebateStartRequest } from '../api/types'
import { useAuthStore } from '../auth/authStore'
import { useDraftStore } from '../wizard/draftStore'
import QueryComposer from '../components/society/QueryComposer'
import ConfigPanel from '../components/society/ConfigPanel'
import type { PlanLimits } from '../components/society/ConfigPanel'
import Button from '../components/ui/Button'
import Label from '../components/ui/Label'
import { toast } from '../components/ui/Toast'
import { fmtInt } from '../utils/format'

/**
 * The config a fresh form starts with: the defaults, lowered to the plan's caps. An untouched form
 * must always start inside the plan so the server never has to reject it.
 */
export function initialConfig(limits?: PlanLimits): DebateConfig {
  return clampConfig(DEBATE_CONFIG_DEFAULTS, limits)
}

/** Keep an already-edited config inside the plan when entitlements change under it. */
export function clampConfig(value: DebateConfig, limits?: PlanLimits): DebateConfig {
  if (!limits) return value
  return {
    ...value,
    max_agents: Math.min(value.max_agents, limits.max_agents),
    max_rounds: Math.min(value.max_rounds, limits.max_rounds),
  }
}

/**
 * The debate request, or null while there is nothing to ask: no question, or no map (the corpus
 * hasn't been extracted yet). The gate lives at the one place a request is born — no second
 * mechanism — so the step cannot convene before extraction, and the whole thing is assertable
 * without a renderer. The client's corpus name rides along as the run's label.
 */
export function debateRequest(
  datasetId: string | null,
  corpusName: string,
  query: string,
  config: DebateConfig,
): DebateStartRequest | null {
  if (!query.trim() || !datasetId) return null
  return {
    graph_id: datasetId,
    corpus_label: corpusName,
    query: query.trim(),
    selected_domains: [],
    simulation_depth: 'standard',
    config,
  }
}

export default function SocietyPage() {
  const navigate = useNavigate()
  const datasetId = useDraftStore((s) => s.datasetId)
  const corpusName = useDraftStore((s) => s.corpusName)
  const graphSummary = useDraftStore((s) => s.graphSummary)
  const clear = useDraftStore((s) => s.clear)
  const limits = useAuthStore((s) => s.user?.entitlements)
  const [query, setQuery] = useState('')
  const [config, setConfig] = useState<DebateConfig>(() => initialConfig(limits))
  // Derived each render so a plan change cannot leave an out-of-range value in the payload.
  const effectiveConfig = clampConfig(config, limits)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // No session guard here — this is a step, not a host. The workspace returns to the first step with
  // the note IngestPage renders when the corpus is gone. `convene` still refuses without a graph id.

  const convene = async () => {
    const body = debateRequest(datasetId, corpusName, query, effectiveConfig)
    if (!body || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      const { job_id } = await startDebate(body)
      clear() // documents are done with; datasetId survives for the run views
      toast('success', 'Decision convened')
      // The handoff tells the shell to keep the extraction map already on screen (Task 6): the run
      // grows that map in place rather than replacing it (D14).
      navigate(`/runs/${job_id}/roster`, { state: { handoff: true } })
    } catch (err) {
      setError(
        err instanceof ApiError && err.status < 500
          ? `The server rejected this decision: ${err.detail}`
          : `Couldn't reach the server. Nothing ran — try again.`,
      )
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">Your question</p>
        <h1 className="mt-3 font-display text-display font-medium tracking-[-0.03em] text-ink">Ask the question</h1>
        <p className="tnum mt-3 font-mono text-mono text-ink-3">
          Corpus: {corpusName}
          {graphSummary ? ` (${fmtInt(graphSummary.chunks)} sections)` : ''}
        </p>
      </div>

      <div>
        <Label as="label" htmlFor="society-question" className="mb-2 block">
          Your question
        </Label>
        <QueryComposer id="society-question" value={query} onChange={setQuery} onSubmit={convene} />
        <p className="mt-2 max-w-[60ch] font-ui text-body-sm text-ink-2">
          The question picks which parts of the map speak. Broader questions convene more of your panel.
        </p>
      </div>

      <ConfigPanel value={effectiveConfig} onChange={setConfig} limits={limits} />

      {error && <p className="border-t border-danger/40 pt-3 text-body text-ink-2">{error}</p>}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Button variant="primary" className="w-full sm:w-auto" loading={submitting} disabled={!query.trim()} onClick={convene}>
          Convene the panel
        </Button>
        <span className="font-ui text-micro text-ink-3">Decisions take a few minutes — you can watch every pass live.</span>
      </div>
    </div>
  )
}
