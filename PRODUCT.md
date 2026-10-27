# Product

<!-- impeccable:product-schema 1 -->

**Societas** — a panel of experts that argues a hard decision and files a verdict you can act on.

This is the confirmed product truth. Every line below was settled in the working session of 2026-10-17; the decisions behind it are recorded in the Decision Log of `docs/superpowers/plans/2026-10-17-societas-workspace-and-visual-world.md`. Nothing here is inferred, and nothing here is a draft.

## Implementation contract — read this first

This file carries **two layers**: the built product (implemented) and the target (new). An agent must not edit the built layer to deliver the target.

- **Read order:** `docs/DESIGN_SPEC.md` **§0.2 and §15 first**; §1–§14 are the built record.
- **The built layer is context, not a task list.** Do not re-implement anything already shipped; compose it. Only the target is work.
- **One surface per task.** Touch only the files in your row of `DESIGN_SPEC.md` §15.7. Shared files (`Rail`, `AppShell`, `Workspace`, `RunPage`) are changed additively and must keep the E tests green.
- **E — reuse unchanged:** do not edit the file or its behavior.
- **C — additive re-shell:** the behavior, copy, fetch, keyset, empty/error states and tests stay; only the container or route changes.
- **N — new:** add new files, routes or additive functions; never fork an E component.
- **Migration order:** add the three pages and the full-screen workspace first; change the rail and landing **last**. Keep `/dashboard` and its four anchors working until the target passes `DESIGN_SPEC.md` §15.8.
- **If a task needs to edit an E file or change a C behavior, stop and report it.** Do not refactor silently.
- The per-file allowed/forbidden map is `docs/DESIGN_SPEC.md` §15.7.

## Platform

web

## Users

- **Primary — the decider.** A single owner-operator with a decision they cannot look up: a founder weighing a market, a shop owner weighing a second location, a department lead weighing a cut. They decide alone, they are time-poor, and they want both a defensible verdict *and the strongest case against it* — not a chat transcript they have to keep prompting.
- **Equally served — the explainer.** A consultant or analyst who must show their reasoning to a client, a board, or a partner, and who needs the conclusion to leave the app as a document and to trace back to a source.
- **Out of scope — by decision, not omission:** teams, sharing, organisation accounts, tenancy, cross-user access. Ownership stays per-user (`user_id`), and an owner check answers 404, never 403, so existence is never leaked.

**Job to be done:** turn a decision the user cannot check into a verdict they can act on, with the confidence and the dissent stated plainly.

## Product Purpose

Societas convenes a panel of domain-specific experts — drawn from the customer's own documents — who argue the customer's question across computed passes and return a **weighted verdict with a confidence score, the case against, and the sources behind it**. It exists so a decision-maker hears the strongest argument on every side *before* committing, with all of the reasoning inspectable. Success is a verdict the owner trusts enough to act on, grounded in their own material, never a black box.

## Positioning

**Not a chatbot.** A panel of many specialists, a structured argument whose pairings are chosen by the material's own structure, a weighted verdict with a confidence metric, and the whole argument — beside a live map of the customer's material — visible as it forms. A neighbouring single-model assistant cannot truthfully claim a panel of experts, computed pairings, or a division of weighted opinion.

## The experience standard

The bar is the craft of a **billion-dollar startup's product**, applied to a decision tool:

- **Human psychology first, machinery never.** Every surface answers what the person is feeling at that moment and what they need to see next. No surface explains the technology; each one moves the person forward.
- **Feeling before topic.** The first line a stranger reads names what they *feel* — a decision they cannot check — not a use case.
- **Premium and confident.** Generous scale, real material, deliberate colour, considered gradients. Never a template, never a mood, never decoration without a job.
- **Honest by default.** Where proof does not exist, the surface proves the mechanism by *showing the mechanism*. Nothing is claimed that the product does not do.

## Operating Context

- Web app. Flow: public marketing homepage → sign-up/sign-in → **the dashboard** → **a decision**.
- The shell is a persistent left rail — **+ New decision · Documents · Verdict · Runs**, with Account at the foot — beside the region where the selected section renders. Each section is its own page; the rail is the navigation, not a table of contents inside a page.
- The whole lifecycle lives in one workspace, in one fixed order: **add documents → the material is read → the question is asked → the panel argues → the answer is filed.** The order is a decision. A new decision opens that workspace **full-screen**: no rail, one continuous map on the left, the flow on the right, an adjustable divider between them.
- Beside the live work sits **one** map of the customer's material — never a second one. It starts when extraction starts and stays visible to the final answer, grows as the material is read and as opinions are formed, and answers a click on any entry with that entry's details. A document read on the server appears in the customer's map in the same moment it is written; the map is a window onto stored truth, not an illustration of it.
- The map holds three kinds of entry on one canvas: **the material** (what was read from the documents), **the experts** (who the panel is), and **the opinions** (what each expert argued). The customer can show or hide each kind.
- **The dashboard is the account's record, split into three destinations.** **Documents** holds the input — every file, in any format, with how much of each has been read; clicking one opens it. **Runs** holds the process — every decision the account has made, newest first, each opening its full flow: the map, the pairs, the experts, the turns, the answer. **Verdict** holds the outcome — the question and the complete answer, newest first. Each is a page of its own, not a section inside another.
- **A run is not a section.** A run concerns **one** decision and is its own workspace — the argument, the map, the evidence, the answer. Runs is the index of runs; a run is one of them. They are different questions and different surfaces.
- **Documents = the input. Runs = the process. Verdict = the outcome.** Three destinations, three jobs. The customer-facing labels are *Documents · Runs · Verdict*; the routes stay `/documents`, `/runs`, `/results` — a path is an internal identifier and is exempt from the copy law. A new decision is the one primary action in the rail, never a section.

## The Flow

The product is four moments, and the customer must be able to see the work at every one of them. The visual realisation of each is in `docs/DESIGN_SPEC.md` §8–§10; this is what the customer *does* and *gets* — never how it looks.

**Landing.** A new account lands on **Documents** and is asked for exactly one thing: add the first document. An account with material but no filed answer lands on **Runs**, because the work to continue is the decision. An account with a filed answer lands on **Verdict**, the last answer, with Runs one click away. The rail always names all three.

**Moment 1 — the material (add documents).** The owner drops files, pastes links, or connects a source. Each piece is read, and as it is read the customer watches it appear — the map grows in front of them. What they get: a page listing everything they have added, with how much of it has been read. Clicking a document opens it: the extracted text is shown in a reader beside the list.

**Moment 2 — the question.** The owner types the decision they cannot look up, in their own words, and names the body of material it is about. What they get: the sentence the whole run will answer, restated on screen for the duration.

**Moment 3 — the panel (the run).** A panel of specialists is convened **from the owner's own material**, paired up by what their documents have in common, and set arguing across passes. The customer watches this happen: who was chosen, who was paired with whom, what each one argued, how close the panel is to agreement. **Every element the panel produces appears on the map the moment it is produced** — nothing is batched, nothing waits for the run to end. The decision opens full-screen, with no rail: the map grows on the left from extraction to decision; the flow — pairs, turns, experts — runs on the right; the divider is adjustable and the map can be minimised. What they get: a live account of the argument as it forms.

**Moment 4 — the verdict.** The panel files a weighted verdict: the position, a confidence figure, the strongest case against it, who held which view, and every source. The verdict is filed in three places, each with one job: the run's **Verdict** view (the full document), the **Verdict** page (the latest answer in full, every earlier answer as a row), and the run's row in **Runs** (the outcome). What they get: a document they can read on screen and take away as a file — the same document both times.

| Moment | Lives in | What it is |
|---|---|---|
| The material | **Documents** `/documents` | The input; click a row to read the document |
| The question | The full-screen workspace `/new` | The sentence the run answers |
| The panel | The full-screen workspace, then **Runs** → the run | The live flow; later, the stored flow |
| The verdict | The run's Verdict view · **Verdict** `/results` · the run's row in **Runs** | The outcome, at three depths |

**The standard the flow is held to.** A run is reconstructible: opening a finished decision next month shows the identical map it ended with, because the map is a view of what was stored, never an illustration drawn afterwards. A customer who watches a run and a customer who reopens it see the same thing. If those two ever differ, the product has broken its central promise.

**What the customer should feel, moment by moment.**

| Moment | What they should be able to say |
|---|---|
| Homepage | *"It argues the decision and shows me its work."* |
| Sign-up | *"Three fields. Done."* |
| First landing | *"One thing to do: add my documents."* |
| Adding material | *"I can watch it reading — and open any document."* |
| Asking | *"Here is what I want to know."* |
| The panel | *"I can watch it think, and every thought lands on the map."* |
| The verdict | *"Here's the answer, the case against it, and where it came from."* |
| Returning | *"The answer is here; the work behind it is one click away."* |
- A finished answer is read on screen **and** leaves the app as a document.
- A run is reconstructible: **replay = live**. A run reopened next month renders the identical map it ended with, because the map is a view of stored truth, not a likeness.
- Experts are created only from the customer's own material — there is no hardcoded expert store.
- Local-first posture: corpus, map, and runs stay on the machine running the tool; expert text goes to the configured analysis provider.

## Capabilities and Constraints

- **Weight:** CIOR weight = `confidence × conviction × (1 + cior) / 2`; the argument converges when the dominant position's weight share reaches `convergence_threshold` (default **0.8**).
- **Four positions, frozen order:** `POSITIVE, NEUTRAL, AMBIVALENT, NEGATIVE`.
- Position, confidence and intensity are parsed from expert turns; a run can take several passes, and new experts can join between passes.
- **Stack:** React 19 + Vite + Tailwind v4 + sigma/graphology; FastAPI + Postgres + Neo4j behind it.
- **Undecided — do not invent:** the auth provider, whether marketing and app share a host, and the demo video's content and length.
- **Decided — pricing.** The product is **free to use**. "Start free" is a true statement about the product and is the door's label. **No paid tier exists, and none may be implied** on any surface: no price, no tier name, no "upgrade", no "pro", no feature comparison that implies a paid variant. If a paid tier is ever introduced, it is a new decision with its own surface — not something a surface may hint at today.

## Brand Commitments

- **Name:** *Societas* (rename of the internal "Simulation World"). The internal codename "The Chamber" is retired from customer surfaces.
- **No fabricated commercial claims.** No customer logos, testimonials, benchmarks, press, or capability the product does not have. Where a surface wants proof and none exists, it ships authored demonstrative material clearly labelled as an example — and that material goes on the replacement list handed to the owner at finish. **Prices and tiers are a separate matter:** the product is free to use (decided above), so stating that is a fact, not a fabrication; what is banned is any price, tier, benchmark or comparison the product has not been decided to have.
- **The visual world.** The incumbent worlds — "The Chamber" and its successor "The Survey" — are retired; they are *evidence, not authority*. Kept from them: the three installed faces (Archivo, Spectral, JetBrains Mono) and the four-position system. The committed world is the **standard premium-SaaS system** in `docs/DESIGN_SPEC.md`: a neutral daylight ground, one considered accent, cards as the material, and the map as the single dark surface in the product. It is deliberately *not* the cream-and-serif editorial default, *not* near-black with a neon accent, and *not* a generic purple-gradient product page. Gradients are material with a job, never wallpaper. The `impeccable` direction roll in Phase 2 may confirm or replace the palette's roots — every token hangs off one accent and one ground, so the change is one variable wide.
- **The target dashboard's surfaces.** The committed world stays. Gradients remain material with a job: the one primary action's ramp, the map's radial ramp, the answer band's tonal wash, and a 320px page-ground lift. Cards stay flat white; no gradient on a card, a record or a panel. The content grid is the standard 12-column grid, max 1280px, 24px gutters, on the 4px spacing scale.

## Voice and Psychology

The copy is written for a person under pressure, not for a system. In practice:

- **Speak to the fear, not the feature.** "A decision you cannot look up" beats "multi-agent simulation".
- **Never name the machinery.** The copy law below governs every customer-visible string — marketing, app chrome, empty states, errors, toasts, tooltips, aria labels and exports.
- **Every empty state names the one next action.** A brand-new account is asked to do exactly one thing: add the first document. No sample data, no tour.
- **Every state is honest.** A run still in progress says so; a section that cannot yet show something says that, rather than implying a feature that does not exist.

### Copy law — banned words and their replacements

A customer may never read these words: *agent, graph, node, edge, round, retrieval, ontology, model, society, chunk, embedding, vector, LLM, prompt, token, pipeline, job*.

Replacements: agent → **expert** · graph → **the map** · node → **entry** · edge → **connection** · round → **pass** · retrieval → **reading your material** · ontology → **the kinds of things in your material** · model → **the analysis** · society → **your panel** · chunk → **section** · job → **this decision**.

Internal code identifiers, route paths, API fields, log lines and test names are exempt — the law governs rendered text only.

## Evidence on Hand

- Working dashboard components and data model: `frontend/src/components/**`, `frontend/src/run/**`, `frontend/src/graph/**`.
- **Built today:** the shell, the one-page dashboard and its four sections, the two-pane workspace, the live graph, the run stream, the run page and its five tabs, the map drawer, the verdict document.
- **New in the target:** the three-section rail and its three pages; the document reader; the full-screen decision workspace; the continuous map handoff; the adjustable divider; the unified Flow view; auto-open Verdict; round-by-round decision replay.
- **Not built and must not be claimed:** click-a-document content (the endpoint exists; the UI does not) and extraction-growth replay for a past run.
- A design-system target: `docs/DESIGN_SPEC.md`.
- **Absent and must not be fabricated:** real customer logos, testimonials, case studies, press, or performance benchmarks.
- **Real captures** of the running product are taken only once the feature actually works; a mockup standing in for a working feature is a claim, not an illustration.
- **Demo video:** to be supplied by the owner; only its frame and cold-open are specified.

## Scope

- **In:** three account destinations (Documents, Runs, Verdict); a full-screen decision workspace; one continuous map from extraction to decision; an adjustable split and a minimised map; a document reader; a per-run flow (pairs, turns, experts); per-user run history in full detail; an answer that is both readable and exportable.
- **Out by decision:** sharing, teams, organisations, tenancy, cross-user access.
- **Deferred, and said out loud:** extraction-growth replay for a past run (the build's deltas are streamed, not stored; the final map and the decision layer are replayed). Any cross-run, persistent panel of experts: until an expert's identity survives a run, a run's panel is that run's panel.

## Build status — implemented vs new

Marker: **E** = built, reuse unchanged · **C** = built, restyle/restructure without changing behavior · **N** = new.

| Surface | Marker | Built today | The target requires | Do not |
|---|---|---|---|---|
| Shell & rail | C | One item, “Your work” | `+ New decision` · Documents · Verdict · Runs | Do not edit `Rail` before the three pages exist |
| Landing | C | `/dashboard` | Documents (empty) · Runs (no answer) · Verdict (filed) | Do not change `DEFAULT_NEXT` before the pages exist |
| Documents | C | Dashboard section; list only | `/documents` page; table; click to read | Do not change the uploads fetch or `UploadRow` |
| Document reader | N | — | Right-side reader; extracted text | Do not invent an endpoint; use `/api/v1/ingest/documents` |
| Runs | C | Dashboard section; `RunTable`; `/runs` redirects | `/runs` page; every run; opens the workspace | Do not change `RunTable`'s field mapping |
| Verdict | C | Newest answered only | `/results` page; latest in full + earlier rows | Do not fork `AnswerDocument` |
| New decision | C | `/new` inside the rail; three steps | Full-screen, no rail; same step surfaces | Do not rewrite the ingest/graph/question surfaces |
| Continuous map | N | Extraction stream, then the run map is reseeded | One store from extraction to decision | Do not change `GraphCanvas` drawing |
| Adjustable divider | N | Fixed split; minimise/expand | Draggable 25–75%, keyboard, persisted | Do not remove minimise/expand |
| Round pair graph | E | `ChamberFloor` + `PairArc` + `Seat` + the pass scrubber | preserved inside the Flow view; each pass redraws its arcs | Do not delete or replace the graph |
| Flow view | N | Five tabs | the Debate tab composed as the Flow view; all five tabs kept | Do not delete the tabs; compose them |
| Past-run replay | N | Final map | Decision layer replays by pass | Do not claim extraction replay |
| Auto-verdict | N | Verdict-ready link | Open Verdict once on completion | — |

**E — reuse unchanged (do not edit):** `AppShell`, `AppErrorBoundary`, `ToastHost`, `SectionHeading`, `Card`, `Band`, `Rule`, `FiledSheet`, `AnswerDocument`, `RunTable`'s field mapping, `RunsSection`'s fetch/keyset, `DocumentsSection`'s fetch/empty/error, `ResultsSection`'s subject walk, `Workspace`'s panes, `GraphPane`, `GraphCanvas`, `useGraphStream`, `graphStore`, `runStore`, `NodeDetailsDrawer`, `SectionNav`, **`ChamberFloor`, `PairArc`, `Seat`, `ConvergenceTape` and the pass scrubber**, the three step pages' inner surfaces, and the copy law.

**The agent rule.** The rows marked **E** are not edited. The rows marked **C** keep their behavior (fetch, keyset, empty/error, copy) and are re-shelled. The rows marked **N** are added. The full contract is `docs/DESIGN_SPEC.md` §15.7.

## Product Principles

1. **Show the work.** The argument and the map are always inspectable; there is no black-box verdict.
2. **Earned confidence.** Every verdict ships with a weighted confidence and the strongest dissent.
3. **Evidence over assertion.** Claims trace back to the customer's material and to each expert's sources.
4. **The owner decides.** The output is a verdict to act on, not a conversation to continue.
5. **One voice is not enough.** The mechanism is a panel of specialists, not one model's single answer.
6. **Never fake it.** No invented claim, no implied continuity, no synthetic material standing in for a real capture.

## Accessibility & Inclusion

- Target **WCAG 2.2 AA** — a floor, not a polish pass. Every colour pair states its measured contrast ratio, and colour is never the only signal: every position shows a symbol, a colour *and* a word.
- Every interactive element is reachable and operable by keyboard, with a visible focus ring on both the light ground and the dark map surface.
- Motion is suppressed under `prefers-reduced-motion`; the live argument and the map must remain legible as static text, never livestream-only.
