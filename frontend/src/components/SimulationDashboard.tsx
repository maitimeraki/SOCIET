// SimulationDashboard.tsx
import React, { useState } from 'react';

// Type definitions
interface SimulationResult {
  confidence_metrics: {
    overall_confidence: number;
  };
  society_opinion: {
    assessment: string;
    key_drivers: string[];
    risks_identified: string[];
    opportunities_identified: string[];
    recommendations: Array<{
      action: string;
      confidence: string;
      contingencies?: string[];
    }>;
  };
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
}

const SimulationDashboard: React.FC = () => {
  const [scenario, setScenario] = useState<string>('');
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  const runSimulation = async (): Promise<void> => {
    setLoading(true);
    const response = await fetch('/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scenario,
        simulation_depth: 'standard',
        required_perspectives: ['finance', 'legal', 'cultural']
      })
    });
    const data: SimulationResult = await response.json();
    setResult(data);
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-100">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        {/* Header */}
        <div className="text-center mb-12">
          <div className="inline-flex items-center justify-center p-2 bg-gradient-to-r from-indigo-600 to-purple-600 rounded-2xl mb-4">
            <div className="bg-white rounded-xl px-4 py-2">
              <span className="text-2xl font-bold bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">
                Society Simulation Engine
              </span>
            </div>
          </div>
          <p className="text-gray-600 mt-4 text-lg">
            Simulate complex societal impacts with multi-agent AI
          </p>
        </div>

        {/* Input Section */}
        <div className="max-w-3xl mx-auto mb-12">
          <div className="bg-white rounded-2xl shadow-xl border border-gray-100 overflow-hidden">
            <div className="p-6">
              <label className="block text-sm font-semibold text-gray-700 mb-2">
                Describe Your Scenario
              </label>
              <textarea
                value={scenario}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setScenario(e.target.value)}
                placeholder="e.g., 'Should I expand my SaaS into Europe?', 'What would be the impact of implementing a 4-day work week?', 'How would our community respond to a new sustainability initiative?'"
                rows={4}
                className="w-full px-4 py-3 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all resize-none"
              />
              <button
                onClick={runSimulation}
                disabled={loading}
                className="mt-4 w-full bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-semibold py-3 px-6 rounded-xl hover:from-indigo-700 hover:to-purple-700 transition-all transform hover:scale-[1.02] disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100 shadow-lg"
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Simulating Society...
                  </span>
                ) : (
                  'Get Society Opinion'
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Results */}
        {result && (
          <div className="space-y-8">
            {/* Society Opinion Card */}
            <div className="bg-white rounded-2xl shadow-xl border border-gray-100 overflow-hidden">
              <div className="bg-gradient-to-r from-indigo-600 to-purple-600 px-6 py-4">
                <h2 className="text-xl font-bold text-white">Society Opinion</h2>
              </div>
              <div className="p-6">
                <div className="flex items-center justify-between mb-6">
                  <div className="flex items-center gap-3">
                    <div className="relative">
                      <svg className="w-16 h-16 transform -rotate-90">
                        <circle
                          cx="32"
                          cy="32"
                          r="28"
                          stroke="#e5e7eb"
                          strokeWidth="4"
                          fill="none"
                        />
                        <circle
                          cx="32"
                          cy="32"
                          r="28"
                          stroke="url(#gradient)"
                          strokeWidth="4"
                          fill="none"
                          strokeDasharray={`${result.confidence_metrics.overall_confidence * 175.84} 175.84`}
                          strokeLinecap="round"
                        />
                        <defs>
                          <linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%" stopColor="#4f46e5" />
                            <stop offset="100%" stopColor="#9333ea" />
                          </linearGradient>
                        </defs>
                      </svg>
                      <span className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 text-xl font-bold">
                        {(result.confidence_metrics.overall_confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div>
                      <p className="text-sm text-gray-500">Confidence Score</p>
                      <p className="text-xs text-gray-400">Based on multi-agent consensus</p>
                    </div>
                  </div>
                </div>
                <p className="text-gray-700 leading-relaxed text-lg mb-6">{result.society_opinion.assessment}</p>

                <div className="border-t border-gray-100 pt-6">
                  <h4 className="text-sm font-semibold text-gray-700 mb-3">Key Drivers</h4>
                  <div className="flex flex-wrap gap-2">
                    {result.society_opinion.key_drivers.map((d: string) => (
                      <span key={d} className="px-3 py-1 bg-indigo-50 text-indigo-700 rounded-full text-sm font-medium">
                        {d}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Risk/Opportunity Matrix */}
            <div className="grid md:grid-cols-2 gap-6">
              <div className="bg-white rounded-2xl shadow-xl border border-gray-100 overflow-hidden">
                <div className="bg-red-50 px-6 py-4 border-b border-red-100">
                  <h3 className="text-lg font-bold text-red-700 flex items-center gap-2">
                    <span>⚠️</span> Risks Identified
                  </h3>
                </div>
                <div className="p-6">
                  <ul className="space-y-3">
                    {result.society_opinion.risks_identified.map((r: string) => (
                      <li key={r} className="flex items-start gap-2 text-gray-700">
                        <span className="text-red-500 mt-1">•</span>
                        <span>{r}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              <div className="bg-white rounded-2xl shadow-xl border border-gray-100 overflow-hidden">
                <div className="bg-green-50 px-6 py-4 border-b border-green-100">
                  <h3 className="text-lg font-bold text-green-700 flex items-center gap-2">
                    <span>✅</span> Opportunities
                  </h3>
                </div>
                <div className="p-6">
                  <ul className="space-y-3">
                    {result.society_opinion.opportunities_identified.map((o: string) => (
                      <li key={o} className="flex items-start gap-2 text-gray-700">
                        <span className="text-green-500 mt-1">•</span>
                        <span>{o}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>

            {/* Dissenting Views */}
            <div className="bg-gradient-to-r from-amber-50 to-orange-50 rounded-2xl shadow-xl border border-amber-200 overflow-hidden">
              <div className="bg-amber-100 px-6 py-4 border-b border-amber-200">
                <h3 className="text-lg font-bold text-amber-800 flex items-center gap-2">
                  <span>🗣️</span> Dissenting Views
                </h3>
              </div>
              <div className="p-6">
                <div className="grid md:grid-cols-2 gap-6">
                  {result.dissenting_views.map((view, i) => (
                    <div key={i} className="bg-white rounded-xl p-5 shadow-sm border border-amber-100">
                      <p className="font-semibold text-gray-800 mb-3">Alternative View {i + 1}</p>
                      <p className="text-gray-700 mb-4">{view.view}</p>
                      <div className="mb-3">
                        <div className="flex justify-between text-sm mb-1">
                          <span className="text-gray-600">Support Level</span>
                          <span className="font-semibold text-amber-600">{(view.support * 100).toFixed(0)}%</span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2">
                          <div
                            className="bg-gradient-to-r from-amber-500 to-orange-500 rounded-full h-2"
                            style={{ width: `${view.support * 100}%` }}
                          />
                        </div>
                      </div>
                      <p className="text-sm text-gray-500">
                        <span className="font-medium">Why different:</span> {view.why_different.join(', ')}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Agent Profiles */}
            <div className="bg-white rounded-2xl shadow-xl border border-gray-100 overflow-hidden">
              <div className="bg-gray-50 px-6 py-4 border-b border-gray-200">
                <h3 className="text-lg font-bold text-gray-800">Simulation Participants</h3>
                <p className="text-sm text-gray-500 mt-1">Multi-agent perspectives from diverse expertise</p>
              </div>
              <div className="p-6">
                <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {result.agent_profiles.map(agent => (
                    <div key={agent.name} className="bg-gray-50 rounded-xl p-5 hover:shadow-md transition-shadow">
                      <div className="flex items-center justify-between mb-3">
                        <h4 className="font-bold text-gray-800 text-lg">{agent.name}</h4>
                        <span className={`px-2 py-1 rounded-full text-xs font-semibold ${
                          agent.final_stance === 'supportive' ? 'bg-green-100 text-green-700' :
                          agent.final_stance === 'opposed' ? 'bg-red-100 text-red-700' :
                          'bg-gray-100 text-gray-700'
                        }`}>
                          {agent.final_stance}
                        </span>
                      </div>
                      <div className="space-y-2 text-sm">
                        <div>
                          <span className="font-semibold text-gray-600">Expertise:</span>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {agent.expertise.map(e => (
                              <span key={e} className="px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded-full text-xs">
                                {e}
                              </span>
                            ))}
                          </div>
                        </div>
                        <div>
                          <span className="font-semibold text-gray-600">Personality:</span>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {agent.personality.map(p => (
                              <span key={p} className="px-2 py-0.5 bg-purple-100 text-purple-700 rounded-full text-xs">
                                {p}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Recommendations */}
            <div className="bg-white rounded-2xl shadow-xl border border-gray-100 overflow-hidden">
              <div className="bg-blue-50 px-6 py-4 border-b border-blue-100">
                <h3 className="text-lg font-bold text-blue-800 flex items-center gap-2">
                  <span>📋</span> Recommendations
                </h3>
              </div>
              <div className="p-6">
                <div className="space-y-4">
                  {result.society_opinion.recommendations.map((rec, i) => (
                    <div key={i} className={`rounded-xl p-5 border-l-4 ${
                      rec.confidence === 'high' ? 'bg-green-50 border-green-500' :
                      rec.confidence === 'medium' ? 'bg-yellow-50 border-yellow-500' :
                      'bg-gray-50 border-gray-500'
                    }`}>
                      <p className="text-gray-800 font-medium mb-3">{rec.action}</p>
                      {rec.contingencies && (
                        <div className="mt-3">
                          <p className="text-sm font-semibold text-gray-700 mb-2">Contingencies:</p>
                          <ul className="list-disc list-inside space-y-1">
                            {rec.contingencies.map((c: string) => (
                              <li key={c} className="text-sm text-gray-600">{c}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      <div className="mt-3">
                        <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-semibold ${
                          rec.confidence === 'high' ? 'bg-green-200 text-green-800' :
                          rec.confidence === 'medium' ? 'bg-yellow-200 text-yellow-800' :
                          'bg-gray-200 text-gray-800'
                        }`}>
                          {rec.confidence.toUpperCase()} Confidence
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default SimulationDashboard;