import type { AgentView, RunEvent, Stance, TurnInfo } from '../events'

function profile(name: string, role: string, stance: Stance, type: string): AgentView {
  return {
    name,
    type,
    role,
    stance,
    strength: 0.65,
    bio: `${name} reads the record as a ${role.toLowerCase()}.`,
    details: `I read the record as a ${role.toLowerCase()}; the evidence is on my side.`,
    confidence: 0.7,
  }
}

/** One agent view with every field filled; a test overrides only what it reads. */
export function sampleView(overrides: Partial<AgentView> = {}): AgentView {
  return {
    name: 'D. Weber',
    type: 'Trade body',
    role: 'Trade analyst',
    stance: 'POSITIVE',
    strength: 0.65,
    bio: 'D. Weber reads the record as a trade analyst.',
    details: 'The tariff record favours an early entry.\n\nThe entry cost is the open question.',
    confidence: 0.7,
    ...overrides,
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
    },
  },
  { type: 'stage', stage: 'intake', index: 0, query: 'Should we expand into the European market in 2027?' },
  { type: 'stage', stage: 'selection', index: 1 },
  { type: 'agent', index: 1, total: 3, profile: profile('D. Weber', 'Trade analyst', 'POSITIVE', 'Trade body') },
  { type: 'agent', index: 2, total: 3, profile: profile('M. Chen', 'Entry-cost strategist', 'NEGATIVE', 'Company') },
  { type: 'agent', index: 3, total: 3, profile: profile('P. Silva', 'Policy analyst', 'NEUTRAL', 'Regulator') },
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
    consensus: { stance: 'POSITIVE', weight_share: 0.55, threshold: 0.8, weights: { POSITIVE: 0.55, NEUTRAL: 0.15, ABSTAIN: 0.1, NEGATIVE: 0.2 } },
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
    consensus: { stance: 'POSITIVE', weight_share: 0.72, threshold: 0.8, weights: { POSITIVE: 0.72, NEUTRAL: 0.08, ABSTAIN: 0.05, NEGATIVE: 0.15 } },
  },
  { type: 'commit', round: 2, opinions: 3, edges: 2, failed: false },
  { type: 'activation', round: 2, agents: ['L. Novak'], reasons: { 'L. Novak': 'invited via "steel tariffs"' } },
  { type: 'stage', stage: 'convergence', index: 5, converged: true, rounds_executed: 2, share: 0.83, threshold: 0.8 },
  { type: 'stage', stage: 'verdict', index: 6, converged: true, rounds_executed: 2 },
  {
    type: 'complete',
    converged: true,
    verdict: 'The debate concluded with 67% of turns expressing POSITIVE stance. Confidence score: 0.83.',
    narrative: '## Recommendation\nExpand, cautiously.\n\n## Reasoning\nSteel tariffs bite the entry cost.',
    dissenting_views: [{ stance: 'NEGATIVE', view: 'Entry cost outweighs the single market.' }],
    evidence: [{ entity: 'EU single market', claim: 'Lowers per-unit distribution cost.' }],
    final_stances: { 'D. Weber': 'POSITIVE', 'M. Chen': 'NEGATIVE', 'P. Silva': 'POSITIVE' },
    warnings: [],
    rounds_executed: 2,
    confidence_score: 0.83,
    cluster_details: {
      POSITIVE: { stance: 'POSITIVE', count: 3, total_weight: 0.61, avg_confidence: 0.7, avg_conviction: 0.68, agents: ['D. Weber', 'P. Silva'] },
      NEGATIVE: { stance: 'NEGATIVE', count: 2, total_weight: 0.24, avg_confidence: 0.65, avg_conviction: 0.6, agents: ['M. Chen'] },
      ABSTAIN: { stance: 'ABSTAIN', count: 0, total_weight: 0, avg_confidence: 0, avg_conviction: 0, agents: [] },
      NEUTRAL: { stance: 'NEUTRAL', count: 1, total_weight: 0.15, avg_confidence: 0.58, avg_conviction: 0.5, agents: ['L. Novak'] },
    },
    supporting_entities: ['EU single market', 'steel tariffs'],
    opposing_entities: ['entry cost'],
  },
]
