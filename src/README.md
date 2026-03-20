┌─────────────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE LAYER                             │
│  (Web Dashboard / API / CLI - where users submit scenarios/queries)     │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                      ORCHESTRATION ENGINE (The "Government")               │
│  • Parses user input into simulation parameters                          │
│  • Spawns relevant agent societies                                        │
│  • Manages simulation lifecycle (init → debate → consensus → output)     │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                      SIMULATION WORLD (The "Society")                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │   Agent A   │  │   Agent B   │  │   Agent C   │  │   Agent N   │     │
│  │  (Domain 1) │  │  (Domain 2) │  │  (Domain 3) │  │  (Skeptic)  │     │
│  │  Beliefs    │  │  Beliefs    │  │  Beliefs    │  │  Beliefs    │     │
│  │  Memory     │  │  Memory     │  │  Memory     │  │  Memory     │     │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘     │
│         └──────────────────┼──────────────────┘              │           │
│                            ↓                                │           │
│                    ┌───────────────┐                        │           │
│                    │  Message Bus  │ ←── All agent comms     │           │
│                    │  (Pub/Sub)    │     (opinions, debates)  │           │
│                    └───────┬───────┘                        │           │
│                            ↓                                │           │
│                    ┌───────────────┐                        │           │
│                    │  Shared World │ ←── Consensus reality    │           │
│                    │    State      │     (facts, events)      │           │
│                    └───────────────┘                        │           │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                      CONSENSUS & SYNTHESIS LAYER                         │
│  • Debate rounds (structured argumentation)                              │
│  • Belief aggregation (not just voting - weighted by reasoning quality)  │
│  • Dissent preservation (minority opinions included)                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                      OPINION OUTPUT ENGINE                                 │
│  • Generates final "society opinion" - not information dump              │
│  • Includes: Confidence level, Dissenting views, Assumptions made        │
│  • Actionable recommendations with risk analysis                         │
└─────────────────────────────────────────────────────────────────────────┘