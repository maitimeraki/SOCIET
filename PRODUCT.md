# Product

<!-- impeccable:product-schema 1 -->

> **Draft for review.** Written unattended from the explicit brief (the Impeccable init interview had no answer mechanism in this session; every field not confirmed by repository evidence is marked `[inferred]`). Confirm or correct the inferred lines before the build.

## Platform

web

## Users

- **Primary:** a single owner-operator weighing a real business decision — a founder, shop owner, or department lead in economics/business (e.g. "should I expand into Europe in 2027?"). `[inferred]` They decide alone, are time-poor, and want a defensible verdict *and the case against it*, not a chat transcript to keep prompting.
- **Secondary:** analysts / enterprise decision-support staff who must show their reasoning to a board or partner. `[inferred]`
- **Deferred:** teams and collaborative groups (explicit brief: primary user is a single owner).

**Job to be done:** turn a hard business decision into an evidence-grounded verdict the owner can act on.

## Product Purpose

Societas convenes a society of domain-specific AI agents that debate a business question and return a **CIOR-weighted verdict with a confidence score and dissenting views**. It exists so a decision-maker can hear the strongest case for and against a call *before* committing, with the reasoning inspectable. Success is a verdict the owner trusts enough to act on — grounded in their own material, not a black box.

## Positioning

**Not a chatbot.** Many specialized agents, a structured debate with computed (Cypher) pairings, a weighted verdict with a confidence metric, and the full debate and knowledge graph shown as it forms. A neighboring single-model assistant cannot truthfully claim a multi-agent society, computed pairings, or a division of weighted opinion.

## Operating Context

- Web app. Flow: public marketing homepage → sign-up/sign-in → dashboard (run timeline + live debate graph). `[inferred — homepage and auth are new; the dashboard exists today]`
- Agents are created **only** from graph retrieval over the user's own corpus — no hardcoded agent store. (Evidence: `CLAUDE.md` Agent Society System.)
- A run is reconstructible: "replay = live" (a finished run renders exactly as it ended). (Evidence: `docs/DESIGN_SPEC.md`.)
- Local-first posture: corpus, graph, and runs stay on the machine running the tool; agent text goes to the configured LLM provider. (Evidence: incumbent spec FAQ.)
- The owner will add a **demo video** to the homepage. (Explicit brief.)

## Capabilities and Constraints

- **CIOR weight** = `confidence × conviction × (1 + cior) / 2`; convergence when the dominant stance's weight share ≥ `convergence_threshold` (default **0.8**). (Evidence: `CLAUDE.md`.)
- **Four stances**, frozen order: `POSITIVE, NEUTRAL, AMBIVALENT, NEGATIVE`. (Evidence: `CLAUDE.md`, `index.css`.)
- Stance/confidence/intensity come from parsing LLM turns; a debate can run several rounds with new agents activating between rounds.
- **Stack:** React 19 + Vite + Tailwind v4 + graphology/sigma. (Evidence: `frontend/`.)
- **Undecided (do not invent):** pricing, plan tiers, auth provider, whether marketing and app share a host/domain, the demo video's content/length.

## Brand Commitments

- **Name:** *Societas* (rename of "Simulation World"; internal codename *"The Chamber"*). (Explicit brief.)
- The **deliberation-as-chamber** metaphor and a Greek/Latin civic-society register are the incumbent identity. `[inferred]`
- Existing **"The Chamber" tokens** are *evidence, not authority*: ink `#100E09`, parchment `#F2EBDD`, verdigris `#43A98B`, brass `#D9A741`; Newsreader (serif) / Public Sans / IBM Plex Mono. (Evidence: `frontend/src/index.css`.) May be kept or deliberately replaced — see `docs/DESIGN_SPEC.md`.
- **No fabricated commercial claims** — no prices, customers, benchmarks, or capability the tool does not have. (Impeccable law; incumbent §2.3 honesty rule.)

## Evidence on Hand

- Working dashboard components and data model: `frontend/src/components/**`, `frontend/src/run/**`, `frontend/src/graph/**`.
- Design spec: `docs/DESIGN_SPEC.md` ("The Survey").
- **Absent and must not be fabricated:** real customer logos, testimonials, case studies, press, or performance benchmarks. `[absence]`
- **Demo video:** to be supplied by the owner. `[explicit brief]`

## Product Principles

1. **Show the work.** The debate and the graph are always inspectable; there is no black-box verdict.
2. **Earned confidence.** Every verdict ships with a weighted confidence and the strongest dissent.
3. **Evidence over assertion.** Claims trace back to the corpus and to each agent's provenance.
4. **The owner decides.** The output is a verdict to act on, not a conversation to continue.
5. **One voice isn't enough.** The mechanism is many specialized agents, not one model's single answer.

## Accessibility & Inclusion

- Target **WCAG 2.2 AA**. `[inferred — no product-specific standard was established; recorded as the default floor.]`
- Motion-sensitive users honored (`prefers-reduced-motion`); the debate must remain legible as static text, never livestream-only.
