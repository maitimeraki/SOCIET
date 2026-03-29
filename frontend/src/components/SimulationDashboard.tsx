import React, { useMemo, useState } from 'react';

type Depth = 'shallow' | 'standard' | 'deep';

interface Recommendation {
  action: string;
  confidence: string;
  contingencies?: string[];
}

interface SimulationResult {
  confidence_metrics: {
    overall_confidence: number;
    debate_rounds?: number;
    debate_intensity?: string;
    provider?: string;
    model?: string;
  };
  society_opinion: {
    assessment: string;
    key_drivers: string[];
    risks_identified: string[];
    opportunities_identified: string[];
    recommendations?: Recommendation[];
  };
  recommendations?: Recommendation[];
  dissenting_views: Array<{
    view: string;
    support: number;
    why_different: string[];
  }>;
  agent_profiles: Array<{
    name: string;
    expertise: string[];
    personality: string[];
    final_stance: string;
  }>;
  raw_debate_log?: Array<Record<string, unknown>>;
}

const stanceTone = (stance: string) => {
  const value = (stance || '').toLowerCase();
  if (value.includes('agree') || value.includes('support')) {
    return 'bg-emerald-100 text-emerald-800 border-emerald-200';
  }
  if (value.includes('disagree') || value.includes('oppose')) {
    return 'bg-rose-100 text-rose-800 border-rose-200';
  }
  if (value.includes('question')) {
    return 'bg-amber-100 text-amber-800 border-amber-200';
  }
  return 'bg-slate-100 text-slate-700 border-slate-200';
};

const confidenceTone = (confidence: string) => {
  const c = (confidence || '').toLowerCase();
  if (c === 'high') return 'bg-emerald-100 text-emerald-800';
  if (c === 'moderate' || c === 'medium') return 'bg-amber-100 text-amber-800';
  return 'bg-slate-200 text-slate-700';
};

const SimulationDashboard: React.FC = () => {
  const [scenario, setScenario] = useState('');
  const [depth, setDepth] = useState<Depth>('deep');
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const recommendations = useMemo(() => {
    if (!result) return [];
    if (Array.isArray(result.recommendations) && result.recommendations.length > 0) return result.recommendations;
    if (Array.isArray(result.society_opinion.recommendations)) return result.society_opinion.recommendations;
    return [];
  }, [result]);

  const runSimulation = async (): Promise<void> => {
    if (!scenario.trim()) {
      setError('Please provide a scenario to simulate.');
      return;
    }

    try {
      setLoading(true);
      setError('');
      setResult(null);

      const response = await fetch('http://127.0.0.1:8000/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario,
          context: {},
          simulation_depth: depth,
          required_perspectives: ['finance', 'legal', 'cultural', 'technology']
        })
      });

      if (!response.ok) {
        throw new Error('Simulation failed with status ' + String(response.status));
      }

      const data: SimulationResult = await response.json();
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unexpected error during simulation.');
    } finally {
      setLoading(false);
    }
  };

  const confidence = result?.confidence_metrics?.overall_confidence || 0;
  const confidencePct = Math.max(0, Math.min(100, Math.round(confidence * 100)));
  const roundCount = result?.confidence_metrics?.debate_rounds || 0;
  const agentCount = result?.agent_profiles?.length || 0;
  const dissentCount = result?.dissenting_views?.length || 0;

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <div className="absolute inset-0 pointer-events-none">
        <div className="h-72 bg-linear-to-r from-cyan-200 via-blue-200 to-emerald-200 opacity-55" />
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="h-px bg-linear-to-r from-transparent via-slate-300 to-transparent" />
        </div>
      </div>

      <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-10">
        <header className="rounded-3xl border border-white/60 bg-white/85 backdrop-blur-xl shadow-xl overflow-hidden">
          <div className="p-7 md:p-10">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6">
              <div>
                <p className="text-xs uppercase tracking-[0.28em] text-slate-500 font-semibold">
                  Strategic Simulation Suite
                </p>
                <h1 className="text-3xl md:text-5xl font-black leading-tight mt-2 text-slate-900">
                  Society Intelligence Command Center
                </h1>
                <p className="mt-3 text-slate-600 max-w-2xl">
                  Run multi-agent deliberation, observe disagreement dynamics, and convert collective reasoning into action.
                </p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 min-w-56">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Session Status</p>
                <div className="mt-3 flex items-center justify-between">
                  <span className="text-sm text-slate-600">Engine</span>
                  <span className="text-sm font-semibold text-slate-800">{loading ? 'Running' : 'Idle'}</span>
                </div>
                <div className="mt-2 flex items-center justify-between">
                  <span className="text-sm text-slate-600">Mode</span>
                  <span className="text-sm font-semibold text-slate-800">{depth}</span>
                </div>
                <div className="mt-2 flex items-center justify-between">
                  <span className="text-sm text-slate-600">Last Confidence</span>
                  <span className="text-sm font-semibold text-slate-800">{result ? String(confidencePct) + '%' : 'N/A'}</span>
                </div>
              </div>
            </div>

            <div className="mt-8 grid md:grid-cols-[1fr_auto] gap-4">
              <textarea
                value={scenario}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setScenario(e.target.value)}
                rows={5}
                placeholder="Example: Should we expand our AI platform into the EU market in 2026, given limited legal budget and aggressive growth targets?"
                className="w-full rounded-2xl border border-slate-200 bg-white p-4 text-slate-800 placeholder:text-slate-400 shadow-sm focus:outline-none focus:ring-2 focus:ring-cyan-400/60 focus:border-cyan-300 resize-none"
              />
              <div className="flex md:flex-col gap-3">
                <select
                  value={depth}
                  onChange={(e) => setDepth(e.target.value as Depth)}
                  className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700"
                >
                  <option value="shallow">Shallow</option>
                  <option value="standard">Standard</option>
                  <option value="deep">Deep</option>
                </select>

                <button
                  onClick={runSimulation}
                  disabled={loading}
                  className="rounded-xl px-6 py-3 font-semibold text-white bg-slate-900 hover:bg-slate-800 disabled:opacity-60 disabled:cursor-not-allowed shadow-lg"
                >
                  {loading ? 'Simulating...' : 'Launch Simulation'}
                </button>
              </div>
            </div>

            {error ? (
              <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-rose-700 text-sm">
                {error}
              </div>
            ) : null}
          </div>
        </header>

        {loading ? (
          <section className="mt-8 grid md:grid-cols-3 gap-4">
            {[1, 2, 3].map((n) => (
              <div key={n} className="h-28 rounded-2xl border border-slate-200 bg-white animate-pulse" />
            ))}
          </section>
        ) : null}

        {result ? (
          <main className="mt-8 space-y-6">
            <section className="grid md:grid-cols-4 gap-4">
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Confidence</p>
                <p className="mt-2 text-3xl font-black text-slate-900">{String(confidencePct)}%</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Agents</p>
                <p className="mt-2 text-3xl font-black text-slate-900">{agentCount}</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Rounds</p>
                <p className="mt-2 text-3xl font-black text-slate-900">{roundCount}</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Dissent Views</p>
                <p className="mt-2 text-3xl font-black text-slate-900">{dissentCount}</p>
              </div>
            </section>

            <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex flex-wrap items-center gap-3 justify-between">
                <h2 className="text-2xl font-extrabold text-slate-900">Society Verdict</h2>
                <div className="flex items-center gap-2">
                  <span className="rounded-full bg-cyan-100 text-cyan-800 px-3 py-1 text-xs font-semibold">
                    {result.confidence_metrics.provider || 'provider: n/a'}
                  </span>
                  <span className="rounded-full bg-emerald-100 text-emerald-800 px-3 py-1 text-xs font-semibold">
                    {result.confidence_metrics.model || 'model: n/a'}
                  </span>
                </div>
              </div>

              <p className="mt-4 text-slate-700 leading-8">{result.society_opinion.assessment}</p>

              <div className="mt-6">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Key Drivers</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {result.society_opinion.key_drivers.map((driver) => (
                    <span key={driver} className="rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1 text-xs font-semibold text-cyan-800">
                      {driver}
                    </span>
                  ))}
                </div>
              </div>
            </section>

            <section className="grid lg:grid-cols-2 gap-6">
              <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <h3 className="text-xl font-bold text-slate-900">Agent Interaction Theater</h3>
                <p className="mt-1 text-sm text-slate-500">Each participant profile and final stance in the social debate.</p>
                <div className="mt-5 grid sm:grid-cols-2 gap-4">
                  {result.agent_profiles.map((agent) => (
                    <article key={agent.name} className="rounded-2xl border border-slate-200 p-4 bg-slate-50">
                      <div className="flex items-start justify-between gap-2">
                        <h4 className="font-bold text-slate-800">{agent.name}</h4>
                        <span className={'border rounded-full px-2.5 py-1 text-xs font-semibold ' + stanceTone(agent.final_stance)}>
                          {agent.final_stance || 'unknown'}
                        </span>
                      </div>
                      <div className="mt-3">
                        <p className="text-xs uppercase tracking-[0.15em] text-slate-500">Expertise</p>
                        <div className="mt-1 flex flex-wrap gap-1.5">
                          {agent.expertise.map((e) => (
                            <span key={e} className="rounded-full bg-blue-100 text-blue-800 px-2 py-0.5 text-[11px] font-semibold">
                              {e}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className="mt-3">
                        <p className="text-xs uppercase tracking-[0.15em] text-slate-500">Personality</p>
                        <div className="mt-1 flex flex-wrap gap-1.5">
                          {agent.personality.map((p) => (
                            <span key={p} className="rounded-full bg-violet-100 text-violet-800 px-2 py-0.5 text-[11px] font-semibold">
                              {p}
                            </span>
                          ))}
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              </div>

              <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <h3 className="text-xl font-bold text-slate-900">Debate Dynamics</h3>
                <p className="mt-1 text-sm text-slate-500">Support distribution from dissenting clusters.</p>

                <div className="mt-5 space-y-3">
                  {result.dissenting_views.length === 0 ? (
                    <p className="text-sm text-slate-500">No major dissent clusters detected.</p>
                  ) : (
                    result.dissenting_views.map((view, i) => (
                      <div key={String(i) + view.view.slice(0, 14)} className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                        <div className="flex items-center justify-between text-sm">
                          <span className="font-semibold text-amber-900">Alternative View {i + 1}</span>
                          <span className="font-bold text-amber-800">{Math.round(view.support * 100)}%</span>
                        </div>
                        <div className="mt-2 h-2 rounded-full bg-amber-100">
                          <div className="h-2 rounded-full bg-amber-500" style={{ width: String(Math.max(3, Math.round(view.support * 100))) + '%' }} />
                        </div>
                        <p className="mt-3 text-sm text-slate-700">{view.view}</p>
                        <p className="mt-2 text-xs text-slate-500">Assumptions: {view.why_different.join(', ') || 'n/a'}</p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </section>

            <section className="grid lg:grid-cols-2 gap-6">
              <div className="rounded-3xl border border-rose-200 bg-rose-50 p-6 shadow-sm">
                <h3 className="text-xl font-bold text-rose-900">Risk Surface</h3>
                <ul className="mt-4 space-y-2 text-sm text-rose-900">
                  {result.society_opinion.risks_identified.length === 0 ? (
                    <li className="text-rose-700">No high-priority risks were returned.</li>
                  ) : (
                    result.society_opinion.risks_identified.map((risk) => (
                      <li key={risk} className="rounded-lg border border-rose-200 bg-white px-3 py-2">
                        {risk}
                      </li>
                    ))
                  )}
                </ul>
              </div>

              <div className="rounded-3xl border border-emerald-200 bg-emerald-50 p-6 shadow-sm">
                <h3 className="text-xl font-bold text-emerald-900">Opportunity Surface</h3>
                <ul className="mt-4 space-y-2 text-sm text-emerald-900">
                  {result.society_opinion.opportunities_identified.length === 0 ? (
                    <li className="text-emerald-700">No major opportunities were returned.</li>
                  ) : (
                    result.society_opinion.opportunities_identified.map((opp) => (
                      <li key={opp} className="rounded-lg border border-emerald-200 bg-white px-3 py-2">
                        {opp}
                      </li>
                    ))
                  )}
                </ul>
              </div>
            </section>

            <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900">Action Plan</h3>
              <div className="mt-4 space-y-3">
                {recommendations.length === 0 ? (
                  <p className="text-sm text-slate-500">No recommendations were returned by the API payload.</p>
                ) : (
                  recommendations.map((rec, i) => (
                    <div key={String(i) + rec.action.slice(0, 16)} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                      <div className="flex items-center justify-between gap-3">
                        <p className="font-semibold text-slate-800">{rec.action}</p>
                        <span className={'text-xs font-bold px-2 py-1 rounded-full ' + confidenceTone(rec.confidence)}>
                          {rec.confidence.toUpperCase()}
                        </span>
                      </div>
                      {rec.contingencies && rec.contingencies.length > 0 ? (
                        <ul className="mt-2 list-disc pl-5 text-sm text-slate-600 space-y-1">
                          {rec.contingencies.map((c) => (
                            <li key={c}>{c}</li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  ))
                )}
              </div>
            </section>
          </main>
        ) : null}
      </div>
    </div>
  );
};

export default SimulationDashboard;