import type { AgentProfile, RunEvent, Stance, TurnInfo } from '../events'

function profile(id: string, name: string, archetype: string, stance: Stance, tags: string[]): AgentProfile {
  return {
    agent_id: id,
    identity: { name, archetype, communication_style: 'measured' },
    bio: `${name} reads the record as a ${archetype.toLowerCase()}.`,
    detailed_perspective: `I read the record as a ${archetype.toLowerCase()}; the evidence is on my side.`,
    stance,
    intensity: 0.6,
    confidence: 0.7,
    conviction: 0.65,
    cior: stance === 'POSITIVE' ? 0.4 : stance === 'NEGATIVE' ? -0.4 : 0,
    domain_tags: tags,
    instinct_tags: [],
    communication_radius: 1,
    summary_provenance: [{ doc_id: 'doc-1', title: 'eu-market-2027.pdf', breadcrumb: 'Section 3', chunk_id: 'chunk-1' }],
    confidence_breakdown: { source_breadth: 2, node_density: 5, relationship_connectivity: 0.6 },
  }
}

function turn(agent_id: string, agent_name: string, stance: string, confidence: number, content: string): TurnInfo {
  return { agent_id, agent_name, content, stance, confidence, references: ['steel tariffs'] }
}

export const RUN_SAMPLE: RunEvent[] = [
  {
    type: 'intent',
    intent: {
      direct_keywords: ['expansion', 'European market', '2027'],
      latent_sectors: ['energy', 'trade'],
      search_perspectives: ['regulator', 'industry', 'analyst'],
      core_question: 'market-entry risk vs opportunity in EU steel',
      domain_tags: ['trade', 'energy'],
      entity_frame: ['EU'],
      stance_axis: 'expansion risk vs opportunity',
      extraction_confidence: 0.9,
      llm_model: 'gpt-4',
      llm_provider: 'openai',
    },
  },
  { type: 'stage', stage: 'intake', index: 0, query: 'Should we expand into the European market in 2027?' },
  { type: 'stage', stage: 'selection', index: 1 },
  {
    type: 'selection',
    rows: [
      { name: 'D. Weber', semantic: 0.8, density: 0.64, blended: 0.74 },
      { name: 'M. Chen', semantic: 0.77, density: 0.58, blended: 0.7 },
      { name: 'P. Silva', semantic: 0.41, density: 0.52, blended: 0.45 },
      { name: 'L. Novak', semantic: 0.22, density: 0.4, blended: 0.29 },
    ],
  },
  { type: 'agent', index: 1, total: 3, profile: profile('a1', 'D. Weber', 'Trade analyst', 'POSITIVE', ['steel tariffs', 'EU']) },
  { type: 'agent', index: 2, total: 3, profile: profile('a2', 'M. Chen', 'Entry-cost strategist', 'NEGATIVE', ['entry cost']) },
  { type: 'agent', index: 3, total: 3, profile: profile('a3', 'P. Silva', 'Policy analyst', 'NEUTRAL', ['regulatory risk']) },
  { type: 'stage', stage: 'synthesis', index: 2, agents: 3 },
  { type: 'stage', stage: 'round', index: 3, round: 1, pairs: 2, turns: 3 },
  { type: 'pair_turn', pair_id: 'ds-fixture:D. Weber:M. Chen', response: 'Tariff alignment matters more than entry cost.', error: null },
  { type: 'pair_turn', pair_id: 'ds-fixture:M. Chen:P. Silva', response: 'Entry costs compound in year one.', error: null },
  {
    type: 'round',
    round: 1,
    pairs: [
      { agent_a: 'D. Weber', agent_b: 'M. Chen', shared_entities: ['steel tariffs'] },
      { agent_a: 'M. Chen', agent_b: 'P. Silva', shared_entities: ['entry cost'] },
    ],
    turns: [
      turn('a1', 'D. Weber', 'POSITIVE', 0.72, 'Tariff alignment favours early expansion.'),
      turn('a2', 'M. Chen', 'NEGATIVE', 0.64, 'Entry costs compound in the first year.'),
      turn('a3', 'P. Silva', 'NEUTRAL', 0.58, 'The regulatory path is conditional.'),
    ],
    consensus: { stance: 'POSITIVE', weight_share: 0.55, threshold: 0.8, weights: { POSITIVE: 0.55, NEUTRAL: 0.15, AMBIVALENT: 0.1, NEGATIVE: 0.2 } },
  },
  { type: 'commit', round: 1, opinions: 3, edges: 2, failed: false },
  { type: 'stage', stage: 'round', index: 4, round: 2, pairs: 2, turns: 3 },
  { type: 'pair_turn', pair_id: 'ds-fixture:D. Weber:P. Silva', response: 'A staged entry answers the risk.', error: null },
  {
    type: 'round',
    round: 2,
    pairs: [
      { agent_a: 'D. Weber', agent_b: 'P. Silva', shared_entities: ['steel tariffs'] },
      { agent_a: 'M. Chen', agent_b: 'P. Silva', shared_entities: ['entry cost'] },
    ],
    turns: [
      turn('a1', 'D. Weber', 'POSITIVE', 0.76, 'A staged entry answers the risk.'),
      turn('a2', 'M. Chen', 'NEGATIVE', 0.66, 'Staging delays the payoff.'),
      turn('a3', 'P. Silva', 'POSITIVE', 0.61, 'Conditions can be met by 2027.'),
    ],
    consensus: { stance: 'POSITIVE', weight_share: 0.72, threshold: 0.8, weights: { POSITIVE: 0.72, NEUTRAL: 0.08, AMBIVALENT: 0.05, NEGATIVE: 0.15 } },
  },
  { type: 'commit', round: 2, opinions: 3, edges: 2, failed: false },
  { type: 'activation', round: 2, agents: ['L. Novak'], reasons: { 'L. Novak': 'invited via "steel tariffs"' } },
  { type: 'stage', stage: 'convergence', index: 5, converged: true, rounds_executed: 2, share: 0.83, threshold: 0.8 },
  { type: 'stage', stage: 'verdict', index: 6, converged: true, rounds_executed: 2 },
  {
    type: 'complete',
    converged: true,
    verdict: 'The debate concluded with 67% of turns expressing POSITIVE stance. Confidence score: 0.83.',
    final_stances: { 'D. Weber': 'POSITIVE', 'M. Chen': 'NEGATIVE', 'P. Silva': 'POSITIVE' },
    warnings: [],
    rounds_executed: 2,
    confidence_score: 0.83,
    cluster_details: {
      POSITIVE: { stance: 'POSITIVE', count: 3, total_weight: 0.61, avg_confidence: 0.7, avg_conviction: 0.68, agents: ['D. Weber', 'P. Silva'] },
      NEGATIVE: { stance: 'NEGATIVE', count: 2, total_weight: 0.24, avg_confidence: 0.65, avg_conviction: 0.6, agents: ['M. Chen'] },
      AMBIVALENT: { stance: 'AMBIVALENT', count: 0, total_weight: 0, avg_confidence: 0, avg_conviction: 0, agents: [] },
      NEUTRAL: { stance: 'NEUTRAL', count: 1, total_weight: 0.15, avg_confidence: 0.58, avg_conviction: 0.5, agents: ['L. Novak'] },
    },
    supporting_entities: ['EU single market', 'steel tariffs'],
    opposing_entities: ['entry cost'],
  },
]
