# LarkVision — Design Proposal: The Decision Ledger

**Status:** Proposal for owner review. Nothing here is implemented, and no existing design file was edited.
**Revision 2 — aligned to `DESIGN_PRODUCT_V7.html`.** Revision 1 was written against the code at HEAD. The owner has since named `DESIGN_PRODUCT_V7.html` as the authoritative interface design: its colour, structure, layout and type are the system this file now specifies. `DESIGN.md` (the Quiet Room) and `docs/DASHBOARD_DESIGN.html` are superseded, and the latter has been deleted from the repository. Where revision 1 and V7 disagreed, V7 has won and revision 1 has been corrected — §3.10 lists every such correction, so nothing changed silently.
**Date:** 2026-11-20, revised 2026-11-22.
**Read against:** `DESIGN_PRODUCT_V7.html` (measured block by block: 125,332 bytes of CSS in four blocks, 10 views, 10 dialogs), the code as checked out (branch `feat/graph-agent-output-redesign`, HEAD `43e6dc3`), and the security-audit findings in `run-2/REPORT.md` where they touch a screen.
**Existing design files:** `DESIGN_PRODUCT_V7.html` (the authority, kept unchanged), `docs/DESIGN_SPEC.md` (the record, now stale in its palette and type — §3.1), `PRODUCT.md` (product truth).

---

## 0. Summary

**Diagnosis.** The live app is competent and conformant, and it reads as a generic warm editorial SaaS: a bone ground, a high-contrast serif display, an evergreen primary, beige bands, shadowed cards and a dashboard shell. The prototyped chain (`DESIGN_LEDGER_PREVIEW.html` → `V2` → `V3` → `V4` → `V6` → `V7`) had already left that behind: indigo ink, a neutral daylight ground, tinted planes, panels with tinted heads, and Archivo expanded at display sizes with no serif anywhere in the interface. **`DESIGN_PRODUCT_V7.html` is that endpoint, and it is this proposal's system.** The gap this file has to close is therefore not "what should the design be" — V7 answers that — but "the shipped React app still renders the old world, and here is every token, component and page it must change to render V7's".

**Direction: The Decision Ledger, as V7 renders it.** A decision is a filed record. Passes are its entries. The weighted share is its total. The case against is the note in the margin. The convergence line is drawn the way a ledger draws a total: a double rule. The system is three planes — a tinted rail, a sheet-white utility bar, and ledger-paper content — with every section of a page an object: a 10px panel with a tinted head and foot.

**Signature: the convergence rule.** The existing convergence tape, unchanged, with a double rule drawn at the 0.80 threshold. None of the four reference sites has a threshold object, and this one is the product's own mechanism made visible.

**Kept from the current build:** the map as the one dark instrument; the filed sheet and its anatomy; the four position symbols with words; the copy law and the current copy voice; the labelling of examples as "Worked example"; the pricing data (Free 1,000 · Starter 8,000 at $10 · Studio 16,000 at $20 · Enterprise custom); WCAG 2.2 AA.

**What changed in this revision.** Twelve things, all of them measured from V7 rather than chosen: the ground (`#F1F2EE`), the panel ladder (`--rail`/`--sheet`/`--panel-head`/`--panel-line`/`--hairline`/`--record`), the 10px panel radius, the removal of the serif from the interface, the type scale at V7's own `clamp()` values, the five material layer colours, the explicit gradient rule (one radial ramp, on the map; the primary action is flat, and `DESIGN_SPEC.md`'s plum action ramp is withdrawn), the three-plane shell at 280px/60px/1400px, the page-head ledger rule, the ten dialogs, and the scenario matrix. §3.10 is the full diff against revision 1.

**Decisions the owner must take before any code** (full list in §12): the accent is now settled (D2, indigo, because V7 uses it), and so is the ground (D3); what remains open is the document of record (D5), the pricing rows that are hard-coded (D6), the word "corpus" (D7), the threshold window (D8), the Method page wording (D9), and whether the shipped app is migrated to V7 at all (D11, new).

---

## 1. Scope, sources and method

**Asked for:** an analysis of four reference sites (their pricing, about and other pages), an analysis of the current frontend, and a new design file. The current design files are not edited.

**Reference sites** (the four named by the owner; no other sites are used anywhere in this file):

| Site | Pages analysed | Page height at 1280px |
|---|---|---|
| maritime.sh | home, pricing, security (its closest "about" equivalent is a trust page) | 10,218 · 5,867 · 3,952 px |
| boxes.dev | home (pricing is the `#pricing` section), about | 12,192 · 2,669 px |
| openrelay.inc | home, inference pricing, about | 7,246 · 4,639 · 3,659 px |
| inkbox.ai | home, pricing, integrations (first viewport only; height not measured) | 4,305 · 5,119 px |

**Current frontend:** the dev server at `localhost:5173`, measured with the same extractor used on the references, plus source reads of the shell, the marketing page, the record pages, the workspace, the primitives and the tokens. Signed-in screens (Documents, Runs, Verdict and the decision workspace) were not captured, because they need a session. Their layout is described from source and from `DESIGN_SPEC.md` §15, and each description says so.

**Method:**
- Headless capture with the gstack browse tool, because the Chrome extension was not connected. Only public pages were loaded. No form was submitted and no credential was entered.
- Per page: computed background and text colours, families, size and line-height pairs, weights, radii, shadows, borders, container widths, section tops and heights, and root custom properties.
- Every contrast ratio in this file was computed from the hex values with the WCAG 2.2 relative-luminance formula. None is estimated.
- The ui-ux-pro-max design-system and domain searches were run, and their outputs were checked against the product. The top design-system pattern (scroll storytelling), style (Liquid Glass, which is an Apple-platform style), palette (black with gold, a luxury default) and type (a fashion serif pairing) were rejected as unfit for a decision tool. The domain results were generic defaults and were used only as negative examples (§5.5).

---

## 2. The application context the design must serve

From `PRODUCT.md`, the product truth:

- **Who.** The decider: one owner-operator with a decision they cannot look up, time-poor, deciding alone. And the explainer: a consultant or analyst who must show their reasoning to a client, board or partner. Ownership is per user. Teams, sharing and organisations are out of scope.
- **The job.** Turn a decision the user cannot check into a verdict they can act on, with the confidence and the dissent stated plainly.
- **The flow.** Add documents → the material is read → the question is asked → the panel argues in passes → the answer is filed. A new decision opens full-screen, with the map and the flow side by side and an adjustable divider.
- **The mechanism the design must show.** Experts are convened from the customer's own material, paired by shared ground, and set arguing across passes. A pass's weight is confidence × conviction × (1 + cior) / 2. The argument converges when the dominant position's share of weight reaches 0.8. The four positions, in frozen order: POSITIVE, NEUTRAL, AMBIVALENT, NEGATIVE.
- **The three destinations.** Documents is the input, Runs is the process, Verdict is the outcome. The rail reads + New decision · Documents · Verdict · Runs, with Account at the foot.
- **The standard.** Replay equals live. A finished answer is read on screen and leaves the app as the same document. No logo, testimonial, benchmark or capability is shown unless it is real.
- **Copy law.** These words never reach a customer: agent, graph, node, edge, round, retrieval, ontology, model, society, chunk, embedding, vector, LLM, prompt, token, pipeline, job. Replacements: expert, the map, entry, connection, pass, reading your material, the kinds of things in your material, the analysis, your panel, section, this decision.
- **Pricing (decided).** Free to start. Starter $10 for 8,000 units a month. Studio $20 for 16,000 units a month. Enterprise custom. One unit pool per month, no per-question invoice, no seats.
- **Accessibility floor.** WCAG 2.2 AA. Colour is never the only signal. Every position shows a symbol, a colour and a word.

**The emotional brief (derived).** The person is alone, under pressure, and about to commit money or reputation. They need calm, specific evidence and an honest account of what is not known. The design must feel like a careful instrument that shows its work. It must not feel like a chat product, a generic admin dashboard or a luxury brand.

---

## 3. The current interface, measured

### 3.1 The three documents disagree, and the code has moved past two of them

| Topic | `PRODUCT.md` (committed) | `docs/DESIGN_SPEC.md` (record) | `DESIGN.md` (Quiet Room) | Code at HEAD |
|---|---|---|---|---|
| Ground | "a neutral daylight ground" | grey `#ECEFF4` | warm bone `#F4EFE6` | bone `#F4EFE6` |
| Accent | "one considered accent" | plum `#823A86` | evergreen `#1E4B38` | evergreen `#1E4B38` |
| Display face | kept faces: Archivo, Spectral, JetBrains Mono | Archivo | Fraunces | Fraunces (`--font-display`) |
| Reading face | Spectral | Spectral | Archivo | Archivo |
| Refused look | "not the cream-and-serif editorial default" | refuses cream and serif | is the cream-and-serif direction | is the cream-and-serif direction |
| Shell | rail: + New decision, Documents, Verdict, Runs | one-item rail (record); §15 target | rail | rail 72px at `md`, 264px at `lg` |
| Records | "cards as the material" | ruled records; cards for objects | sheets for documents; ruled records for lists | sheets and shadowed cards |
| Pricing | Starter $10 / 8,000; Studio $20 / 16,000; Enterprise custom | "No pricing, no tier" on sign-up (§8.2) | Desk $0 and Studio $29 placeholders | Starter $10 / 8,000; Studio $20 / 16,000; Enterprise custom |

How to read this. `PRODUCT.md` is the product truth, and it names the committed world: a neutral daylight ground, one accent, cards as material, and an explicit refusal of the cream-and-serif editorial default. The code implements the Quiet Room, which is that default. The commit history confirms the move: `f31d479` (2026-10-25, "the app speaks one visual language"), `8420e31` (2026-10-30, "the Quiet Room colour tokens") and `546a64f` (2026-10-30, "the Quiet Room type scale"). `DESIGN_SPEC.md` still describes the grey and plum world and cites `frontend/src/index.css` as its token source, so its palette and type sections no longer describe the built app. Its §15 lists `DocumentsPage`, `RunsPage` and `ResultsPage` as not yet built. All three now exist in `frontend/src/pages/`.

Two observed drifts the code has made against the record:
- The sign-up fields are **boxed** (1px border, 8px radius). `DESIGN_SPEC.md` §11 specifies a ruled baseline with no box.
- The built **NEGATIVE** symbol is a filled down-pointing triangle, visible on the homepage and sign-up captures. The record specifies a cross-hatch.

So "the current design" is not one document. The honest baseline for this proposal is the code, because that is what the owner sees.

### 3.2 The measured tokens (`frontend/src/index.css`, `@theme`)

| Role | Token | Value | Contrast (computed unless marked) |
|---|---|---|---|
| Ground | `--color-bone` | `#F4EFE6` | — |
| Sheet | `--color-paper` | `#FFFCF6` | ink 17.35:1 (DESIGN.md §4.2) |
| Band | `--color-sand` | `#EAE2D4` | — |
| Hairline | `--color-hairline` | `#D8D0C2` | 1.34:1 on bone (decorative) |
| Record rule | `--color-rule` | `#8A806E` | 3.40:1 on bone · 3.03:1 on sand |
| Ink | `--color-ink` | `#191814` | 15.51:1 on bone (DESIGN.md §4.2) |
| Ink 2 | `--color-ink-2` | `#443F36` | 9.12:1 on bone (DESIGN.md §4.2) |
| Ink 3 | `--color-ink-3` | `#6B6457` | 5.11:1 on bone · **4.55:1 on sand** |
| Accent | `--color-accent` | `#1E4B38` | 8.65:1 on bone |
| Caution | `--color-caution` | `#8F3A1C` | used for the case against |
| Pine (map) | `--color-map-ground` | `#0B1510` | — |

Type (`--text-*`): hero `clamp(56px, 4.2vw + 24px, 104px)` Fraunces 500 · display `clamp(40px, 3vw + 16px, 64px)` · title 32/38 · heading 24/30 at 600 · subhead 20/30 · body 16/26 · body-sm 14/22 · label 12/16 at 600 with +0.08em · micro 11/16 · mono 13/20 · numeral `clamp(56px, 5vw, 80px)` at 500.

Radius `xs` 6 · `sm` 8 · `md` 12 · `lg` 16 · `xl` 24. Shadows: `card`, `sheet`, `map` (`0 24px 80px` at 28% pine), `overlay`. Gradients: `map`, `first-light`, `morning`, `marked`. Motion: 120, 180, 240 and 560 ms at `cubic-bezier(0.2, 0, 0, 1)`.

### 3.3 The live homepage (`/`), measured at 1280px

Height 7,634px, eleven bands (tops and heights in px):

| Band | Top | Height | Surface |
|---|---|---|---|
| Hero (text and evidence desk) | 73 | 918 | bone |
| "Your material, handled plainly" | 991 | 195 | bone |
| "The problem" | 1,186 | 465 | sand |
| "How it works" | 1,651 | 572 | bone |
| "The difference" | 2,222 | 986 | sand |
| "What you get" | 3,208 | 770 | bone |
| "Why you can check it" | 3,978 | 699 | sand |
| "The honest part" | 4,677 | 690 | bone |
| "Use cases" | 5,366 | 872 | sand |
| "Questions" | 6,238 | 586 | bone |
| Close | 6,824 | 401 | pine |

Nine section headings are set at 54.4px / 56.6px in Fraunces 500. The hero heading is 77.8px Fraunces 500 across three lines. The hero is the strongest composition on the page: a text column on the left, and an "evidence desk" on the right. The desk holds a pine map card, a paper quote card and a filed sheet that overlaps the bottom edge. Every band is a flat fill, so the page is a sequence of identically built sections.

The page is built from `frontend/src/marketing/Hero.tsx` (919 lines). Its default export composes section functions in order: `HeroSection` (with `EvidenceDesk` and `Nav`), `Facts`, `Problem`, `HowItWorks`, `Difference` (with `ChatBubble`), `WhatYouGet`, `Trust`, `Limits`, `UseCases`, `Questions`, `Close` and `Footer`, plus the small helpers `BrandMark` and `Eyebrow`.

Details that matter for the critique:
- "How it works" numbers its four steps 01 to 04 in ruled columns. The steps are a real sequence, so the numbering is correct.
- "The difference" sets chat bubbles against the filed sheet. The bubbles look like any chat product, and that weakens the contrast the section is trying to make.
- "The problem" uses three ruled statements. This is a good device and the proposal keeps it.

### 3.4 Sign-up (`/auth/signup`)

A split screen. On the left, a paper sheet of about 420px holds the form. On the right, a thesis line and a worked-example filed sheet. The inputs are boxed. The primary is a flat evergreen button with a card shadow. The filed sheet carries the honest line "These are AI-generated perspectives, not human advisors", which the proposal keeps.

### 3.5 Pricing (`/pricing`)

Above the fold: a "PLANS" eyebrow, a 56px Fraunces heading ("Pay for the material. And the arguments."), a lead, a numbered rule list ("01 One unit pool per month"), and two form controls, Currency and Billing country, before any plan appears. Below: Starter at $10 a month (outline button) and Studio at $20 a month (evergreen button), each a paper card with a rule table (Units per month, Panel size, Passes per decision). Then an Enterprise band on sand with "Talk to the founder" and a mono note.

Two problems:
- The form controls come before the plans.
- The rule table shows **Panel size 12** and **Passes per decision 4** for every plan. Those values are hard-coded in the fallback rows (`PricingPage.tsx` lines 38–39, 52–53 and 62–63). Only the dynamic branch (lines 73–74) reads `plan.max_agents` and `plan.max_rounds`. The fallback values must be sourced from plan configuration, or removed, before launch. The proposal treats them as claims that need a source.

### 3.6 The shell and the record pages (from source)

- **Shell** (`components/shell/AppShell.tsx`): `min-h-screen bg-bone`. The main column is `max-w-[1320px]`, `px-6`, `pt-8`, `pb-24` at `md` and `pb-32` below, `lg:px-12`. There is no top bar.
- **Rail** (`components/shell/Rail.tsx`): `w-[72px]` at `md`, `lg:w-[264px]`, with `border-r border-hairline bg-bone`. It is a `nav aria-label="Sections"`, with a primary "New decision" button at the top, a list of `NavLink` items with a 16px icon column, and an account foot with a round initials badge on `accent-soft` and a "Sign out" link.
- **Overview** (`pages/OverviewPage.tsx`): a morning-gradient wash behind the header, a date eyebrow, a greeting in the display face, a state line. Below, `lg:grid-cols-[minmax(0,1.6fr)_minmax(300px,0.75fr)]`: a main column of sections and a 300px `aside` of stacked cards.
- **Verdict** (`pages/ResultsPage.tsx`): `lg:grid-cols-12`. The latest answer takes eight columns. "Earlier answers" takes four columns in an `aside`, with a mono count and ruled rows (question, date, stance, share).
- **Documents and Runs** (`pages/DocumentsPage.tsx`, `pages/RunsPage.tsx`): present in the code. Not captured, because they need a session. `DESIGN_SPEC.md` §15.2 and §15.4 describe the intended ruled table on a 12-column grid.
- **Workspace** (`components/workspace/Workspace.tsx`): a `--map-w` split, with the map on one side and the activity pane on the other. The order swaps below `lg`. There is a `SplitDivider`, with a default ratio of 0.4 and a range of 0.3 to 0.7, and minimise and expand states.

### 3.7 Primitives (from source)

- **Button** (`components/ui/Button.tsx`): four variants. `primary` is `action-fill rounded-md shadow-card`, a flat evergreen fill with a 12px radius. `secondary` is paper with a rule border. `ghost` is mono text with an underline in the rule colour. `danger` is paper with a danger border and label. Heights 32, 40 and 48px.
- **Filed sheet** (`components/ui/FiledSheet.tsx`, `components/run/AnswerDocument.tsx`): the position symbol and word, the share as a meter with a mono figure, the case against as caution-coloured text, and the sources.
- **Chip** (`components/ui/Chip.tsx`): 6px radius, mono labels, and a `StateChip` for run states.
- **Map** (`components/graph/GraphCanvas.tsx`, `plot-ground`): the one dark surface. A radial pine ramp, seven Sigma canvas layers, a text alternative and layer toggles.

### 3.8 Where the generic reading comes from

Each finding below is tied to a measurement or to a line of code.

1. **The default look.** The frontend-design guidance names three looks that AI-generated design clusters around. The first is "a warm cream background with a high-contrast serif display and a terracotta accent". The Quiet Room matches it: bone `#F4EFE6`, Fraunces 500 at 77.8px, and a sienna caution `#8F3A1C`. The point of the guidance is that such defaults appear regardless of subject.
2. **Repetition with no scale contrast.** Nine section headings share one size. Ten bands alternate two beige tones, and the eleventh is the pine close. The page has no largest idea and no quiet idea, so every section carries the same weight.
3. **Card-and-shadow geometry.** Seven shadowed surfaces, and radii of 12, 16 and 24px across buttons, cards and sheets. The geometry reads as a consumer app. An instrument would use fewer, sharper edges.
4. **The dashboard template.** A date eyebrow, a greeting heading, and a 1.6fr / 0.75fr grid with a stacked-card aside. This is the standard admin layout, and it is the first screen a returning owner sees.
5. **The same card grid, three times.** "What you get back", "Where it earns its keep" and the Verdict and Runs side panels are all four-up or two-up grids of the same card form.
6. **Boxed fields.** The record's answer was a ruled baseline. The built field has a box, so the form looks like every other sign-up.
7. **Pricing leads with controls.** Currency and billing-country selects sit above the plans, and a numbered list labels rules that are not a sequence. Numbers that carry no sequence add structure without information.
8. **The proof is small.** The evidence desk is the strongest idea on the homepage, but its filed sheet is about a third of the viewport at 1280px. The product's own object never leads a screen at full scale.

### 3.9 What to keep

- The evidence-desk concept in the hero (map, quote, sheet), with the proportions changed in §8.2.
- The dark map as the one dark instrument.
- The filed sheet as the verdict object, with its anatomy (position, share, case against, sources) and its "Worked example" label.
- The four position symbols with words. They are the product's strongest visual idea (`PositionMark`).
- The three ruled statements in "The problem" and the ruled lists in "The honest part".
- The copy voice: "The decision you can't look up", "Start your first decision", "A panel of experts reads your documents, argues the question, and files an answer."
- The pricing data and the Enterprise band.
- The motion grammar (120, 180, 240 and 560 ms) and the reduced-motion rule.

---

### 3.10 What this revision changed, and why

Revision 1 was written against the shipped code. The owner has since named `DESIGN_PRODUCT_V7.html` as the authority, so revision 1 was re-measured against V7 and corrected wherever the two disagreed. Every correction is listed here, so no change is silent.

| # | Topic | Revision 1 said | V7 says (measured) | What this file now says |
|---|---|---|---|---|
| 1 | Ground | `#F3F4F1`, "the ground `PRODUCT.md` commits to" | `--ground: #F1F2EE` | `#F1F2EE` (§6.1). A cooler, slightly greener paper. |
| 2 | The light ladder | four surfaces: ground, sheet, band, hairline | **six** roles in five planes: `--ground`, `--rail`, `--sheet`, `--panel-head`, `--panel-line`, `--hairline`, plus `--record` | §6.1's ladder, with every contrast ratio computed. The rail and the tinted panel head are new and they are what makes the app read as a document, not a dashboard. |
| 3 | Graphite | `--color-ink: #16181D` | `--graphite: #15171C`, with `--graphite-hover: #2B3038` as a sixth ink | §6.1. The hex changed by a hair; the hover ink is new. |
| 4 | Record rule | `#8A806E` on bone | `--record: #7C848F` | §6.1. `--record` is now the only grey that clears 3:1, so it is the only grey allowed to hold a meaningful boundary. |
| 5 | Hairline | `#D5DAE1` | `--hairline: #DDE1D7` (green-warmed) alongside `--panel-line: #C7CDC2` | §6.1. Two decorative greys, and the rule that neither carries meaning alone. |
| 6 | Accent | Indigo `#2D3F9C` proposed as D2 | `--accent: #2D3F9C` **is already what V7 ships** | Confirmed, not proposed. D2 becomes "decided by V7". `--accent-hover` is `#24357F`, `--accent-soft` is `#E7EAF6`. |
| 7 | Display type | Fraunces leaves the UI, Archivo expanded takes over | V7 ships **only** Archivo and JetBrains Mono for the interface; Georgia appears in one `.paper` block only | §6.2. Confirmed, and the `.paper` exception is stated so nobody re-introduces a serif "for the document". |
| 8 | Type scale | `display-xl clamp(48px,4.6vw+14px,84px)`, `display clamp(36px,2.8vw+12px,52px)`, `numeral clamp(64px,6vw,96px)` | `hero-h1 clamp(40px,4.9vw,74px)`, `display clamp(30px,2.4vw+10px,40px)`, `numeral clamp(44px,4.4vw,58px)`, plus `display-sm`, `headline`, `sheet-q`, `panel-kicker`, `fig-sm` | §6.2 reproduces V7's `clamp()` values verbatim. Every size is smaller than revision 1 proposed, and every one of them is now read from the file rather than chosen. |
| 9 | Width axis | `font-stretch` 100–120% | 105–116% | §6.2. The axis is real and used; the extremes were overstated. |
| 10 | Panel radius | sheets at 8px, no panel object at all | **the panel is the unit of layout**, at **10px**, with a tinted head and foot | §6.4 and §6.5. This is the single largest structural change: a page is a `.page-stack` of panels, not a grid of cards. |
| 11 | Surfaces rule | "a sheet never gets a shadow · a record never gets a box" | same two outcomes, but derived from four planes, and the panel's head is tinted rather than ruled | §6.5's three rules, which supersede the two-line version. |
| 12 | Gradients | "no gradient except the map's radial ramp", left as an assertion | confirmed by measurement, and the `DESIGN_SPEC.md` §3 plum action ramp is **withdrawn** | §6.9, a new section: the one radial ramp, the three `linear-gradient` utilities that are not gradients, and the flat primary. |
| 13 | Layer colours | none | five material layers, light and night | §6.1. New. The map needs them and they had no spec. |
| 14 | Rail | 240px at `lg`, 72px at `md`, active state a 2px accent rule | **280px** expanded, **76px** collapsed, hidden below `lg` | §7.11 and §10.3. The nav order is Documents · Runs · Verdict, not Documents · Verdict · Runs. |
| 15 | App content width | 1280px | `.content` at **1400px**, `32px 40px 96px` | §6.3. Marketing is `.site-wrap` at 1280px. |
| 16 | Page head | not specified | a title block closed by a **1px `--record`** rule, with a mono meta count on the right | §8.5. This rule is why an app page reads as a ledger heading. |
| 17 | Landing page | fourteen parts | **ten** sections: a hero, eight `.site-section`s (each with a margin label), and the night close band | §8.2, with every margin label and every `h2` quoted from V7. |
| 18 | Pricing | three plans, "the Free plan is not a column" | **four** plans, Free included, as four cards plus a row-by-row `.cmp-table` | §8.3. This **reverses** a decision revision 1 had recorded as approved. Free is named on `/pricing`; the Billing panel keeps three. |
| 19 | Documents | reader as an overlay | reader is an inline **sticky 560px panel** in a `1fr / 24px / 560px` split | §8.8. The overlay reader in revision 1 was a misreading of the built app. |
| 20 | Verdict layout | 8/4 columns | `minmax(0,1fr) minmax(296px,336px)`, and the aside is a flush record of earlier verdicts | §8.7. |
| 21 | Runs | one record with a 12-column grid | **three** panels: plan usage, the filter, the decisions | §8.9. Plan usage is a billing surface inside the app and it was missing entirely. |
| 22 | Billing, Account | not specified as pages | six billing panels and four account panels, with every kicker and every explanation | §8.10, §8.11. Both are new. Billing has no page in the shipped app at all. |
| 23 | Dialogs | a drawer and a toast | **ten dialogs** and one command palette | §8.13. The modal surface is specified as a set, because V7 ships it as one. |
| 24 | Scenarios | states were described per page, unevenly | a **scenario matrix**: 15 scenarios × 12 pages | §8.14, new. The owner asked for "each pages and scenario"; this is that table. |

**What did not change, because V7 agrees with revision 1:** the indigo accent; the refusal of the serif; the refusal of gradients on controls; the convergence rule as the signature; the four positions in frozen order with symbol, colour and word; the copy law; the map as the only dark instrument; the motion grammar of 120/180/240/560ms on one curve; WCAG 2.2 AA; "a sheet carries no shadow".

**What this file still cannot decide for the owner:** whether the shipped React app is migrated to V7 at all (D11). V7 is a prototype; the app at HEAD renders the Quiet Room. Everything in §6, §8 and §11 is the work of closing that gap.

---

## 4. The four reference sites

Each site is described from computed styles and from the captures. Measured values come first, and the judgement follows.

### 4.1 maritime.sh — infrastructure for AI agents; light, Geist, mono labels

**Pages:** home (10,218px), pricing (5,867px), security (3,952px). There is no about page. Security is the closest "others" page: a trust document.

**Home structure** (container 1280px, 32px gutters):

| Band | Top–bottom (px) | Content |
|---|---|---|
| Hero | 0–720 | A framed rounded panel with a dotted field, a centred heading, a navy primary, a pill secondary with three brand glyphs, and a text link |
| Logo strip | 720–874 | "Backed by Y Combinator" and a logo marquee |
| "Agents are not web apps." | 874–1,705 | 36/45 two-tone heading (ink line, grey line); three feature cards with small diagrams |
| "You ship the agent. We run everything under it." | 1,705–2,998 | Five numbered steps (a real sequence) beside a product panel |
| "Deploy in one command." | 3,078–3,863 | Tabs for Dashboard, CLI and SDK, each with a product screenshot |
| "$1 a month per agent." | 3,863–4,756 | A dotted map and a price list |
| "Built for every kind of agent." | 4,836–6,727 | A six-tile bento of product screenshots |
| "When your agent needs more." | 6,727–7,690 | Three large tiles and three small tiles, each with a price |
| "Add-ons." | 7,690–8,214 | Horizontal cards |
| Startup credits | 8,214–8,610 | A blue rounded panel: "Building an agent startup? Get up to $10,000 in credits." |
| Close | 8,610–9,563 | One large heading and one CTA |
| Footer | 9,563–10,218 | Four link columns |

**Colour.** Page `#F4F5F7`. Body text `#1F2937`. Headings and the primary button `#0B1220`. Greys `#4B5563` and `#6B7280`. Hairlines are `rgba(11,18,32,0.10)` at 1px. The brand blue `#2553C4` carries links and accent words. Two illustration colours, yellow `#F4C542` and light blue `#5AB0F0`, appear only in artwork. A hard "sticker" shadow `2px 2px 0 #1F1C19` appears in illustrations, and a soft lift `0 24px 48px -24px rgba(11,18,32,0.22)` on panels.

**Type.** Geist throughout, with Geist Mono for small uppercase labels. The hero is 104px at 98.8px line height, weight 400. Section headings are 36/45 at weight 400, in two tones. Feature titles are 19/26 at 600. Weight 400 dominates the page (496 text nodes at 400, 63 at 600).

**Components.** A navy primary, 44px tall with a 4px radius and a white label at 14px/600. A pill secondary (999px radius). Cards are white with a 1px rgba-navy border and an 8 to 10px radius. The hero frame has a rounded 1px border on the page ground.

**Pricing** (5,867px). A 48/50 two-tone heading: "Simple pricing." in ink, "Per agent, or per second." in grey. A right-aligned explainer sits on the heading's baseline, with one underlined link. Three equal white cards each have a mono uppercase eyebrow that names the job the plan serves: "FOR AGENTS THAT STAY", "FOR JOBS THAT FINISH", "FOR APPS WITH A SCREEN". Each shows a product name at 20px, a price at 48px with a small unit ("/mo per 2 GB", "/h per vCPU and 2 GB", "/h awake"), a 1px divider and a check list at 14px. A single-line rule note sits under the cards. Further sections: a slider calculator ("What would you pay? Drag to your monthly use."), a bill ("Your bill. Every charge, in one place."), add-ons ("No extra charge on the plans."), a rates table ("Rates. The same on every plan.") and an accordion FAQ.

**Security** (3,952px). A 36/40 heading at weight 500. Below it, one 704px column of ten sections, each with an 18/28 heading at 600 and prose. Hairlines at 10% alpha separate them. There are no images, and the sign-up button is the only control. It is a long-form trust document, read top to bottom.

**What to borrow:** the two-tone heading split as a hierarchy device; a mono eyebrow that names the job each plan serves; a plan card with a price, a unit line and a check list; a rule note under the grid; a trust page as one narrow column with short section headings.

**What to avoid:** the dotted field and the sticker shadows (decoration); the brand-glyph row (a product-specific device); logo marquees (LarkVision has no customers to show, and must not invent any).

### 4.2 boxes.dev — cloud computers for coding agents; dark-first, Inter, mono labels

**Pages:** home (12,192px, with pricing as the `#pricing` section) and about (2,669px).

**Home structure** (container 1200px plus 32px gutters):

| Band | Top–bottom (px) | Content |
|---|---|---|
| Hero | 0–640 | A full-bleed photograph of a laptop on a desk with a dark overlay; a bold left-aligned headline; two CTAs; a "Backed by Y Combinator" pill |
| Product window | 630–1,428 | A full-width app window that bleeds into the next band |
| Surfaces | 1,428–2,557 | H2 "Manage your agents from any surface." beside device cards |
| Product | 2,557–3,825 | H2 "Linux machines in the cloud, not local worktrees." with 14/21 feature cards |
| Automation | 3,825–5,059 | H2 "Start from anywhere…" with integration chips |
| How it works | 5,059–6,974 | H2 "From your laptop to the cloud in three steps." Three numbered steps, a real sequence |
| Compare | 6,974–8,188 | H2 "We couldn't find an ADE with everything we wanted — so we built it." |
| Pricing | 8,188–9,644 | Two-tone H2, then five plan columns in one row |
| Teams | 9,644–10,340 | H2 and three text links |
| FAQ | 10,340–11,280 | "FAQ." at about 115px bold, then an accordion |
| CTA band | 11,280–11,702 | "Free your coding agents." at 84px bold |
| Footer | 11,702–12,192 | Four link columns |

**Colour.** The page is near-black, `#0A0A0B` to `#0D0D10`. Text is `#F4F4F5` (primary), `#C4C4C8` (secondary) and `#8B8B92` (muted). The accent is green `#22C983`, used on checkmarks, status and a 1px glow ring `rgba(34,201,131,0.18)`. The light button is `#FAFAFA` with a `#0A0A0B` label at an 8px radius. The dark button is `#0D0D10`. Hairlines are `rgba(255,255,255,0.14)` and `0.08`. The product window carries `0 32px 80px rgba(0,0,0,0.55)`.

**Type.** Inter at 400, 500, 600 and 700. Display sizes run from about 80px to 115px at weight 700 on the about page, the FAQ and the CTA band. Section headings are 46/48 at 600. Labels and plan lines use `ui-monospace` at 10 to 15px in uppercase. Body is 13.5 to 16px.

**Pricing.** A centred heading in two tones: "Get started for free." in white bold, "Pay only for compute." in grey bold. Five plan columns in one row: Trial $0, Starter $19, Pro $99 with a "RECOMMENDED" mono pill on the card's top edge, Max $249, and Teams Custom. Each column has an uppercase mono plan label, a price at about 46px bold with a unit ("/ user / mo"), a mono line that states the included usage ("20 box-hours included"), a description, a hairline and a green check list. The recommended card has a slightly lighter surface and border.

**About** (2,669px). A 58/59 bold heading on the left, four lines. On the right, a terminal artifact with macOS window chrome, mono 13px lines and green prompts, which tells the founding story as a `git log`. Section eyebrows are mono labels with a hairline running to the right ("OUR STORY"). A founders section follows, then five values numbered 01 to 05. The numbers carry no sequence.

**What to borrow:** the product window as a full-width band directly under the hero; the unit line under each price; the Recommended pill on the card's edge; an eyebrow with a trailing hairline; a left headline paired with a right-hand artifact on the about page.

**What to avoid:** photography (it implies a physical setting the product does not have); green glow rings; numbered values that carry no sequence; the 115px bold FAQ heading, which shouts in a trust product.

### 4.3 openrelay.inc — inference and compute; light, Geist, instrument cards, no shadows

**Pages:** home (7,246px), inference pricing (4,639px) and about (3,659px).

**Home structure** (container 1360px plus 32px gutters):

| Band | Top–bottom (px) | Content |
|---|---|---|
| Hero | 0–1,032 | Left: a 44.8/46.6 heading at weight 400, "The inference delivery network.", a sub-line and two CTAs. Right and below: a framed isometric instrument with mono labels ("SEA · H100", "GPUS ONLINE 70", "SITES IN POOL 5") |
| Metrics | 1,032–1,229 | Stat tiles ("2.5x faster autoscaling", "2T+ tokens") |
| Logos | 1,229–1,323 | "Built by engineers previously at" and a row of names |
| Tiers | 1,323–2,023 | "Built for teams that outgrew the hyperscaler bill." Three animated tier cards |
| Three ways | 2,023–2,605 | "Three ways onto one network.": Call the endpoint · Rent a GPU · Supply the network |
| Terminal | 2,605–3,377 | "Your terminal is the console. So is your agent." Two cards |
| CDN | 3,377–4,406 | "A CDN, for inference." A diagram |
| API | 4,406–5,499 | "Control OpenRelay from your own stack." A code block |
| FAQ | 5,499–6,215 | An accordion with 66px rows |
| CTA | 6,215–6,710 | "Deploy your first workload." |
| Footer | 6,774–7,182 | Four columns (Product, Pricing, Resources, Company) in Geist Mono |

**Colour.** Page `#FDFCFC`, ink `#08090A`, muted `#5C6370`, surfaces `#F6F7F8` and `#F9FAFB`, borders `#E3E4E8` at 1px. The accent is lime `#C7F25A`, used on highlight surfaces, with lime ink `#4D7C0F` for text. A second accent, blue `#0065F4`, carries secondary actions. Amber `#F5B83D` marks pending states. **There are no shadows anywhere on the site.**

**Type.** Geist at 400, 500 and 600. The headings are 44.8 to 60.8px at weight 400 with tight leading. The H2s run from 38 to 50px at weight 400. The H3s are 17 to 21px at weight 500. Geist Mono carries labels, identifiers, footer headings and tags.

**Components.** A black primary with a 6px radius (86×32 small; 151×48 large). A white outline secondary with a 1px border. Pill tags at 999px for small status. Tables are bordered boxes with 1px rules. The **instrument card** is the signature device: the `overlay_network` table on the about page lists region codes in mono (iad1, sfo3, ord1, ams1), region names, a bar, a percentage and a "● healthy" status, with "regions online 4 / 4" in the footer. The tier cards on the homepage animate in a loop.

**Inference pricing.** A centred 60.8/62 heading at weight 400: "Pay per token, nothing else." A 20px sub-line. Two CTAs: a black "Get an API key" and an outline "API reference". A fact row of four short items separated by black bullets: "Billed per 1M tokens · Async 20% to 50% off · Batch 50% off · Cached input rates". A left-aligned 30/36 heading at 500, "Rates per 1M tokens", with a 672px lead. Then a bordered four-column rate table with mono tags: "Sync" with a BASE RATE tag, "Async within 1 hour" with a 20% OFF SYNC tag, "Async within 24 hours" with a 50% OFF SYNC tag, and "Batch" with a 50% OFF SYNC tag. A model table follows.

**About.** A 60.8/63 heading on the left: "Resilient compute, for everyone." On the right, the `overlay_network` instrument. Principles appear as three steps (Detect, Reroute, Heal), which is a real sequence. Then "Designed for failure." at 43/65, a principles list, and "Join the team." with job rows as 44px black pills.

**What to borrow:** the bordered rate table with mono tags for comparative numbers; the fact row under the CTAs; the instrument card as proof on a page that is not the product; flat surfaces where hairlines carry the structure; mono for every identifier.

**What to avoid:** the isometric illustration and the looping tier animations (decorative motion); the lime accent for text (its contrast works on highlight surfaces, not on body copy); black pill rows used as links.

### 4.4 inkbox.ai — agent identity and channels; violet band, Funnel Display, pill controls

**Pages:** home (4,305px), pricing (5,119px) and integrations (first viewport only).

**Home structure** (container 1080 to 1188px):

| Band | Top–bottom (px) | Content |
|---|---|---|
| Announcement | 0–36 | A dark violet strip: "Announcing hosted agents and our $5.3M seed. Read the announcement →" |
| Hero | 36–823 | A violet band `#74629D`. A pill "Backed by Y Combinator". A 48/51 heading, "Run agents here. Reach them anywhere.", with the last word in coral. A sub-line and two pill CTAs. A row of eight harness chips. A prompt card: "No account yet? Copy and paste this prompt…" with a code block and a Copy button |
| Teammate | 823–1,222 | A light panel `#F8FBFF`. 32/34 heading "Reach your agent like a teammate", with four channel headings: Email, Phone/iMessage/WhatsApp, Slack, Agent2Agent |
| Hosted | 1,223–1,603 | "Run your agent on Inkbox", with four features: Wakes on new messages, Sleeps when idle, Works on a schedule, A real computer |
| Capabilities | 1,604–2,723 | Four features at 20 to 24px, each with a product panel |
| Integrations | 2,724–3,081 | "UseInkbox with any agent harness", with pill chips |
| Identity | 3,082–3,706 | "Agents need more than intelligence. They need an identity." |
| Close | 3,784–4,305 | A violet band with a CTA |

**Colour.** Warm off-white page `#FBFAF6`. Violet band `#74629D`. Deep violet `#3E2A53` for the announcement bar, the dark pill and text on light. Lavender text `#E4CDFF` and `#EEEDFA`. A coral accent `#F9B1B5` marks one highlight word, the prices and the Recommended pill. Panel `#F8FBFF`. The light primary is `#F7F5FF` with a `#0B0A12` label. A lavender glow `rgba(210,152,242,0.25) 0 0 36px` sits behind the primary.

**Type.** Funnel Display at 600 for all headings (48/51 for the hero, 32/34 for sections, 18 to 24px for features). Geist at 400 and 500 for body and controls. Geist Mono for code and small labels.

**Components.** Pill buttons and pill chips throughout (999px). Cards at 16px, plan cards at 24px. A segmented toggle, "Monthly | Annual · 2 months free", with a coral chip. A row of harness chips as proof of integration.

**Pricing.** A 48/51 heading: "Start free." in coral, "Pay as you grow." in white. The toggle. Three plan cards on dark violet: Free at $0, Developer at $25 and Startup at $167 a month, with coral prices and lavender units. A coral "RECOMMENDED" pill sits across the top edge of the Startup card. Each card holds a tinted callout that states the plan's included identities ("3 agent identities. Each gets:", "10 …", "100 …") and a check list. Below: "Custom pricing", "Overage", "Add-ons" and an FAQ, each at 32/34, and a full-width "Talk to us" pill.

**Integrations** (first viewport). A violet band with the heading "Works with the / harness you already run", the second line in coral, and undersea decorative illustrations. Below, light split cards with the heading "Create an identity from the CLI" and a mono code chip on a lavender tint.

**What to borrow:** one coral accent word inside the headline as the single emphasis device; the segmented monthly and annual toggle with the saving chip; a callout inside each plan card that states what the plan includes; the Recommended pill straddling the card edge; the harness-chip row as integration proof.

**What to avoid:** the mascot and undersea art (the product must not be cute, and `DESIGN.md` already forbids mascots); the violet and coral palette in a trust product; pill geometry everywhere; a prompt card that tells the visitor's own agent to sign up.

### 4.5 Cross-site comparison (measured)

| | maritime.sh | boxes.dev | openrelay.inc | inkbox.ai | LarkVision (live) |
|---|---|---|---|---|---|
| Ground | `#F4F5F7` light | `#0A0A0B` dark | `#FDFCFC` light | `#FBFAF6` warm light, with violet bands | `#F4EFE6` bone |
| Accent | navy `#0B1220` action; blue `#2553C4` links | green `#22C983` | lime `#C7F25A` surfaces, `#4D7C0F` text, blue `#0065F4` | violet `#74629D` and `#3E2A53`; coral `#F9B1B5` | evergreen `#1E4B38` |
| Display | Geist 400 · 104 / 48 / 36px | Inter 700 · about 80 to 115px | Geist 400 · 44.8 to 60.8px | Funnel Display 600 · 48px | Fraunces 500 · 77.8 / 54.4px |
| Body | Geist 14–16px | Inter 13.5–16px | Geist 14–16px | Geist 14–16px | Archivo 14–16px |
| Mono | labels | labels, plan lines | identifiers, tags, footers | code, small labels | JetBrains Mono (figures) |
| Radius | 4px buttons; 8–10px cards; 999px pills | 8px buttons; 12–16px cards; 999px chips | 6px throughout; 999px tags | 999px pills; 16–24px cards | 6 / 8 / 12 / 16 / 24px |
| Shadow | soft `0 24 48 −24`; sticker 2px | product float `0 32 80` at 55% | none | lavender glow 36px | four soft tokens |
| Container | 1280 (+32) | 1200 (+32) | 1360 (+32) | 1080–1188 | app 1320 (+48 at `lg`); marketing text 477–824 |
| Hero | centred, framed dotted field | full-bleed photograph, left text | left text with instrument | centred on violet band | split: text beside evidence desk |
| Loops | logo marquee; bento keyframes | product window | tier and queue keyframes | sway; sparkles | state and bloom only |
| Pricing | 3 cards, mono eyebrows | 5 columns; unit line; Recommended | one bordered rate table | 3 cards; toggle; callout | 2 cards and an Enterprise band |

Notes. The figures come from computed styles at 1280px. The boxes.dev wordmark appears to be a serif, but the page's type is sans throughout. The only serif on the four sites is that wordmark.

### 4.6 What the four sites agree on, and what it means for LarkVision

1. **All four are grotesk plus mono.** None sets its headings in a serif. Fraunces is therefore distinctive, but the reason it is there is editorial taste, not the subject, and the category is moving the other way.
2. **Two of four show a product surface on the first screen** (boxes with its window, openrelay with its instrument). The other two show a product panel within the first three screens (maritime, inkbox). The product is the image in every case. LarkVision' evidence desk is smaller than any of them.
3. **Pricing is short.** Three to five columns, one unit line, one recommended mark, and a custom door. None of the four puts a slider or a form in the first screen of its pricing page. The LarkVision pricing page puts its controls first.
4. **Colour is restrained.** Each page has one accent, used on actions and highlights. The LarkVision homepage obeys this, while the rest of the app does not always.
5. **Texture and glow are decoration on three of the four.** The dotted field, the lavender glow and the isometric art do no work that the copy cannot.

### 4.7 Ranked borrow and avoid list

**Borrow (in order of fit):**
1. A single emphasised line in the headline, set in a second tone (maritime's two-tone split; inkbox's accent word). The proposal uses the two-tone split in ink and grey, with no coloured word.
2. The product or an instrument at scale directly under the headline (boxes' window; openrelay's instrument). The proposal puts the share track on the filed sheet at full width under the hero text.
3. A unit line under each price (boxes), and mono labels that name the job a plan serves (maritime). Both go into the pricing ledger.
4. A bordered rate table with mono tags for comparative numbers (openrelay). This becomes the plan ledger.
5. A callout inside a plan card that states the included scope (inkbox). Used only where the scope is decided. Otherwise nothing.
6. A terminal or instrument artifact beside a story (boxes about; openrelay about). This becomes the method diagram.
7. A trust page as one narrow long-form column (maritime security). This becomes the Method page.
8. Flat hairline sheets with no shadow (openrelay). This becomes the ledger sheet.

**Avoid:**
- Photography, mascots, undersea and other illustrative art, dotted textures, sticker shadows and glows.
- Looping motion beyond the one live indicator.
- Numbered labels that carry no sequence (boxes' values; the current "01" pricing rules).
- Lime, violet, neon and green-glow accents.
- Logo marquees and "Backed by Y Combinator" lines. LarkVision has no customers and no such backing to show, and it must not claim either.

---

## 5. The direction: The Decision Ledger

### 5.1 The idea in one sentence

A decision is a filed record. Passes are its entries, the weighted share is its total, the case against is the note in the margin, and the convergence line is drawn the way a ledger draws a total.

### 5.2 Why this, and not the others

The subject supplies the choices. A panel argues in passes until its weight converges. The outcome is filed. The owner reads the total and the note beside it. A ledger is where a careful person files a result they may have to defend later, so its grammar is the product's grammar: margin labels, rules, mono figures, a double rule under a total, and the note placed beside the entry it qualifies.

The four reference sites share one vocabulary: terminals, isometric racks, live status tables, lime, violet and green accents, and grotesk-plus-mono type. The ledger sits outside that set and is specific to this product. It also matches the committed world in `PRODUCT.md` (a neutral daylight ground, one accent, the map as the only dark surface) without repeating the cream-and-serif default that `PRODUCT.md` refuses.

### 5.3 The signature: the convergence rule

The one thing a customer must remember is the moment the argument converges. The convergence rule draws that moment on a part the app already has.

The app already has the **convergence tape**. It is headed "The Tape", its caption reads "weighted share per pass vs 0.80", and it shows each pass as a stacked bar of weight by position, one row per pass (P1, P2 and so on). A dashed warning line marks the threshold, with its value in a small chip. The tape stays unchanged. The rule is an overlay on it:

1. **The double rule.** Two 1px graphite lines, 3px apart, drawn over the tape's dashed line at the same position, using the same position formula. The gap between the two lines is filled with the surface colour, so the dashed line does not show through. The label reads "Converges at 0.80", and the value comes from the run's configuration (0.80 is the default in `PRODUCT.md`). The overlay shows only when the tape shows at least one pass, as the tape's own line does.
2. **Nothing else.** No trail, no total track and no second convergence visual anywhere in the product. The pass bars and their position marks stay as they are.

**States**, in the words the app already uses:
- Before the first pass: "Waiting for pass 1…" (the tape's own text).
- Converged: "Converged — the verdict is ready."
- Not converged: "Verdict ready — a plurality, not a consensus."
- A pass with no weight: "No position carries weight in this pass." (the tape's own text).
- Running: the bars arrive pass by pass, and no verdict line appears yet.

**Motion.** When a verdict files, the double rule draws from top to bottom over 560ms, once. Under reduced motion it appears complete at once.

**Text alternative.** The tape's caption states the threshold. A visually hidden sentence states the result, for example "Negative, share 0.82. Converged at 0.80 in pass 3." The Verdict view repeats the per-pass figures in a small table.

**Data.** The tape is built on the client (`convergenceSeries(run)` in `components/run/FlowView.tsx`), so the rule needs no backend change. One question is open (D8). The tape compares each pass on its own with the threshold, but the verdict is decided on the last two passes (`CONSENSUS_ROUNDS = 2` in `CLAUDE.md`). The overlay shows the threshold. It does not change which window decides the verdict.

**Where it appears.** In the Debate tab, below the floor card, where the tape already is. On the Verdict sheet, the same tape with the same overlay, beneath the share meter. Nowhere else.

**Why it is distinctive.** No reference site has a threshold object. The rule shows the product's own mechanism, drawn on the object that already carries it.

### 5.4 Principles

1. **The record is the proof.** Show the sheet, the tape and the margin note before any claim.
2. **One object leads each screen.** The homepage leads with the sheet. Runs leads with the ledger. The workspace leads with the map. No screen has two leads.
3. **Structure encodes truth.** A rule marks an entry. A double rule marks a total. Numbers appear only for a true sequence (the four stages) or a quantity (units, shares, dates, counts).
4. **One accent, one night.** Indigo ink carries action, focus and the live state. The map is the only dark surface.
5. **Words are design.** Plain verbs. The copy law binds every rendered string. Every empty state names one next step.
6. **A quality floor, not a polish pass.** WCAG 2.2 AA on every pair (§6). Everything works from the keyboard. Reduced motion renders the complete result.

### 5.5 The generic-default check, and what changed

The guidance this proposal was built against names defaults that appear regardless of subject. Each is tested below.

| Default | Test against this design | Result |
|---|---|---|
| Warm cream ground with a high-contrast serif display and a terracotta-family accent | The Quiet Room ground and display | **Refused.** Neutral ground `#F1F2EE`. Fraunces leaves the UI entirely; no serif reaches the interface. |
| Near-black ground with a neon or lime accent | A dark page with a bright accent | **Refused.** Night is the map and the closing band only. The accent is indigo ink. |
| Broadsheet: hairlines everywhere, zero radius | Zero radius on every control | **Not adopted.** 4px controls and 8px sheets keep fields and buttons legible on a phone. |
| Purple or violet gradient | A violet accent or a gradient | **Refused.** No gradient on any surface except the map's radial ramp. |
| Glass and blur | Translucent panels | **Refused.** No blur anywhere. |
| Centred hero with three stats | A centred heading and a stat strip | **Refused.** Left-aligned hero. No stat strip, because no real metric exists to show. |
| Four identical cards per section | A repeated card grid | **Refused.** Each section has one dominant object and a different shape. |
| Dashboard greeting and KPI tiles | A "Good morning" heading and tiles | **Refused.** No greeting. The page leads with the decision's state. |

**What changed between drafts** (the check was run on every draft):

- **Draft 1** kept the Quiet Room palette and proposed a stronger serif. **Revised:** the serif goes. It is the most common editorial default, and `PRODUCT.md` refuses it.
- **Draft 2** proposed a violet accent to echo the references. **Revised:** indigo ink. It is the colour of archival ledger ink, and it sits outside the reference set's accent families.
- **Draft 3** proposed a bare progress bar as the signature. **Revised:** the convergence rule, because a bare bar reads as a loading state. The tape carries a threshold and one bar per pass, so it means something.
- **Draft 4** kept shadowed sheets. **Revised:** a `--panel-line`-edged panel with no shadow, with the two shadows in the product reserved for overlays and one large modal. Shadows imply physical lift, and a ledger page is flat.
- **Draft 5** kept numbered pricing rules. **Revised:** ruled lines. Numbers stay only for the four stages, which are a true sequence.
- **Draft 6** added a trail and a total track beside the existing tape. **Revised:** both removed. The tape already draws each pass's weights against the threshold, so the new parts duplicated it.

### 5.6 Alternatives considered (not recommended)

| Alternative | For | Against | Measured |
|---|---|---|---|
| Keep the Quiet Room (bone, Fraunces, evergreen) | Already built; warm tone suits a reading room | It is the category default, and `PRODUCT.md` refuses it | evergreen on bone 8.65:1 |
| Oxblood ledger (accent `#7E2430`) | Warm, like binding cloth; strongest on paper | Reads as legal; close to the danger colour | white on oxblood 9.62:1 |
| Verdigris (accent `#2E6F62`) | Archival patina; distinct from blue | Teal reads as fintech; close to the current evergreen | white on verdigris 5.89:1 |
| Dark-first product | The night instrument as the whole product | Long reading sessions suffer; the verdict has to read and print as paper | not a page measurement |

**Recommended: indigo ink.** Oxblood is the owner's choice if warmth matters more than the ledger's cool precision (D2).

---

## 6. Tokens

### 6.1 Colour

The palette below is `DESIGN_PRODUCT_V7.html`'s `:root` block, resolved last-wins (the file redeclares some tokens; the final value is the one that renders). It is the palette this proposal now adopts. Contrast is computed with the WCAG 2.2 relative-luminance formula on the four light grounds.

**The light ladder.** Five surfaces, in the order a page stacks them.

| Name | Token | Hex | Role | On ground | On sheet |
|---|---|---|---|---|---|
| Ground | `--ground` | `#F1F2EE` | the page, behind every panel | — | — |
| Rail | `--rail` | `#E7EAE1` | the navigation plane, tinted one step under the page | — | — |
| Sheet | `--sheet` | `#FFFFFF` | panels, the reader, the card | — | — |
| Panel head | `--panel-head` | `#F3F4EE` | the tinted header and foot of a panel | — | — |
| Panel line | `--panel-line` | `#C7CDC2` | a panel's own edge, and the border between planes | 1.44:1 | 1.62:1 |
| Hairline | `--hairline` | `#DDE1D7` | rules **inside** a panel (decorative) | 1.18:1 | 1.33:1 |
| Record rule | `--record` | `#7C848F` | column heads, the reader's edge, instrument rules; **never text** | 3.36:1 | 3.78:1 |

**Ink.**

| Token | Hex | Role | On ground | On sheet | On panel head |
|---|---|---|---|---|---|
| `--graphite` | `#15171C` | headings, figures, primary text | 15.95:1 | 17.93:1 | 16.21:1 |
| `--graphite-hover` | `#2B3038` | the ink fill's hover | 14.05:1 | 15.74:1 | 14.28:1 |
| `--ink-2` | `#3B414B` | body text, table cells, panel foot notes | 9.14:1 | 10.28:1 | 9.29:1 |
| `--ink-3` | `#5B636E` | margin labels, kickers, captions, metadata | 5.41:1 | 6.08:1 | 5.50:1 |

**Accent.** One accent, indigo ink, and it is the same `#2D3F9C` this file already specified as D2.

| Token | Hex | Role | Contrast |
|---|---|---|---|
| `--accent` | `#2D3F9C` | the primary action's flat fill, text links, focus ring, the live dot, selected marks | 8.11:1 on ground · 9.12:1 on sheet · **white on it 9.12:1** |
| `--accent-hover` | `#24357F` | hover and press of an accent fill | white on it 11.11:1 |
| `--accent-soft` | `#E7EAF6` | a selected row's fill, the current plan's tint strip, the reader's hover | ink 14.94:1 · ink-2 8.56:1 · ink-3 5.06:1 on it |

**Night.** The map, the closing band, and nothing else.

| Token | Hex | Role | On night | On ramp top |
|---|---|---|---|---|
| `--night` | `#0F1320` | the dark surface | — | — |
| `--night-ramp` | `#1B2440` | the top of the map's one radial ramp | — | — |
| `--night-ink` | `#E7EAF1` | text on night | 15.37:1 | 12.70:1 |
| `--night-ink-2` | `#9EA8BC` | secondary text, connections | 7.74:1 | 6.40:1 |
| `--night-accent` | `#9DAAF2` | material entries, links and focus on night | 8.34:1 | 6.89:1 |
| `--night-rule` | `#27304A` | rules on night (decorative) | 1.42:1 | 1.17:1 |
| `--night-edge` | `#6B7694` | the map pane's own edge | 4.09:1 | 3.38:1 |

**The four positions** (frozen order POSITIVE, NEUTRAL, AMBIVALENT, NEGATIVE; each always shows symbol, colour and word):

| Position | Symbol | Light | On sheet | Night | On night |
|---|---|---|---|---|---|
| POSITIVE | up-pointing filled triangle ▲ | `--pos` `#1E7A4C` | 5.33:1 | `--pos-n` `#6FCF97` | 9.74:1 |
| NEUTRAL | square with a graticule ▦ | `--neu` `#5B636E` | 6.08:1 | `--neu-n` `#B8C2D0` | 10.28:1 |
| AMBIVALENT | dashed circle ◌ | `--amb` `#8A6410` | 5.37:1 | `--amb-n` `#D8B05E` | 9.07:1 |
| NEGATIVE | down-pointing filled triangle ▼ | `--neg` `#A3362B` | 6.73:1 | `--neg-n` `#F08A72` | 7.57:1 |

All four clear 4.5:1 on the sheet, on the ground and on `--accent-soft` (the weakest is POSITIVE at 4.44:1 on the soft fill, which is a 22px dot-plus-word mark, so it clears the 3:1 graphic floor with room). The NEGATIVE symbol is the built down-pointing triangle (D10).

**The five material layers.** V7 gives each kind of material its own hue for the map's entry dots and its legends. It is the one place a second and third colour family is allowed, because there the colour *is* the category.

| Layer | Light | On sheet | Night | On night |
|---|---|---|---|---|
| 1 | `--layer-1` `#4A5B8C` | 6.63:1 | `--layer-1-n` `#A9B8E8` | 9.44:1 |
| 2 | `--layer-2` `#5E6E4A` | 5.52:1 | `--layer-2-n` `#C3CE9B` | 11.13:1 |
| 3 | `--layer-3` `#7A4A5E` | 7.07:1 | `--layer-3-n` `#E0A9BE` | 9.33:1 |
| 4 | `--layer-4` `#3F6B6B` | 5.95:1 | `--layer-4-n` `#9FD3D3` | 11.22:1 |
| 5 | `--layer-5` `#6B5A3A` | 6.67:1 | `--layer-5-n` `#D6C199` | 10.53:1 |

**Danger** is `--neg` `#A3362B` (6.73:1 on sheet). A destructive action carries a stop icon and its own word, never colour alone.

**Usage rules.**
- Accent appears on: the primary action's flat fill, text links, the focus ring, the live dot, the current-row tint, and the verdict's share emphasis. Nothing else.
- Night appears on the map pane and the closing band only. Never on a card, a panel or a sheet.
- `--record` is the only structural grey that clears 3:1, so it is the only grey allowed to hold a boundary that means something. `--panel-line` and `--hairline` are decorative (1.62:1 and 1.33:1) and never carry meaning alone; every panel that matters also carries a heading.
- `--ink-3` is the only grey text. There is no fourth grey.
- No gradient on any page surface, and no gradient on the primary action (§6.9). No blur except the marketing header's backdrop, which V7 already ships. No coloured shadows.
- Every text pair clears 4.5:1 and every meaningful graphic clears 3:1, at the figures above.

### 6.2 Typography

**Families.** V7 ships two, and only two, for the interface: `--sans: "Archivo"` and `--mono: "JetBrains Mono"`. **The interface has no serif display face.** Georgia appears in exactly one place in the whole file — inside `.paper`, the rendered-document facsimile that stands in for an exported PDF — so a serif reaches the customer only as the *content* of an export, never as chrome. Fraunces therefore leaves the UI, which is what D1 already decided; V7 confirms it.

**The width axis.** `font-stretch` is used as a real axis, not decoration: V7 sets `105%` to `116%` across the display sizes. Archivo Variable's width axis is already installed and already imported, so this costs no dependency (§11.1).

**The measured scale.** Every value below is read from V7's stylesheet; `clamp()` values are reproduced verbatim so the two files cannot drift.

| Token | Size / line | Weight | Width | Tracking | Use |
|---|---|---|---|---|---|
| `hero-h1` | `clamp(40px, 4.9vw, 74px)` / 0.98 | 500 | 116% | −0.032em | the landing hero heading only |
| `display` | `clamp(30px, 2.4vw + 10px, 40px)` / 1.06 | 500 | 112% | −0.025em | page titles (`page-head h1`) |
| `display-sm` | `clamp(24px, 2.2vw, 32px)` / 1.08 | 500 | 110% | −0.025em | pricing and closing section headings |
| `headline` | `clamp(30px, 3.4vw, 52px)` / 1.02 | 500 | 112% | −0.03em | the closing band's heading |
| `title` | 26px / 32px | 600 | 105% | −0.01em | sheet and card titles |
| `sheet-q` | `clamp(22px, 1.6vw + 12px, 28px)` / 1.16 | 600 | 106% | −0.02em | the filed decision's question |
| `heading` | 20px / 28px | 600 | 100% | −0.01em | section sub-headings |
| `panel-title` | 14px / 20px | 600 | 100% | 0 | a panel's header title |
| `subhead` | 18px / 28px | 400 | 100% | 0 | section leads |
| `lead` | 16px / 26px | 400 | 100% | 0 | body prose, ≤ 62ch |
| `body-sm` | 14px / 22px | 400 | 100% | 0 | UI copy and table cells |
| `label` | 13px / 20px | 600 | 100% | 0 | form labels |
| `panel-kicker` | JetBrains Mono 10px / 16px | 500 | — | +0.10em, uppercase | a panel's kicker |
| `margin-label` | JetBrains Mono 11px / 16px | 500 | — | +0.08em, uppercase | margin labels, eyebrows, column heads |
| `figure` | JetBrains Mono 13px / 20px | 400 | — | 0 | identifiers, dates, counts |
| `fig-sm` | JetBrains Mono 11px / 16px | 400 | — | 0 | captions and notes beside a figure |
| `numeral` | `clamp(44px, 4.4vw, 58px)` / 1.00 | 500 | 112% | −0.04em | the verdict's share |
| `numeral-sm` | `clamp(34px, 3.4vw, 52px)` / 1.00 | 500 | 110% | −0.04em | a price in a plan card |

**Rules.**
- Any measurement is set in JetBrains Mono with `font-variant-numeric: tabular-nums`. That covers dates, counts, shares, units, passes, prices and identifiers.
- Weights are 400, 500 and 600. There is no 700, and no italic.
- Capitals appear only in `margin-label`, `panel-kicker` and table heads, always with their tracking.
- Measures: verdict prose ≤ 62ch; a panel foot note ≤ 66ch; a hero heading ≤ 15ch; a `sheet-q` ≤ 36ch; form help ≤ 40ch.
- The type floor is 10px, and it is used only for a `panel-kicker` and a table head. Body text never goes below 14px.

### 6.3 Space, grid and containers

- **Spacing scale:** 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 28, 32, 40, 44, 48, 56, 64, 72, 80, 88, 96. It is a wider set than a strict 8-point ramp, and that is deliberate: 14px is the page-stack gap and 18px the panel padding, and both are load-bearing.
- **Containers.** The marketing shell is `.site-wrap` at `min(1280px, 100% - 96px)`. The app's work area is `.content` at `max-width: 1400px`, padding `32px 40px 96px`. The Method page and the auth column are narrow by design: `.method` at `min(704px, 100%)`, `.signin-sheet` at `min(430px, 100vw - 32px)`.
- **Stacking.** A page's parts are a `.page-stack`: a single column with a `14px` gap. Panels are its children, always full width, and the gap is the only thing that separates them. There is no card grid on any app page except Plans, which is a three-up `.plans` grid that collapses to one column below `lg`.
- **Two-column page layouts.** Verdict is `minmax(0,1fr) 296–336px`. Documents is `minmax(0,1fr) 24px var(--reader-w, 560px)` with the reader closed by default. Auth is `minmax(0,430px) minmax(0,1fr)`. The workspace is `44% | 8px divider | 1fr`. Everything else is one column.
- **Rhythm.** `.site-section` is 80px of vertical padding on desktop, 60px at `md`, 44px on phone, with a `--hairline` top rule and the first section's rule removed. Panel internals are 18px; a panel head is 46px minimum.
- **Rail and bar.** The rail is `280px`, collapsing to `76px`. The utility bar and the workspace bar are both `60px` (`--topbar-h`), 56px on phone.

### 6.4 Radius

| Value | Where |
|---|---|
| **0** | rules, the tape and its tracks, record rows, the ledger table, `.paper` |
| **3px** | chips, keyboard hints |
| **4px** (`--r-1`) | buttons, inputs, selects, the segmented control |
| **8px** (`--r-2`) | sheets, cards, the reader, the map pane |
| **10px** | every panel — the app's principal object |
| **999px** | the live dot only |

The one value that changed from the previous draft is the panel: a page is not built from 8px cards, it is built from 10px panels. The difference is small and it is the difference between "a card" and "a section of a document".

### 6.5 Surfaces, borders and elevation

V7's grammar is four nested planes. It is the clearest thing in the file and the whole layout follows from it.

| Plane | It declares itself with | It never has |
|---|---|---|
| 1 · Ground | `--ground`, the page fill | a border, a shadow |
| 2 · Rail | `--rail`, one step tinted under the page, with a `--panel-line` right edge | a shadow, a radius |
| 3 · Sheet / Panel | `--sheet` paper white, a **1px `--panel-line`** edge, a **10px** radius | a shadow |
| 4 · Panel head / foot | `--panel-head` `#F3F4EE`, a `--panel-line` divider from the body | a radius of its own; it is clipped by the panel |
| Overlay | `.dlg`, `.popover`, the palette: `--overlay-shadow: 0 16px 40px rgba(22,24,29,.18)` and a `--panel-line` edge | a second shadow, a second layer |
| Map pane | `--night` fill with the one radial ramp, an 8px radius, `--night-edge` | a light neighbour |
| Total (a double rule) | two 1px `--graphite` rules, 3px apart | a single heavy rule |

**The panel is the unit of layout.** Every app page is a `.page-stack` of `.panel`s, and each panel is exactly three parts:

```
┌──────────────────────────────────────────────────────────────┐
│ panel-head   --panel-head fill, 46px min, 1px --panel-line   │  kicker · title … actions
├──────────────────────────────────────────────────────────────┤
│ panel-body   18px padding (or 0 when it holds a record)      │  the content
├──────────────────────────────────────────────────────────────┤
│ panel-foot   --panel-head fill, 11px 18px, top --panel-line  │  a note, a count, a total
└──────────────────────────────────────────────────────────────┘
```

Three rules follow, and they replace the previous draft's "a sheet never gets a shadow / a record never gets a box":
1. **A panel is drawn, never floated.** No panel carries a shadow. The only shadows in the product belong to an overlay, a popover or a dialog.
2. **A panel's head is tinted, not ruled.** The separation between head and body is a fill change plus a 1px line, never a heavier rule, and never a coloured bar.
3. **A record inside a panel is flush.** `.panel-body--flush` holds a `.record` whose rows are separated by `--hairline` and whose `.record-head` is a `--panel-head` fill. The record is not boxed inside the box.

Two shadows are permitted in total: `--overlay-shadow` for a dialog, popover or palette, and `0 24px 72px rgba(22,24,29,.3)` for the largest modal. Nothing else in the file has a shadow except one `inset 0 0 0 1px` language, which is a border written as a shadow and is read as a border.

### 6.6 Motion

V7's motion grammar, reproduced exactly. It is kept, and it is the whole grammar.

- **Durations:** `--t-state: 120ms`, `--t-enter: 180ms`, `--t-layout: 240ms`, `--t-draw: 560ms`. Easing, one curve: `--ease: cubic-bezier(0.2, 0, 0, 1)`.
- **What each duration is for.** `state` is a hover, a press, a toggle, a chip. `enter` is an overlay, a popover, a toast. `layout` is the rail collapse and the map's minimise — a width change, never a height jump. `draw` is the convergence rule drawing once (§5.3), and nothing else.
- **The authored moment.** The convergence rule draws top to bottom over 560ms, once, when a verdict files. Nothing else in the product is theatrical.
- **Loops.** One only: the live dot's opacity breathes at 1.6s, and only while a decision is running.
- **Prohibited.** Marquees, sway, keyframe loops on marketing pages, parallax, scroll-scrubbing, and any animation that answers nothing.
- **Reduced motion.** `@media (prefers-reduced-motion: reduce)` sets every duration to 0.01ms and removes the breathe loop. The convergence rule appears complete. A new map entry fades in instead of blooming.

### 6.7 Iconography and imagery

- **One icon set, one weight, one size:** 16px inline with 14px labels, and 20px where an icon stands alone. V7 uses a single sprite (`<symbol id="i-…">`) referenced by `<use href>`, so every icon is one path and there is no icon font.
- The four position symbols are authored SVG in a second sprite (`#p-POSITIVE` … `#p-NEGATIVE`), 12–14px, and they are the only marks that carry colour.
- **No emoji, no mascots, no illustrations of robots, no photography, and no decorative art.** The map and the filed sheet are the only visual assets the product makes. The one 「paper」 facsimile is content, not decoration.
- Every icon that stands alone carries an `aria-label`; every icon beside a word is `aria-hidden="true"`.

### 6.8 Focus and states

All of these are V7's, and all of them are required on every interactive element.

- **Focus:** a 2px `--accent` ring with a 2px offset, `:focus-visible` only — never `:focus`, so a mouse click does not ring. On night, the ring is `--night-ink` (15.37:1). A record row takes the ring *inside* its edge (`outline-offset: -2px`) so the ring cannot be clipped by the panel.
- **Hover:** an accent fill darkens to `--accent-hover`; a secondary fill takes `--accent-soft`; a row takes `--accent-soft`; a link takes `--accent`. A ghost button on night takes `rgba(255,255,255,.08)`.
- **Pressed:** the hover value, with no scale transform and no translate.
- **Disabled:** `--ink-3` label, a `--panel-line` edge, no fill, `cursor: not-allowed`. The reason appears as text beside the control — never a faded control alone.
- **Invalid field:** the field's 1.5px bottom rule turns `--neg` at 2px, a `--neg` alert icon sits beside the label, and the message is `--ink-2` with `role="alert"`. The message says what to do ("At least 8 characters"), not what went wrong.
- **Busy:** the control is disabled and its label becomes the progress ("Creating your account…"), with `aria-busy="true"` on the form. No spinner for a wait under 200ms.
- **Selected:** `aria-pressed="true"` or `aria-current="page"`, an `--accent-soft` fill and, in the rail, a 2px `--accent` left rule. Colour is never the only signal.

### 6.9 Gradients: the explicit rule

This section exists because the previous draft left the question open. The answer, measured from V7 block by block:

**The product has exactly one gradient, and it is on the map.**

```
background: radial-gradient(120% 100% at 50% 0%, var(--night-ramp) 0%, var(--night) 72%);
```

That is the night instrument's depth — `#1B2440` at the top edge falling to `#0F1320` over 72% of the height. It appears on the map pane and nowhere else.

**Three other `linear-gradient(...)` declarations in the file are not gradients.** They are flat single-colour fills used as a CSS utility, and they must not be read as a ramp:

| Declaration | What it actually is |
|---|---|
| `linear-gradient(var(--record), var(--record)) center / 1px 100% no-repeat` | a **1px vertical hairline** — the workspace divider and the document split, drawn as a background so it can be positioned |
| `linear-gradient(var(--accent-soft), var(--accent-soft)) top / 100% 92px no-repeat` | a **flat 92px tint strip** at the top of the current plan card (76px, 80px, 84px and 96px variants elsewhere) |
| `linear-gradient(45deg, transparent 49%, var(--ink-2) 50%), linear-gradient(135deg, var(--ink-2) 50%, transparent 51%)` | the **two strokes of a select's chevron** |

**The primary action is flat.** `--btn-primary` is `background: var(--accent)` and its hover is `background: var(--accent-hover)`. There is no ramp on it. This confirms what the shipped `frontend/src/index.css` already asserts in a comment — "a flat evergreen fill, never a gradient (§4.8 rule 2)" — and it **overrules** `docs/DESIGN_SPEC.md` §3, which specifies a vertical `#8F3F97 → #823A86 → #6E2F74` ramp on the primary action. That ramp was never built, it is not in V7, and it is hereby withdrawn.

**The rule.**

1. **A control is flat.** A button, a field, a chip, a row, a tab is one solid colour in every state. No ramp, no gloss, no inner shadow.
2. **A large dark instrument may have depth.** The map is the only such instrument, and its radial ramp is the only gradient in the product.
3. **A `linear-gradient` may be used as a positioning utility** for a 1px rule or a flat tint strip, provided both stops are the same colour. If the two stops differ, it is a gradient and rule 1 or 2 applies.
4. **Nothing else.** No gradient text, no gradient border, no mesh, no conic sweep, no glow.

---

## 7. Components

Each component lists its anatomy, sizes, variants and states. Shared components are composed, not forked. The implementation map is in §11.

### 7.1 Button

| Variant | Appearance | Use |
|---|---|---|
| Primary | indigo fill, sheet-white label, 4px radius, no shadow; 40px in the app, 48px on marketing | the one action of a surface |
| Secondary | sheet fill, a 1px record-rule border, graphite label; hover takes the accent-soft fill | any other action |
| Ghost | mono label, graphite text, underlined in the record rule; hover takes accent for text and the underline | measurements and inline links |
| Danger | sheet fill, a 1px brick border, brick label with a stop icon | destructive actions only |

- Labels name the action and its object, in the active voice: "Start your first decision", "Export document", "Try again".
- Text links are at least 44px tall, with the label centred vertically.
- Each surface has one primary. If a second action is needed, it is secondary.

### 7.2 Field

- A label sits above the field in `label` type (14/22 at 600).
- The field has no box and no fill. Its boundary is a 1.5px graphite bottom rule, which clears 3:1 easily. The field is 44px tall.
- Focus turns the rule to the accent at 2px.
- Help text sits below in `body-sm` at ink-3. It is at most 36ch.
- Invalid: a brick rule, a brick alert icon and the message in ink-2 with `role="alert"`. The message says what to do ("At least 8 characters"), not what went wrong.
- Select, number and textarea share the same baseline.

### 7.3 Status chip

- 4px radius, a 1px ink-3 outline, mono 11px uppercase, padding 2px by 8px.
- States, each with a symbol and a word: Complete, Converged, Deliberating (accent dot, breathing), Queued, Failed, Interrupted, Read, Not yet.
- Failed and Interrupted runs still open. The chip says so in its word, and the row remains a link.

### 7.4 Position mark

- The symbol at 12px, then the word in mono 12px uppercase, ink.
- The four symbols and their colours are in §6.1.
- The word is always present. The symbol is always present. The colour is never the only signal.

### 7.5 The convergence rule

Specified in §5.3. The rule is `ConvergenceTape`, used unchanged, with a double-rule overlay (new). It appears in two places: the Debate tab, below the floor card, and the Verdict sheet, beneath the share meter.

- **Position.** The overlay uses the same position formula as the tape's threshold line, so the two agree at any width. It follows the tape's column width.
- **Condition.** The overlay shows only when the tape shows at least one pass.
- **Motion.** Once, when the verdict files (§6.6). Under reduced motion it shows complete.
- **Text alternative.** The tape's caption, and the visually hidden result sentence (§5.3). The Verdict view's table repeats the per-pass figures.
- **Not used in Runs.** The Runs list shows the outcome as a symbol, a word and a share. It carries no convergence visual.

### 7.6 Filed sheet

The verdict object. It is the same component on the homepage, on sign-up and on the Verdict page, so what the visitor sees is what the owner files.

```
┌──────────────────────────────────────────────────────────────┐
│ THE DECISION                                  WORKED EXAMPLE │   margin label · chip (examples only)
│                                                              │
│ Should Ridgeline Coffee open a second location on Mill St?   │   title, Archivo expanded, 28px
│                                                              │
│ ▼ NEGATIVE                                          0.82     │   position · numeral
│ ─────────────────────────────────────────────────────────────│   hairline
│ [the tape, with the 0.80 double rule]                │   §5.3
│ ═════════════════════════════════════════════════════════════│   double rule: a total
│ THE CASE AGAINST                                             │   margin label
│ If the grease-trap work lands on time, the economics hold.   │   dissent block: 3px graphite left rule
│                                                              │
│ SOURCES                                                      │
│ 1 Mill Street lease, p. 4    2 Alder Lane lease, p. 2        │   exhibits, mono
└──────────────────────────────────────────────────────────────┘
```

- **Surface:** sheet white, hairline edge, 8px radius, 32px padding. No shadow.
- **The case against** is a dissent block: a 3px graphite left rule, a margin label, and the text in ink-2. It is not coloured. Its weight comes from its rule and its position in the sheet, below the total.
- **Sources** are exhibits: numbered in mono, with the document name and the location. An exhibit number is a real ordinal, not decoration.
- **The Worked example chip** appears on every authored example, on the homepage and on sign-up, and nowhere else. A real verdict never carries it.

### 7.7 Ledger record row

- Rows are 48px for documents and 56px for runs. A 1px record rule sits above the first row and between rows. There is no box around the list.
- A header row holds margin labels (mono 11px uppercase, ink-3) with a record rule below.
- Hover fills the row with accent-soft. The whole row is the link. Focus shows the accent ring inside the row.
- Columns are set per page (§8).

### 7.8 Run row

- Question (`heading`, 16/22 at 600) · outcome (position symbol and word, or "Still arguing") · status chip · date (mono) · passes (mono) · material (`body-sm`).
- A running row carries the accent live dot. It is the only accent on that row.
- A failed or interrupted row still opens its decision. The status chip says why.

### 7.9 Document row and reader

- **Row (48px):** name (`body-sm` at 500), material (`body-sm`), added (mono), and read state (a dot and a word: "Read" in ink, "Not yet" in ink-3).
- **Reader:** an overlay sheet of 480px on the right, with the overlay shadow. Header 64px: the document name, the mono meta line (added, size) and a 44px close control. Body in `body` at 62ch maximum.
- **Keyboard:** Escape closes the reader and returns focus to the row that opened it.
- **Loading** shows a skeleton that matches the body. **Failure** shows a sentence that names what failed, and "Try again".

### 7.10 Plan ledger and the Enterprise band

- **Plan ledger:** four plan cards (`.plan-option`), Free, Starter, Studio and Enterprise, then the same plans row by row (`.cmp-table`). The Free plan **is** a column on `/pricing`, because that page is where the free tier is named (§8.3). The signed-in Billing panel keeps three (`.plans-panel`), because a paying account moves between paid plans. The header holds the plan name and its price at `numeral-sm`. Rows: units per month (mono), and the rule lines for how units are counted. Rows for panel size and passes appear only when they come from plan configuration (§3.5, decision D6).
- **Currency** is a small segmented control in the table's header row. It is never above the plans.
- **Recommended mark:** not shown until the owner decides which plan is marked (D6). The current plan is marked three ways: a "Your plan" chip, an `--accent-soft` strip at the top of the card, and a replaced action.
- **Enterprise band:** a ruled block beneath the table, not a card. It holds "Enterprise", a sentence about custom volume, one primary action ("Talk to the founder") and a mono note on billing.

### 7.11 Rail and bottom bar

- **Rail (≥ `lg`, 280px):** the wordmark at the top (glyph and "LarkVision", Archivo 600, 18px), a collapse toggle, then a full-width primary "New decision". Then the nav: **Documents, Runs, Verdict**, each with a 16px icon, a 14px label and a mono count on the right. The active item takes `--graphite` at weight 600 and a 2px `--accent` left rule, with no tinted fill. The foot holds the account (initials in a 32px ruled square) and "Sign out". The plane is `--rail`, one step tinted under the page, with a `--panel-line` right edge.
- **Rail (collapsed, 76px):** icons only, the wordmark's word hidden, the labels kept for screen readers, "New decision" a 40px square. The width transition is `--t-layout` 240ms.
- **Below `lg` the rail is hidden** (`display: none`) in favour of a bottom bar of 64px, four items: New decision, Documents, Runs, Verdict. Labels stay visible at 12px. The active item uses the accent rule on its top edge. V7 hides the rail rather than shrinking it to 76px.
- **Landing:** on sign-in, a new account lands on Documents, an account with material but no filed answer on Runs, and an account with a filed answer on Verdict. The rail names all three either way.

### 7.12 Workspace top bar and divider

- **Top bar (56px):** the diamond glyph and "LarkVision" (a link back to Runs), "Close decision" (×, 44px), the question (`heading`, one line, truncated), the status chip, and the elapsed time in mono.
- **Stage words:** between the question and the pass counter, the three words from `workspaceSteps.ts`: Material · Question · Panel. The current stage is set in ink and the others in ink-3. "Your material" and "The map" both light Material, because both are part of the material. "Your question" lights Question, and the run lights Panel.
- **Pass counter:** "PASS 2 OF 4" in mono, beside the elapsed time.
- **Divider (8px):** `role="separator"`, `aria-orientation="vertical"`, and `aria-valuenow` set to the map's percentage. Drag between 25% and 75%, with a 320px minimum on the map. Keyboard: Left and Right move 16px, Home sets 25%, End sets 75%, and a double-click resets to 50%. The ratio is stored per decision. The divider already exists in the build (`SplitDivider`), so phase 5 checks it against this spec rather than adding a control.

### 7.13 Map pane

- Night fill with the radial ramp, 8px radius, the night edge and the map shadow.
- **Layer toggles:** All, Material, Experts, Opinions, Connections. Each is a ghost mono button with a 44px hit area and `aria-pressed`.
- **Counts strip:** mono text that gives counts by kind, the busiest entries and the current pass. It is the map's text alternative, and it is always present.
- **Minimise (48px strip) and expand:** both keep the canvas mounted. Minimise collapses to the strip. Expand gives the map the whole region.
- **Entries:** 7px nodes. Material uses night-accent. Experts use night-ink. Opinions use the position colours on night (§6.1). Connections use night-ink-2. A new entry blooms once.

### 7.14 Drawer (entry details)

- An overlay sheet, 560px wide, with the overlay shadow and a hairline.
- Header: the entry's name, its kind in a margin label, and a close control.
- Ruled blocks, each with a margin label: "From" (the source document and location), "Referenced by" (the experts who cite it, with passes) and "Argued as" (position symbol, word, strength, and the quoted line).
- Escape closes it. Focus returns to the map root.

### 7.15 Toast

- A sheet with a hairline, one line, an icon and a word. It is shown for four seconds.
- When an action is reversible, the toast offers "Undo". A toast never carries a second message.

### 7.16 Empty, loading and error states

- **Empty:** a dashed record rule around one sentence and one action. Examples are in §9.
- **Loading:** a skeleton that matches the shape it replaces. No spinner appears for a wait under 200ms.
- **Error:** a sentence that says what failed, then a "Try again" button. An error never leaves the area blank.
- **Honest state:** a run still in progress says so. A section that cannot show something yet says that, and implies no feature it lacks.

---

## 8. Pages

Every page below is specified against `DESIGN_PRODUCT_V7.html`, section by section, in V7's own order. Where this file and V7 disagree, **V7 wins and this file is corrected** — that is the whole point of this revision. Wireframes are at 1280px. They show structure and proportion, not final pixels.

Two shells carry the ten pages:

| Shell | Pages | Its planes |
|---|---|---|
| **Site** (`#site`) | Landing, Pricing, Method, Sign up, Sign in | `--ground` page · `.site-head` sticky 68px bar · `.site-wrap` 1280px column · `.site-foot` |
| **App** (`.app`) | Verdict, Documents, Runs, Billing, Account | grid `280px \| 1fr` · plane 1 rail · plane 2 `--topbar-h` 60px bar · plane 3 `.content` at 1400px |
| **Workspace** (`.app` with `body.v5`, no rail) | Decision (`/new`, `/runs/:id`) | `44% \| 8px divider \| 1fr`, `--night` map beside a `--sheet` flow |

The site pages and the app pages are switched by `[hidden]`, not by routing, and both shells share one token set. A visitor never crosses a seam, because the sign-up page and the Verdict page are the same paper, the same rules and the same type.

### 8.1 Sign up and sign in (`/auth/signup`, `/auth/signin`)

V7's two auth pages are the same component with different copy, and the aside is the filed sheet.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ◆ LarkVision          How it works   Pricing   Method      Sign in [Start free] │  .site-head, 68px
├──────────────────────────────────────────────────────────────────────────────┤
│ CREATE AN ACCOUNT                          │ ┌────────────────────────────┐ │
│                                            │ │ WHAT YOU GET   Worked example│ │
│ Start your first decision.                 │ │ ▼ NEGATIVE           0.82   │ │
│ An email and a password. No more. The      │ │ share of weight            │ │
│ first decisions are free, and no card is   │ │ Should the Mill Street     │ │
│ asked for.                                 │ │ lease be renewed?          │ │
│                                            │ │ [the tape, 0.80 rule]      │ │
│ Your name                                  │ │ THE CASE AGAINST           │ │
│ ________________________________________   │ │ If the grease-trap work    │ │
│ Email                                      │ │ lands on time…             │ │
│ ________________________________________   │ └────────────────────────────┘ │
│ Password                                   │ AI-generated perspectives,     │
│ ________________________________________   │ not human advisers. Every      │
│ At least 8 characters.                     │ verdict shows the case against │
│ [ ] I agree to the Terms and the Privacy   │ and the passage each claim     │
│     Policy, and I am 18 or older.          │ rests on.                      │
│ [ Create account ]                         │                                │
│ Free to start · No card. This preview      │                                │
│ creates the account on this page.          │                                │
│ Already have an account? Sign in           │                                │
└──────────────────────────────────────────────────────────────────────────────┘
   .auth-col  minmax(0,430px)          .auth-aside  minmax(0,1fr), 72px gap
```

- **Layout.** `.auth-grid` is `minmax(0,430px) minmax(0,1fr)` with a 72px gap, `64px` top and `88px` bottom padding. Below `lg` it is one column with a 44px gap, and the aside follows the form, so the worked example is the last thing on the page.
- **The aside is the filed sheet** (§7.6), `max-width: 460px`, at `padding-top: 36px`. It is the same object the verdict page files. On sign-up its label is "What you get"; on sign-in its label is "Filed 12 Oct 2026" and its note is "Mill Street · Alder Lane", so the two pages show the same object from two angles: what it is worth, and what a filed one looks like.
- **The aside's own footnote** is `fig` in `--ink-3`, at most 44ch, and it carries the honesty line: "AI-generated perspectives, not human advisers. Every verdict shows the case against and the passage each claim rests on." The sign-in variant carries "Worked example. Names and figures illustrative." This line is part of the page, not a disclaimer bolted on.
- **Fields** use the ledger baseline (§7.2): no box, no fill, a 1.5px `--graphite` bottom rule, `--r-1` on nothing because a field is not a box. Focus turns the rule to 2px `--accent`. Height 44px on phone.
- **Sign up's five parts**, in order: the margin label ("Create an account"), the `h1` ("Start your first decision."), the lead, the form, and the "Already have an account? Sign in" line. The form is name, email, password, an agreement checkbox, one primary action, and a `fig-sm` note.
- **Sign in's four parts:** the margin label, the `h1` ("Your decisions, your material and your verdicts."), the lead ("Pick up where the panel left off. The record is where you filed it."), the form (email, password, primary, note), then "No account yet? Create one".
- **The password rule** is stated under the field in `hint` at most 40ch: "At least 8 characters." It is stated before the mistake, not after.
- **States.** Focus: a 2px accent bottom rule. Invalid: a 2px `--neg` bottom rule, a `--neg` icon, the reason in `--ink-2` with `role="alert"`, and the mark recomputed from the current value so an autofill clears it. Submitting: fields disabled, the button reads "Creating your account…", the form is `aria-busy="true"`. Success moves to the landing rule (§8.12). Failure shows a sentence above the form and keeps every typed value.
- **Keys and labels.** Every field has a real `<label for>`, and `autocomplete` is set: `name`, `email`, `new-password` on sign-up and `username`, `current-password` on sign-in.
- **Copy** is V7's copy, verbatim, and it obeys §9.2.

### 8.2 Landing (`/`): ten sections, in this order

The landing page's job is the feeling in one sentence: a panel argues the decision and shows its work. V7 gives it a hero, eight `.site-section`s that each carry a margin label, and a closing night band. Every section earns its place by showing something, not by describing it.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ◆ LarkVision          How it works   Pricing   Method      Sign in [Start free] │  1 · site-head
├──────────────────────────────────────────────────────────────────────────────┤
│ THE DECISION                 │ ┌──────────────────────────────────────────┐ │  2 · hero
│                              │ │ THE DECISION              Worked example │ │
│ The decision you             │ │ Should the Mill Street lease be renewed? │ │
│ can't look up.               │ │ ▼ NEGATIVE                         0.82  │ │
│                              │ │ share of weight                          │ │
│ A panel reads the material   │ │ P1 ▇▇▇▇  P2 ▇▇▇▇▇  P3 ▇▇▇▇▇▇ ┃ 0.80   │ │
│ and argues the question.     │ │ ══════════ converges at 0.80             │ │
│ [ Start your first decision ]│ │ THE CASE AGAINST  If the work lands …     │ │
│ See a filed decision         │ └──────────────────────────────────────────┘ │
│                              │ Worked example. Names and figures illustrative│
├──────────────────────────────┴──────────────────────────────────────────────┤
│ 3 · THE PROBLEM    The argument is the thing you're missing.                  │
├──────────────────────────────────────────────────────────────────────────────┤
│ 4 · HOW IT WORKS   Four steps, and the last one is a document.                │
├──────────────────────────────────────────────────────────────────────────────┤
│ 5 · THE DIFFERENCE A conversation gives you a feeling. A filed decision       │
│                     gives you a record.                                      │
├──────────────────────────────────────────────────────────────────────────────┤
│ 6 · WHAT YOU GET   Four things, and none of them is a summary.                │
├──────────────────────────────────────────────────────────────────────────────┤
│ 7 · WHY YOU CAN    Nothing here asks to be trusted.                          │
│     CHECK IT                                                                 │
├──────────────────────────────────────────────────────────────────────────────┤
│ 8 · WHAT IT DOES, AND WHAT IT DOES NOT DO   It is a panel, not an adviser.    │
├──────────────────────────────────────────────────────────────────────────────┤
│ 9 · USE CASES      Four decisions people bring.                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ 10 · QUESTIONS     The ones asked before signing up.                         │
├──────────────────────────────────────────────────────────────────────────────┤
│ ███ NIGHT BAND  Bring a question you can't look up.  [ Start your first … ]  │
├──────────────────────────────────────────────────────────────────────────────┤
│ The product · The record · Your account · Contact        legal entity line    │
└──────────────────────────────────────────────────────────────────────────────┘
```

**The sections, in order, each with its margin label and its `h2` verbatim from V7:**

| # | Margin label | `h2` | What it shows |
|---|---|---|---|
| 2 | The decision | *the `h1`* "The decision you can't look up." | the hero: the filed sheet with its tape, one primary and one ghost action |
| 3 | The problem | "The argument is the thing you're missing." | three ruled statements from the current copy |
| 4 | How it works | "Four steps, and the last one is a document." | four stages, `h3`: Add the material · Ask the question · The panel argues · The answer is filed |
| 5 | The difference | "A conversation gives you a feeling. A filed decision gives you a record." | two columns, `h3` "A conversation" and "A filed decision" |
| 6 | What you get | "Four things, and none of them is a summary." | the sheet annotated part by part (§7.6) |
| 7 | Why you can check it | "Nothing here asks to be trusted." | the four promises, each linked to the thing itself |
| 8 | What it does, and what it does not do | "It is a panel, not an adviser." | `h3` "It does three things" beside `h3` "It does not three things" |
| 9 | Use cases | "Four decisions people bring." | four real decisions, ruled, not four cards |
| 10 | Questions | "The ones asked before signing up." | `<details>` questions, answers in `body` |
| — | — | "Bring a question you can't look up." | `.close-band`, `--night`, the only dark band on the page |

**Structure.**
- `.site-section` is `80px` of vertical padding with a `--hairline` top rule and the first section's rule removed; `60px` at `md` and `44px` on phone. The rule is what makes ten sections read as one document instead of ten stripes.
- Each section is a two-part grid: a margin you can read down, and one dominant object. Section 5 is two columns because it compares two things; section 8 is two columns because it contrasts two things. Nothing else is a two-up, and **no section is four identical cards.**
- `.hero-grid` is `minmax(0,1.02fr) minmax(340px,.92fr)` with a 64px gap. `.hero-h1` is `clamp(40px,4.9vw,74px)/0.98` at weight 500, `font-stretch: 116%`, `-0.032em`, `max-width: 15ch`. The sheet is the one object that leads the screen.

**Rules for the landing page.**
1. **Every number is real and measured, or it is not shown.** No logo, testimonial, benchmark, "Backed by", user count or award appears anywhere on the page.
2. **Examples carry the Worked example label**, always, and a real verdict never does.
3. **Bands are not alternated by colour.** The rhythm comes from the margin label and the change of object. The only colour break on the page is the closing night band.
4. **One dark surface**, the close band. No other section is tinted.
5. **The Method page is linked from the header and the footer**, because section 7's promises and section 4's steps both point at it.

### 8.3 Pricing (`/pricing`)

V7's pricing page is four parts, ported from V3 and rebuilt on this file's tokens: the thesis and the four cards, the same plans row by row, what every paid plan includes, Enterprise as a ruled split, and the questions.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ◆ LarkVision          How it works   Pricing   Method      Sign in [Start free] │
├──────────────────────────────────────────────────────────────────────────────┤
│ PRICING                                            [ USD │ INR ]           │  .pricing-head
│ Pay for the material. And the arguments.                                     │
│ One unit pool per month, sized by how much material the panel reads and how   │
│ many passes it argues. No seats. No per-question invoice.                    │
├──────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────┬──────────┬──────────┬──────────┐                              │  1 · four cards
│  │ Free     │ Starter  │ Studio   │Enterprise│                              │
│  │ $0       │ $10      │ $20      │ Custom   │                              │
│  │ 1,000    │ 8,000    │ 16,000   │ Custom   │                              │
│  │ [ Start ]│ [Choose ]│ [Choose ]│ [Talk ]  │  ← all four at one height     │
│  └──────────┴──────────┴──────────┴──────────┘                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ 2 · Compare the plans                                                        │
│  PLAN              Free    Starter   Studio    Enterprise                     │
│  Units per month   1,000   8,000     16,000    Custom                         │
│  Experts a panel   10      [config]  [config]  [config]                       │
│  Passes a decision 3       [config]  [config]  [config]                       │
├──────────────────────────────────────────────────────────────────────────────┤
│ 3 · Every paid plan includes      (ruled rows, not a grid of icons)           │
├──────────────────────────────────────────────────────────────────────────────┤
│ 4 · ENTERPRISE BAND  #enterprise-band                                        │
│     More than 16,000 units a month, or the same panel against material that   │
│     keeps growing.  [ Talk to the founder ]      Monthly billing · INR or USD │
├──────────────────────────────────────────────────────────────────────────────┤
│ 5 · About the plans                                                          │
│     <details> What is a unit? · Do I pay per question? · Can I export or      │
│     delete my material? · Which currency do I pay in? · What does the free    │
│     tier include?                                                            │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Four plans, and Free is now one of them.** This is a reversal of the previous draft, and it is V7's decision: the plans page is where the free tier is *named*, so it gets a column. The signed-in Billing panel keeps its own three-tier ledger (§8.7) and does not repeat the free tier.
- **`[config]` cells come from plan configuration**, never from constants. The hard-coded 12 and 4 are removed (D6), so no plan shows a value it does not have.
- **The four cards are one component** (`.plan-option`): name, price (`numeral-sm`), a units line, three `plan-facts` rows, and the action. The action sits at `margin-top: auto`, so all four buttons land on one line. A spacer that absorbed free space is set to `display: none`, and `.plan-desc` has a `min-height` — this alignment was a real bug and is now a rule.
- **`.cmp-table` is the row-by-row view**, `min-width: 720px` on desktop, with a `--graphite` top rule and a `--hairline` between rows. Below `lg` it **stacks** into one ruled block per plan; it never scrolls horizontally.
- **Currency is a segmented control** (`.seg`) in the pricing head, above the cards — it is never a select, never a dropdown, and it never sits inside the table.
- **Enterprise is a ruled split**, `#enterprise-band`, not a fifth card.
- **Recommended:** no plan is marked until D6 is answered.
- **Every price is traceable** to `settings.plan_*_price_inr` / `_usd` (§11.1). A price that appears nowhere in configuration does not appear on the page.

### 8.4 Method (`/method`): the page for a product that checks itself

This page answers the question an owner asks before trusting a verdict: how was it made? It replaces the about-page pattern of the references, because this product has no founders' story to tell. Its authority is the mechanism.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ◆ LarkVision          How it works   Pricing   Method      Sign in [Start free] │
├──────────────────────────────────────────────────────────────────────────────┤
│                          METHOD                                              │
│                          How a panel is checked.                             │  .method, 704px
│                          A plain account of how a verdict is made, and what   │
│                          it does not claim.                                  │
│                          ─────────────────────────────────────────────────   │
│  THE EXPERTS             Each expert is drawn from your own material.         │  .method-row
│  THE PAIRINGS            Experts are paired by what their documents …         │  140px | 1fr
│  THE PASSES              Every turn is filed with its position, strength …    │
│  THE WEIGHT              The weight of a turn comes from its strength and …   │
│  THE THRESHOLD           The argument converges when one position holds 0.80  │
│                          of the weight across the last two passes.            │
│                          [the tape, with its 0.80 double rule]               │
│  WHAT IT DOES            It is an analysis of the material you gave it, not   │
│  NOT CLAIM               an adviser.                                         │
│                          ─────────────────────────────────────────────────   │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Form.** One column of `min(704px, 100%)`, six `.method-row`s on a `140px | 1fr` grid, separated by `--hairline`, with a `--graphite` rule above the first. No imagery, no tabs, no cards. This is the trust-document form, and it is the reason the page exists.
- **The threshold row carries a worked example**: the tape with its 0.80 double rule, inline, at the row that makes the claim. A claim about a threshold shows the threshold.
- **Copy.** The six definitions above are V7's wording. The weight paragraph and the "not an adviser" line need the owner's final wording and a legal read against the Legal pages (D9). Everything else on this page is a statement about mechanism, so it can be checked against the code.
- **Links.** Linked from the header and the footer of the landing page, and from the threshold row of the Verdict page. It is the page that answers "why should I believe this", so it is reachable from every place that makes a claim.

### 8.5 The shell: three planes, and the rail's states

The app shell is the clearest statement in V7, so it is specified before the pages that use it.

```
┌──────────────┬───────────────────────────────────────────────────────────────┐
│ ◆ LarkVision ⇤ │ [search]                                    (PR) Priya Raman  │  plane 2 · --topbar-h 60px
│              ├───────────────────────────────────────────────────────────────┤
│ + New        │  Verdict                                                      │  .page-head
│   decision   │  The answer to every question you have brought.      4 filed   │  1px --record
│              │                                                               │
│ DOCUMENTS 12 │  ┌─────────────────────────────────────────────────────────┐ │
│ RUNS       4 │  │ panel: --sheet, 1px --panel-line, 10px                  │ │
│ VERDICT    4 │  └─────────────────────────────────────────────────────────┘ │
│              │                                                               │
│ ─────────    │                                                               │
│ (PR) Priya   │                                                               │
│ Sign out     │                                                               │
└──────────────┴───────────────────────────────────────────────────────────────┘
   plane 1 · --rail 280px      plane 3 · .content, 1400px, 32px 40px 96px
```

**Plane 1, the rail** (`--rail`, 280px, `--panel-line` right edge):
- Head: the wordmark, a collapse toggle, and one full-width primary "New decision".
- Nav: Documents, Runs, Verdict, each with a 16px icon, a 14px label and a mono count on the right. **The order is Documents · Runs · Verdict**, matching the product's own input → process → outcome.
- The active item takes `--graphite` at weight 600, a 2px `--accent` left rule and no tinted fill.
- Foot: the account (initials in a 32px ruled square), then Sign out.
- **Collapsed (`data-rail="min"`): 76px.** Icons only, the wordmark's word hidden, the labels hidden but kept for screen readers, "New decision" a 40px square. The width transition is `--t-layout` 240ms.
- **Below `lg` the rail is `display: none`** and the page takes a bottom bar. V7 hides it rather than shrinking it.

**Plane 2, the utility bar** (`--sheet`, 60px, `--panel-line` bottom edge):
- The context on the left, one search control on the right that opens the palette dialog (`⌘K`-style: `↑ ↓` to move, `Enter` to open, `Esc` to close).
- The account control opens the profile popover: name, email, plan and price, a units meter, payment method, next charge, then links to Billing, Account settings and Sign out, and one primary "Upgrade plan".

**Plane 3, the work area** (`.content`):
- `max-width: 1400px`, `padding: 32px 40px 96px`. The ground is `--ground`, so the panels sit on paper and the page does not read as a table.
- A page's parts are a `.page-stack` of `.panel`s with a 14px gap (§8.6).
- `.page-head` is the page's title block: an `h1` at `display`, a `lead`, and optionally a mono meta count on the right, closed by a **1px `--record`** rule. That rule is the only place `--record` appears on a light page, and it is what makes a page head read as a ledger heading rather than a dashboard title.

**The landing rule** for a signed-in account is unchanged: no material → **Documents**, empty, with one action; material but no filed answer → **Runs**; a filed answer → **Verdict**. The rail names all three on every page, so the rule never hides a destination.

**No greeting.** No "Good morning", no date eyebrow, no KPI tiles, no stat strip. The page leads with the decision's own state.

### 8.6 The panel, and the states every page shares

Every app page is a `.page-stack` of `.panel`s. The panel is specified once in §6.5, and this section fixes its three parts and the states that are identical on all five app pages.

**Panel anatomy.**

| Part | Fill | Size | Content |
|---|---|---|---|
| `.panel-head` | `--panel-head` | 46px min, `10px 18px` | `.panel-kicker` (mono 10px uppercase) + `.panel-title` on the left; `.panel-head-r` (a count, a segmented control, an action) on the right |
| `.panel-body` | `--sheet` | `18px` padding | the content. `.panel-body--flush` (`padding: 0`) when it holds a record |
| `.panel-foot` | `--panel-head` | `11px 18px`, top `--panel-line` | one `section-note` in `--ink-2` ≤ 66ch: how to read the panel. This is where the product explains itself instead of using a tooltip |

**The shared states.** All five app pages implement these identically, and each one is a *sentence*, not an icon:

| State | The page shows |
|---|---|
| Empty (a list) | A dashed `--record` rule around one sentence and one action. "No decisions yet. Start one with New decision." No sample rows, no tour, no illustration. |
| Empty (a panel that cannot be filled yet) | One sentence that says what will fill it and what the reader can do now. It never implies a feature the product lacks. |
| Loading | A skeleton that matches the shape it replaces, never a spinner alone and never a centre-page spinner. |
| Failed | A sentence that names what failed, then "Try again". The area is never left blank. |
| Partial | The part that worked is shown, and the part that did not says so. A failed measurement is not rendered as a zero. |
| Busy | The control is disabled, its label becomes the progress, and the surface carries `aria-busy="true"`. |
| Honest | A decision still arguing says so. A number that is not yet known is "Not yet", never `0`. |

**Two rules that hold everywhere.**
1. **One primary action per page.** If a page needs a second, it is secondary. If it needs a third, the page is wrong.
2. **Every panel foot explains its own numbers.** A units figure is meaningless without "A pass is one round of the panel's argument. A document is charged once, when the panel first reads it."

### 8.7 Verdict (`/results`)

The outcome. One filed decision is the largest object on the page, and the record of earlier ones is a ledger beside it.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Verdict                                                                      │
│ The answer to every question you have brought, and the record it was filed from│
│                                                              4 filed         │
├──────────────────────────────────────────────────────────┬───────────────────┤
│ ┌──────────────────────────────────────────────────────┐ │ EARLIER VERDICTS  │
│ │ FILED 12 OCT 2026 · MILL STREET · ALDER LANE  ⟨Converged⟩│                 │
│ ├──────────────────────────────────────────────────────┤ │ 09 OCT            │
│ │ Should the Mill Street lease be renewed?             │ │ Can we afford a   │
│ │                                                      │ │ second location?  │
│ │ ▼ NEGATIVE                              0.82         │ │ ▲ POSITIVE  0.86  │
│ │ Converged at 0.80 in pass 3.      share of weight    │ │ ────────────────  │
│ │ P1 ▇▇▇ P2 ▇▇▇▇ P3 ▇▇▇▇▇▇▇ ┃ 0.80                    │ │ 28 SEP            │
│ │ Converged — the verdict is ready.                    │ │ Should we hire a  │
│ │ THE CASE AGAINST                                     │ │ fourth engineer?  │
│ │ If the grease-trap work lands on time…               │ │ ◌ AMBIVALENT 0.58 │
│ │ WHAT THIS RESTS ON                                   │ │                   │
│ │ 1 Mill Street lease, p.4   2 Alder Lane lease, p.2   │ │                   │
│ ├──────────────────────────────────────────────────────┤ │                   │
│ │ [ Open the decision ]  [ Export document ]   8 sources│ │                   │
│ └──────────────────────────────────────────────────────┘ │                   │
└──────────────────────────────────────────────────────────┴───────────────────┘
   minmax(0,1fr)                                            296–336px
```

- **Layout.** `.verdict-layout` is `minmax(0,1fr) minmax(296px,336px)` with a 24px gap, and one column below `lg`, with the aside after the sheet.
- **The leading object** is the filed sheet inside `.verdict-panel`, whose body is `22px 24px`. It carries, in this order: the question at `sheet-q`, the `share-row` (position mark, the converged note, then the numeral at `clamp(44px,4vw,56px)` and "share of weight"), the tape with its double rule, the `tape-state` line, the case against, the sources, and a `panel-foot` with the two actions and the source count.
- **`.tape-state` is a sentence, not a badge.** It is one of: "Converged — the verdict is ready." · "Verdict ready — a plurality, not a consensus." · "Waiting for pass 1…" · "No position carries weight in this pass." Each is the tape's own vocabulary.
- **Earlier verdicts** are an `.aside-panel` whose body is flush: a month label, then rows of `12px 18px` separated by `--hairline`, each carrying the date in mono, the question in at most two lines, the position mark and the share. The whole row opens that verdict. Hover takes `--accent-soft`.
- **The page-head meta** carries the count ("4 filed") in mono. Every count on every page is in mono and comes from data.
- **States.** No verdict yet: "Your first verdict appears here when a decision files one.", with one action, "New decision". A pending decision keeps the previous answer, dated, and shows no placeholder answer. Failure shows a sentence and "Try again".

### 8.8 Documents (`/documents`)

The input. A record of material on the left, a reader on the right.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Documents                                             12 documents · 9 read   │
│ Everything you have added, and how much of it has been read. [ Add documents ]│
├──────────────────────────────────────────────────────────────────────────────┤
│ ┌── FILTER THE DOCUMENTS ───────────────────────────────────────────────────┐ │
│ │ [All] [Mill Street] [Ridgeline]   ⌕                            (sticky)   │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┬────────────────┐ │
│ │ ALL MATERIAL                          ⌕               │ ┌─ reader ────┐ │ │
│ │ DOCUMENT            MATERIAL   ADDED        READ      │ │ Mill Street  │ │ │
│ │ Mill Street lease   Mill St    12 Oct 2026  ● Read    │ │ lease.pdf  × │ │ │
│ │ Market notes.md     Mill St    11 Oct 2026  ● Read    │ │ Added 12 Oct │ │ │
│ │ Works schedule      Mill St    10 Oct 2026  ○ Not yet │ │ 2.4 MB       │ │ │
│ │ Ridgeline brief     Ridgeline  02 Oct 2026  ● Read    │ │              │ │ │
│ ├─────────────────────────────────────────────────────────┤ │ extracted    │ │ │
│ │ 12 documents · page 1 of 1                             │ │ text, 62ch   │ │ │
│ └─────────────────────────────────────────────────────────┴────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
   .doc-list-panel 1fr                                  24px  560px
```

- **Two panels and a split.** The toolbar panel (`.doc-toolbar-panel`, `position: sticky` under the bar) then `.doc-split`, a grid `minmax(0,1fr) 24px var(--reader-w, 560px)`. With the reader closed the last two tracks are `0`, so the list takes the whole width and nothing shifts when it opens.
- **The list panel's head** carries the kicker "All material" and a search control. Its body is a flush `.record`: a `record-head` in `--panel-head` with the column labels, then rows.
- **Columns:** document (`cell-strong`), material, added (mono), read state. A row is ≥ 44px with `13px 12px` padding, `--hairline` between rows, `--accent-soft` on hover, and **the whole row is the link**. Clicking opens the reader.
- **Read state is a dot and a word**: "● Read" and "○ Not yet". Colour is never the only signal.
- **The reader** (`.reader-panel`) is `position: sticky`, `height: calc(100vh - var(--topbar-h))`, `--sheet`, a `--panel-line` edge, 10px radius. Head is `--panel-head` (`12px 16px`) with the document name and a 44px close. Below it a `reader-toolbar`, then `reader-body` on `--ground` holding the extracted text at ≤ 62ch.
- **Keyboard.** Escape closes the reader and returns focus to the row that opened it. The close control is a real `<button>`.
- **Empty:** a dashed rule around "Start with your material. Everything else follows from it." and one action. No sample data and no tour.
- **Reader states:** loading (a skeleton matching the body), failure ("Couldn't open this document. Try again."), and an unsupported file, which says so rather than rendering nothing.

### 8.9 Runs (`/runs`)

The process. What the units bought, and every decision brought, newest first.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Runs                                                            12 decisions  │
│ Every decision you have brought, newest first.                               │
├──────────────────────────────────────────────────────────────────────────────┤
│ ┌── PLAN USAGE ────────────────────────────────────────────────────────────┐ │
│ │ UNITS THIS PERIOD          USED                    PASS UNITS            │ │
│ │ 3,420 / 8,000              15 passes               80 a pass             │ │
│ │ ▇▇▇▇▇▇▇▇▇▇▇▇░░░░░░░░░░░    6 documents · 2,220 units                     │ │
│ │ Resets 30 Nov 2026                                                       │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│ ┌── FILTER THE RUNS ───────────────────────────────────────────────────────┐ │
│ │ [All] [Deliberating] [Converged] [Complete] [Failed]                    │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│ ┌── DECISIONS ─────────────────────────────────────────────────────────────┐ │
│ │ QUESTION                        OUTCOME        STATUS    DATE   PASSES   │ │
│ │ Should we expand into the       still arguing  ● Delib   today   2       │ │
│ │ Should the Mill Street lease    ▼ NEGATIVE .82 Complete  12 Oct  4       │ │
│ │ Can we afford a second loc.?    ▲ POSITIVE .86 Converged 09 Oct  3       │ │
│ ├──────────────────────────────────────────────────────────────────────────┤ │
│ │ 12 decisions · page 1 of 2                                               │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Three panels, in this order: plan usage, the filter, the decisions.** `.units-grid` is `220px minmax(0,1fr) 190px` — the label, the meter, and the third measurement.
- **The plan usage panel is the billing surface inside the app.** It shows units used against the pool, what the passes bought, and when it resets. It is the same data as Billing (§8.10) and it never contradicts it.
- **The decisions table** uses the `.record` grammar: a `--panel-head` header row with mono uppercase labels, then rows of ≥ 56px, `--hairline` between, `--accent-soft` on hover, the whole row a link.
- **Columns:** question (`cell-strong`), outcome (position mark and share, or "still arguing"), status chip, date (mono), passes (mono). **No trail column and no convergence visual here** — the tape belongs to the verdict, and a second convergence visual would make two objects claim the same job.
- **The running row carries the accent live dot** and the words "still arguing". It is the only accent on the page.
- **Every row opens its decision.** A failed or interrupted decision still opens, and its chip says why.
- **Paging** is keyset, and the foot states the count and the page. The table never scrolls horizontally; below `lg` the row's columns collapse into two lines per row.
- **Empty:** "No decisions yet. Start one with New decision."

### 8.10 Billing (`/billing`)

V7's billing page is six panels: what this period has spent, what the units bought, the plans, the payment method, the invoices, and how a plan ends. It is the page the whole commercial relationship is read from, so it is the most panel-dense page in the product and every panel explains itself in its foot.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Billing                                                                      │
│ Your plan, what it costs, and what this period has spent.                    │
├──────────────────────────────────────────────────────────────────────────────┤
│ ┌── THIS PERIOD ───────────────────────────── Starter · $10 a month ────────┐ │
│ │ UNITS USED            NEXT CHARGE            PERIOD                      │ │
│ │ 3,420 of 8,000        $10.00                 1–30 Nov 2026               │ │
│ │ ▇▇▇▇▇▇▇▇▇░░░░░░░░     Charged on the card in  Resets 30 Nov 2026         │ │
│ │                       Payment method                                     │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│ ┌── WHAT YOUR UNITS BOUGHT ──────────────────────────────── 3,420 of 8,000 ┐ │
│ │ Reading your material        6 documents                        2,220    │ │
│ │ Arguing passes               15 passes · 80 units a pass         1,200   │ │
│ │ ════════════════════════════════════════════════════════════════════════ │ │
│ │ Total used                   of 8,000                           3,420    │ │
│ │ A pass is one round of the panel's argument. A document is charged once…  │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│ ┌── PLANS ────────────────────────────────── [ USD │ INR ] ───────────────┐ │
│ │  Starter            │  Studio             │  Enterprise                  │ │
│ │  $10 a month        │  $20 a month        │  Custom                      │ │
│ │  8,000 units        │  16,000 units       │  More than 16,000            │ │
│ │  [Your plan]        │  [ Switch to Studio]│  [ Talk to the founder ]     │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│ ┌── PAYMENT METHOD ──────────────────────── One card on the account ───────┐ │
│ │ VISA  Visa ending 4242 · Expires 09/28 · Priya Raman  [ Update card ]    │ │
│ │ Billing name · Billing country · Receipts                                │ │
│ │ ⓘ Charged monthly, in advance. The unit pool resets on the 30th.         │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│ ┌── INVOICES ───────────────────────────────────────────────── 3 invoices ─┐ │
│ │ DATE        INVOICE     PERIOD          AMOUNT    STATUS                │ │
│ │ 30 Oct 2026 INV-2026-004 1–31 Oct 2026  $10.00    ● Paid     [↓]        │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│ ┌── THE END OF A PLAN ────────────────────────────────────────────────────┐ │
│ │ Cancel the plan? A stopped plan keeps your material…  [ Cancel the plan ]│ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

**The six panels, in order.**

| # | Panel | Its head | Its body | Its foot |
|---|---|---|---|---|
| 1 | `.period-panel` | "This period" + the plan and price in mono | `.period-grid`, four cells: units used with a meter, next charge, period, resets | — |
| 2 | `.ledger-panel` | "What your units bought" + the same fraction | the `.ledger`: one row per source of spend (reading your material, arguing passes), each with a count and a figure; then a `.double-rule`; then the total row | the unit definition, ≤ 66ch |
| 3 | `.plans-panel` | "Plans" + the currency segmented control | the three plan options, the current one carrying its `--accent-soft` tint strip and a "Your plan" chip | one sentence on the unit pool |
| 4 | `.payment-panel` | "Payment method" + "One card on the account" | the card block, the billing lines, and a `.quiet-block`: "Charged monthly, in advance…" | — |
| 5 | `.invoices-panel` | "Invoices" + the count | a flush record: date, invoice, period, amount, status, download | — |
| 6 | `.quiet-panel` | "The end of a plan" | what stops, what stays, and one danger action | — |

- **The double rule is the point of panel 2.** Two 1px `--graphite` rules 3px apart, over the total, exactly as a ledger draws a total (§6.5). The rows above it are the entries. This is the signature object used where the product actually does arithmetic.
- **The plans panel is three, not four.** The free tier is named on `/pricing` only; a paying account's billing page shows what it can move between.
- **The current plan is marked three ways:** the chip "Your plan", the `--accent-soft` strip at the top of the card, and its action replaced by a state. Colour is never the only signal.
- **`.period-grid` is four cells on desktop and two on phone**, with `--hairline` between cells, not `--panel-line`.
- **Invoices** are a record, flush, one row per invoice, each row a real download control ≥ 44px. An invoice row is the only place a browser download happens from a record.
- **Every money figure is mono with tabular figures.** A currency symbol is never the only signal of a currency: the code says "₹1,999" or "$20", and the segmented control states which is in force.
- **States.** No payment method: the card block is replaced by one sentence and one action ("Add a card"), and "Next charge" reads "Not yet" rather than `$0.00`. No invoices: "Your first invoice appears after the first charge." A failed charge is a `--neg` `quiet-block` at the top of the page, above the period panel, with one action — never a silent chip.
- **The cancel flow** is a dialog: what stops, what stays, what is charged, then the confirm. It is not a one-click button, and the label names the object ("Cancel the Starter plan?").

### 8.11 Account (`/account`)

Four panels, each a different kind of setting, in one `.settings-stack` capped at 920px. The page is deliberately the narrowest in the app: settings are read line by line, not scanned.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Account                                                                      │
│ Your name, your sign-in, what we email you, and what you take with you.      │
├─────────────────────────────────────────────── .settings-stack 920px ────────┤
│ ┌── YOU ───────────────────────────────────────────────────────────────────┐ │
│ │ IDENTITY                                                                 │ │
│ │ (PR)  Your name [Priya Raman]   Email [priya@ridgeline.coffee]           │ │
│ │                                          [ Save changes ]                │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│ ┌── PASSWORD AND SESSIONS ─────────────────────────────────────────────────┐ │
│ │ SIGN-IN                                                                  │ │
│ │ Password · Last changed 12 Sep 2026            [ Change password ]       │ │
│ │ MacBook Pro · Chrome · Now          [ Sign out ]                         │ │
│ │ iPhone · Safari · 2 days ago        [ Sign out ]                         │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│ ┌── NOTIFICATIONS ─────────────────────────────────────────────────────────┐ │
│ │ EMAIL                                                                    │ │
│ │ [on ] When a verdict is filed                                            │ │
│ │ [off] When a decision fails                                              │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│ ┌── YOUR DATA ─────────────────────────────────────────────────────────────┐ │
│ │ TAKE IT, OR LEAVE                                                        │ │
│ │ [ Export everything ]  [ Delete your account ]                           │ │
│ │ Deleting removes your material with it. This cannot be undone.           │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

| Panel | Kicker | Title | Content |
|---|---|---|---|
| 1 | Identity | You | the avatar and a `.form-pair` of name and email, then one `.setting-actions` with "Save changes" |
| 2 | Sign-in | Password and sessions | the password line and its action, then `.session-row`s: device, browser, when, and a Sign out per session |
| 3 | Email | Notifications | `.switch-row`s, each with a title and a one-line explanation |
| 4 | Take it, or leave | Your data | "Export everything" (secondary) and "Delete your account" (danger), with the consequence stated in the panel |

- **Every panel is `.account-panel`** with an `18px 20px` body, and the page is `.settings-stack`, `max-width: 920px`, gap 14px. Below `lg` the `form-pair` collapses to one column.
- **A settings row states its current value in text**, not in a control's position. A password row says when it last changed, because "Change password" alone tells the reader nothing.
- **The delete flow is a dialog that names what it destroys**, requires the account's own email or password, and offers no undo. Export is a real download of the same document the verdict page exports.
- **Notifications are switches** (`.switch`), each with `role="switch"` semantics and a visible label. A switch is the one control that may be a toggle, because its two states are the whole content.
- **Sign out is per session**, and the current session is labelled "Now" rather than being singled out by colour.
- **States.** Saving: the button becomes the progress and the fields are disabled, with one toast on success. A failed save keeps the typed values and shows the reason inline. Deleting requires a second confirmation and shows progress, because it is irreversible.

### 8.12 Decision workspace (`/new`, `/runs/:id`): full-screen, no rail

The workspace is the only surface where the map and the flow are both visible, and the only one with no rail. It keeps V7's split exactly.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ◆ LarkVision  [× Close decision]  Should the Mill Street lease be renewed?      │  ws-top 60px
│                                 Material · Question · Panel   PASS 2 OF 4 · 02:14 │
├──────────────────────────────────────────┬┃┬───────────────────────────────────┤
│ THE MAP                    [All][Material]│┃│ THE FLOW                          │
│ [Experts][Opinions][Connections]          │┃│ run tabs, above the content       │
│ 20 entries · 24 connections               │┃│ Debate: stage rail, floor, pass   │
│                                           │┃│ scrubber, the tape with the 0.80  │
│        ●  ●       ●                       │┃│ rule, and the live record         │
│    ●        ●  ●       ●                  │┃│                                   │
│  ●     ●        ●  ●                      │┃│                                   │
│                                           │┃│                                   │
│ ▼ POSITIVE ▦ NEUTRAL ◌ AMBIVALENT ▼ NEGATIVE┃│                                  │
│ [− Minimise]                     [↗ Expand]│┃│                                  │
└──────────────────────────────────────────┴┃┴───────────────────────────────────┘
        44%                             8px divider                          1fr
```

- **Shell.** No rail. `.app` with `body.v5`, the map and the flow side by side. The bars are 60px and 56px on phone. Above `1279px` the question sits in the bar and wraps; the header is allowed to grow with it rather than truncating the decision.
- **The divider** is `role="separator"`, `aria-orientation="vertical"`, `aria-valuenow` set to the map's percentage, `aria-valuemin 25` / `aria-valuemax 75`. Drag between 25% and 75% with a 320px minimum on the map. Keyboard: Left and Right move 16px, Home sets 25%, End sets 75%, double-click resets to 50%. The ratio is remembered per decision. It is an 8px `linear-gradient(--record, --record)` rule, visible as a hairline with an invisible 8px hit area.
- **The map pane** is `.ws-map`: the radial night ramp, the five layer toggles (All · Material · Experts · Opinions · Connections) each with `aria-pressed`, a mono count strip, the SVG, two legends (positions, then material), and a foot with Minimise and Expand. Minimise collapses it to a 52px strip on phone and a narrow column above; Expand gives it the whole region and hides the flow. **Both keep the canvas mounted**, so the map is continuous from the first reading to the verdict.
- **The map is the only dark surface**, and its legend carries the four position marks on night with their words.
- **The flow pane** is `.ws-flow` on `--sheet`: the step's own stage rail, the floor, the pass scrubber, the convergence tape with its 0.80 double rule, and the live record. Nothing in it is deleted or replaced.
- **Step addresses do not change.** The workspace stays at `/new?step=ingest`, `?step=graph`, `?step=society`; a decision stays at `/runs/:id/<tab>`. Only the shell around them changes.
- **The three step words** (Material · Question · Panel) sit in the bar; the current one is `--graphite` and the others `--ink-3`. "Your material" and "The map" both light Material, "Your question" lights Question, and the run lights Panel.

| Step (address) | Map (left) | Flow (right) |
|---|---|---|
| Your material (`?step=ingest`) | empty until reading starts: "The map begins when the reading starts." | drop files, paste a link, name the material set, "Build the map" |
| The map (`?step=graph`) | grows as sections are read | reading progress by document |
| Your question (`?step=society`) | holds | the question composer and the panel settings, "Convene the panel" |
| The decision (`/runs/:id/<tab>`) | grows with experts and opinions | the five tabs; Debate holds the scrubber and the tape |
| Complete | holds the final state | the Verdict tab opens once, automatically |

### 8.13 The dialogs, and the one search

V7 ships ten dialogs and one palette. They are the whole modal surface of the product, and each one is named by its object.

| Dialog | Opened from | It asks |
|---|---|---|
| `new-decision` | the rail's "New decision" | the question, and what material the panel should argue from |
| `add-docs` | Documents, or step 1 | files, a link, and the material set's name |
| `checkout` | a plan's action | the plan, the currency and the total, then the provider's own page |
| `card` | Payment method | the card, replaced never added |
| `invoice` | an invoice row | the invoice, rendered as the document it is |
| `stopped` | a stopped decision | what stopped it, and what can be done |
| `password` | Account | the current password, then the new one twice |
| `cancel` | Billing | what stops, what stays, what is charged |
| `delete` | Account | the consequence, then the confirmation |
| `palette` | the utility bar's search | one field, a `listbox` of results, `↑ ↓` / `Enter` / `Esc` |

- **One dialog component.** `.dlg` = `--sheet`, a `--panel-line` edge, `--r-2` radius, `--overlay-shadow`, with a `.dlg-head` (title, one-line lead, 44px close), a `.dlg-body` and a `.dlg-foot` whose buttons go full width on phone. Escape closes; focus is trapped and returned to the opener.
- **The palette is the only search.** There is one search field in the whole product, it lives in the utility bar, and it opens this dialog. A page does not grow its own search box.
- **No dialog is a page.** Anything longer than one screen is a route, not a modal.

### 8.14 The scenario matrix: every page in every state

A page spec is not finished until its states are named. This table is the checklist: **each cell that applies must exist in the build, and its words must be the ones here.** Where a scenario cannot apply to a page, the cell says why — an honest "does not apply" is part of the spec.

**The scenarios, defined once.**

| # | Scenario | What it means |
|---|---|---|
| S1 | **Signed out** | no session. Only the site shell is reachable; the app shell is not rendered at all |
| S2 | **First use** | signed in, nothing added yet |
| S3 | **In progress** | a decision is arguing, or material is being read |
| S4 | **Complete** | the decision filed a verdict, or the action succeeded |
| S5 | **Empty list** | the page's record has no rows |
| S6 | **Loading** | the first paint before data arrives |
| S7 | **Failed** | the request or the decision failed |
| S8 | **Partial** | some of the data arrived, or a measurement is unavailable |
| S9 | **No plan / Free** | the account has the free entitlement |
| S10 | **Paid plan** | Starter or Studio, active |
| S11 | **Payment problem** | the plan lapsed, or the last charge failed |
| S12 | **At the limit** | the unit pool is exhausted, or a cap is reached |
| S13 | **Restricted** | the route needs a role the account does not have |
| S14 | **Reduced motion** | `prefers-reduced-motion: reduce` |
| S15 | **Phone (390px)** | the narrow layout, where a table becomes lines and a two-up becomes one |

**Page by page.**

| Page | Scenarios it must handle |
|---|---|
| **Landing** `/` (§8.2) | S1. S14 and S15 for the hero and the four stages. A signed-in visitor who reaches `/` is sent to the landing rule (§8.5), so the page has no signed-in state of its own. |
| **Pricing** `/pricing` (§8.3) | S1 · S9 · S10 · S13 · S14 · S15. Currency switch in both currencies. A plan whose price is not configured omits its price rather than showing a placeholder. S11 shows the page normally: a pricing page never scolds. |
| **Method** `/method` (§8.4) | S1 · S15. It carries no data, so it has no loading, failed or empty state, and that is deliberate: a page about the mechanism must not depend on the account. |
| **Sign up** `/auth/signup` (§8.1) | S1 · S5 · S6 · S7 · S15. Submitting (busy), invalid field, email already in use, and the account-created state that moves to the landing rule. |
| **Sign in** `/auth/signin` (§8.1) | S1 · S6 · S7 · S15. Invalid credentials, unverified email (which routes to verification, not to an error), and the busy state. |
| **Verdict** `/results` (§8.7) | S2 · S3 · S4 · S5 · S6 · S7 · S8 · S9 · S10 · S11 · S12 · S14 · S15. S3 keeps the previous verdict, dated. S8 shows the sheet with the sources it has and says the earlier list is incomplete. S12 says the pool is exhausted and offers the plans. |
| **Documents** `/documents` (§8.8) | S2 · S3 · S5 · S6 · S7 · S8 · S12 · S15. S3 shows reading progress per document. S7 is per document, not per page. |
| **Runs** `/runs` (§8.9) | S2 · S3 · S4 · S5 · S6 · S7 · S8 · S12 · S15. S3 is the live dot row. S8 pages what it has. |
| **Billing** `/billing` (§8.10) | S6 · S7 · S8 · S9 · S10 · S11 · S12 · S13 · S15. S9 shows the free state with one action. S11 leads the page with the failed-charge block. S13 returns the page with a sentence, never a blank tab. |
| **Account** `/account` (§8.11) | S6 · S7 · S8 · S13 · S15. Saving, saved, failed save, delete pending. |
| **Decision workspace** `/new`, `/runs/:id` (§8.12) | S2 · S3 · S4 · S7 · S12 · S14 · S15. S12 stops before seating a panel and says why. S7 keeps the map and the record that already exists. |
| **The dialogs** (§8.13) | S6 · S7 · S15 for every one. A dialog that fails stays open with the reason; it never closes silently on failure. |

**Five scenarios that cross every page, and are easy to forget:**

1. **The first 200ms.** No spinner appears. A skeleton, or nothing.
2. **A dead network.** Every panel that fetches owns a failed state with a "Try again". A page does not fail as a whole because one panel did.
3. **A slow network.** The page is usable before the data lands; the shell and the page head never wait for a panel.
4. **A long value.** A decision question of 120 characters, a material set with a long name, an email of 64 characters. Each has a stated measure or a clamp, and none breaks its column.
5. **The second visit.** The page is not newer than it was; if nothing changed, nothing animates and no toast appears for a condition the reader already saw.

**What this matrix deliberately does not include.** There is no onboarding tour, no sample-data mode, no "demo account", no empty-state illustration, no progressive-disclosure wizard and no celebration animation. Each of those would be a feature the product does not have, and §9.2 forbids claiming one.

### 8.15 Overview (retired)

The dashboard overview that the shipped app still serves at `/overview` — greeting, date eyebrow, the 1.6fr/0.75fr grid, KPI tiles — is not part of V7 and has no equivalent in it. V7 replaced it with the five app pages in §8.7 to §8.11 plus the three-plane shell in §8.5. The route stays until Documents, Runs, Verdict and Billing pass §10 in the browser, and it is removed after that. Nothing in this proposal rebuilds it.


---

## 9. Copy system

### 9.1 Voice

- **Plain.** Verbs a stranger understands. "Start your first decision", not "Initiate analysis".
- **Specific.** Names, dates, figures and documents. "Mill Street lease.pdf", not "a document".
- **One next step.** Every empty state and every error names one thing to do.
- **Honest.** The product says what is not known. "Verdict ready — a plurality, not a consensus." is a complete sentence. So is "Your material is too thin to argue this."
- **Active.** "Export document", not "Export". "Delete material", not "Remove".

### 9.2 The copy law (binding on every rendered string)

Never shown to a customer: **agent, graph, node, edge, round, retrieval, ontology, model, society, chunk, embedding, vector, LLM, prompt, token, pipeline, job.**

| Never | Always |
|---|---|
| agent | expert |
| graph | the map |
| node | entry |
| edge | connection |
| round | pass |
| retrieval | reading your material |
| ontology | the kinds of things in your material |
| model | the analysis |
| society | your panel |
| chunk | section |
| job | this decision |

Internal identifiers, route paths, API fields, log lines and test names are exempt. The law governs rendered text only.

**Add to the law (proposal, D7):** "corpus". The built app uses it in "Build the corpus", "Name this corpus" and "Not in a corpus yet". It is machinery vocabulary, so the replacement is "material" or "material set".

### 9.3 Sample copy by surface

| Surface | Copy |
|---|---|
| Documents, empty | "Start with your material. Everything else follows from it." · [Add a document] |
| Runs, empty | "No decisions yet. Start one with New decision." |
| Verdict, empty | "Your first verdict appears here when a decision files one." · [New decision] |
| Map, before reading | "The map begins when the reading starts." |
| Read failure | "Couldn't reach the server. Check your connection and try again." · [Try again] |
| Document failure | "Couldn't open this document." · [Try again] |
| Convergence, running | "Still arguing. Pass 2 of 4." |
| Convergence, converged | "Converged — the verdict is ready." |
| Convergence, not converged | "Verdict ready — a plurality, not a consensus." |
| Example label | "Worked example" · the note beside a real example: "Names and figures are illustrative." |
| Sign-up disclaimer | "AI-generated perspectives, not human advisors." (kept) |
| Toast, reversible | "Document deleted." · [Undo] |
| Toast, permanent | Permanent deletion asks first, in a sheet: "Delete this document for good? This can't be undone." · [Delete] · [Keep it] |
| Enterprise | "More than 16,000 units a month, or the same panel against material that keeps growing." · [Talk to the founder] |

### 9.4 Button and action verbs

Start (the first decision), Add (a document), Open (the decision), Export (the document), Delete (permanent: confirm first), Try again (after a failure), Talk to the founder (Enterprise), Sign in, Create account, Close decision, Minimise, Expand.

---

## 10. Accessibility and responsive rules

### 10.1 Standards

- **WCAG 2.2 AA is the floor.** Each text pair clears 4.5:1 and each control boundary or meaningful graphic clears 3:1. The measured values are in §6.1.
- **Colour is never the only signal.** Every position carries a symbol, a colour and a word. Every run state carries a symbol and a word. The convergence rule carries a label and a text sentence.
- **Targets are at least 44px** for every control and every text link. On a phone viewport the current homepage misses this on two links (the wordmark at 103×22px and "See what it files" at 96×21px, recorded in `DESIGN_SPEC.md` §14). The proposal closes both.
- **Focus** is a 2px indigo ring with a 2px offset on light surfaces, and a 2px night-ink ring (15.37:1) on the map.
- **Motion:** every animation has a reduced-motion form that renders the complete result.

### 10.2 Keyboard and screen readers

- **Everything is operable by keyboard.** The rail, the tabs, the workspace divider (arrow keys, Home, End), the drawer (focus trapped while open, Escape closes, focus returns), the reader and the layer toggles.
- **Map entries are reachable without a mouse.** The current build records a gap here: entries are mouse-only, and a keyboard user reads them only through the counts strip. The proposal adds a visually hidden, ordered list of entries, navigable with the arrow keys, with each entry's kind, position, source and passes. This closes the gap.
- **Live updates are announced once per pass,** in a polite live region: "Pass 2 of 4 filed. Leading position negative, 0.71." Updates within a pass are not announced, so the screen reader is not flooded.
- **Landmarks:** one `nav` for the sections, one `main`, and `aria-current` on the active destination.
- **The verdict is a document.** It has a heading structure (question as `h1`, then "The case against" and "Sources" as `h2`), so a screen reader can navigate it like a page.

### 10.3 Responsive

These are V7's own breakpoints, reproduced. They are not a 12-column system: V7 lays out with explicit `minmax()` grids and a small number of named widths.

| Range | What changes |
|---|---|
| **≤ 767 (phone)** | One column everywhere. The rail is hidden; a bottom bar takes over. `.site-wrap` loses 32px of each margin. `.auth-grid` becomes one column with the aside last. `.period-grid` becomes 2×2. `.units-grid` becomes one column. `.verdict-layout` becomes one column with the aside after the sheet. `.page-head` stacks its meta under the title. The map is 320px and sits *below* the flow (`order: 2`), and Minimise collapses it to a 52px strip. The divider is hidden. Record rows put their columns on two lines. Every control is at least 44px tall: `.field input`, `.field select`, `.field textarea`, `.btn-sm`, `.icon-btn`, `.filter`, `.pager button`, `.invoice-dl`, `.sheet-actions .btn`, `.setting-actions .btn`, `.ws-band .btn`, `.dlg-foot .btn`. |
| **768 to 1023** | Two-column section grids begin. `.hero-grid` is `1.02fr / 0.92fr`. `.site-section` padding drops from 80px to 60px. `.site-head` padding drops to 32px. |
| **1024 to 1279** | The rail is present at 280px. `.verdict-layout` is `1fr / 296–336px`. `.auth-grid` is `430px / 1fr`. The documents split is live. The `.cmp-table` is a real table. The workspace split is live with its divider. `.ws-top` keeps the question in the bar and lets it wrap. |
| **1280 and above** | `.content` is capped at 1400px, `.site-wrap` at 1280px. Display sizes reach their caps at 1440 (`hero-h1` 74px, `display` 40px, `numeral` 58px). |

**The one rule that matters at every width:** a table never scrolls horizontally. It stacks, in its own reading order. V7's `.cmp-table` has a `min-width: 720px` on desktop and is replaced below `lg` by one ruled block per plan — it is not scrolled. The same applies to every record.

### 10.4 Measured checks to run before any phase is accepted

- A contrast script over the token table in §6, using the same formula as in this file, failing on any pair under its floor.
- A screenshot at 390, 768, 1024 and 1440 of every page in §8, compared against the wireframes.
- The text alternative of the convergence rule read by a screen reader, and the same figures in the Verdict table.
- A keyboard-only walk of the workspace, the drawer and the reader.
- A reduced-motion pass with the system preference on.

---

## 11. Implementation map and phases

Nothing in this section is done. It is the plan for after the owner's decisions in §12. The markers follow `DESIGN_SPEC.md` §0.2: **E** keep as built, **C** change in place without changing behaviour, **N** new.

### 11.1 Files

The markers follow `DESIGN_SPEC.md` §0.2: **E** keep as built, **C** change in place without changing behaviour, **N** new.

| File | Marker | Change |
|---|---|---|
| `frontend/src/index.css` | C | Replace the palette and type tokens in `@theme` with §6: `--ground #F1F2EE`, `--rail #E7EAE1`, `--sheet #FFFFFF`, `--panel-head #F3F4EE`, `--panel-line #C7CDC2`, `--hairline #DDE1D7`, `--record #7C848F`, `--graphite #15171C`, `--ink-2 #3B414B`, `--ink-3 #5B636E`, `--accent #2D3F9C`, `--accent-hover #24357F`, `--accent-soft #E7EAF6`, the night set, the five `--layer-*` colours and their night variants. Remove the Fraunces variables. Keep the motion grammar. Keep `--gradient-map` only; delete `--gradient-first-light`, `--gradient-morning` and `--gradient-marked` (§6.9). |
| `frontend/src/main.tsx` | C | Remove the Fraunces import (line 7). The Archivo width import (line 8) is already present and stays. |
| `frontend/package.json` | C | Remove `@fontsource-variable/fraunces` once no import remains. No new dependency. |
| `frontend/src/tokens.test.ts`, `frontend/src/test/gradients.test.ts` | C | Update the assertions to the new tokens and to the single gradient. |
| `components/ui/Button.tsx` | C | 4px radius. Flat primary (no shadow). Secondary, ghost and danger per §7.1. |
| `components/ui/Field.tsx`, `Input.tsx`, `NumberField.tsx`, `Select.tsx`, `Textarea.tsx` | C | The ledger baseline (§7.2): a 1.5px graphite bottom rule, no box. |
| `components/ui/Chip.tsx` | C | 4px radius, mono 11px uppercase, symbol and word (§7.3). |
| `components/ui/PositionMark.tsx` | C | The four symbols in §6.1, with the built NEGATIVE triangle kept (D10). |
| `components/ui/FiledSheet.tsx` | C | `--sheet`, a 1px `--panel-line` edge, 10px radius, no shadow. The dissent block and the sources (§7.6). |
| `components/chamber/ConvergenceTape.tsx` | E | Unchanged. It draws the per-pass bars and the threshold line. The overlay sits on top of it. |
| `components/run/ConvergenceRuleOverlay.tsx` | N | The double rule at the threshold, its label, the surface-coloured gap that hides the tape's dashed line, the one-time draw on verdict filing, and the text alternative (§5.3). |
| `components/run/FlowView.tsx` | C | Wrap the existing `ConvergenceTape` (line 65) with the overlay. The stage rail, floor, scrubber and record are unchanged. |
| `components/run/AnswerDocument.tsx` | C | Render `ConvergenceTape` with the same series and the overlay beneath the share meter. The rest of the sheet is unchanged. |
| `components/shell/Rail.tsx` | C | 280px expanded, 76px collapsed, hidden below `lg` in favour of a bottom bar (N). The `--rail` plane with a `--panel-line` edge. Mono counts, and the nav order Documents · Runs · Verdict (§7.11). |
| `components/shell/AppShell.tsx` | C | A full-screen branch for the workspace, with no rail (§8.9). The ground comes from the token. |
| `components/workspace/Workspace.tsx` | C | The top bar's stage words (Material, Question, Panel) from `workspaceSteps.ts` (§7.12). The divider is checked against §7.12. |
| `pages/NewRunWorkspace.tsx`, `pages/RunPage.tsx` | C | The shell changes (§8.9). The step addresses, the in-flow stage rail and the tab strip above the content stay as built. |
| `marketing/Hero.tsx` | C | Recompose the ten sections of §8.2 — a hero, eight `.site-section`s each carrying a margin label, and the night close band. Copy and behaviour kept. The header and the footer gain a link to the Method page. |
| `auth/AuthLayout.tsx`, `pages/SignInPage.tsx`, `pages/SignUpPage.tsx` | C | `.auth-grid` at `430px / 1fr`, the ledger fields, and the filed sheet in the aside (§8.1). |
| `pages/PricingPage.tsx` | C | The plan ledger without a Free column, currency in the header, and the rows sourced from configuration (§8.3, D6). |
| `pages/ResultsPage.tsx` | C | `.verdict-layout` at `minmax(0,1fr) minmax(296px,336px)`, with the tape and overlay beneath the sheet (§8.7). |
| `components/common/RunTable.tsx` | E | The field mapping is unchanged. The material column is the existing corpus column. |
| `pages/RunsPage.tsx` | C | A `.page-stack` of three panels — plan usage, the filter, the decisions — with the material column and no trail (§8.9). |
| `pages/DocumentsPage.tsx`, `components/documents/DocumentReader.tsx` | C | A sticky toolbar panel, the flush record, and `.doc-split` with a sticky 560px reader (§8.8). |
| `components/graph/GraphCanvas.tsx` | E | Drawing unchanged. Colours come from the tokens. |
| `components/ui/Drawer.tsx` | C | `--overlay-shadow`, a `--panel-line` edge, 8px radius. Behaviour, focus trap and Escape unchanged. |
| `pages/MethodPage.tsx` | N | The Method page (§8.4), its route in `App.tsx`, and its links in the header and footer of `marketing/Hero.tsx`. |
| `components/ui/Panel.tsx` | N | The panel object (§6.5, §8.6): `Panel`, `PanelHead` (kicker, title, right slot), `PanelBody` (18px, or flush), `PanelFoot` (the note that explains the panel's own numbers). Every app page is built from this. |
| `components/ui/DoubleRule.tsx` | N | Two 1px `--graphite` rules 3px apart. Used over the billing total (§8.10) and the convergence threshold (§7.5). |
| `components/shell/TopBar.tsx` | N | Plane 2 (§8.5): the context on the left, the one search control, the account control that opens the profile popover. |
| `components/shell/ProfilePopover.tsx` | N | The account popover: name, email, plan and price, the units meter, the payment method, the next charge, then Billing, Account settings, Sign out, and one primary "Upgrade plan". |
| `components/ui/CommandPalette.tsx` | N | The one search (§8.13), on `<dialog>`, with a `listbox`, `↑ ↓` / `Enter` / `Esc`, and the results grouped by decisions, documents and invoices. |
| `components/billing/PeriodPanel.tsx`, `LedgerPanel.tsx`, `PaymentPanel.tsx`, `InvoicesPanel.tsx`, `QuietPanel.tsx` | N | The six billing panels (§8.10). Billing has no page in the shipped app today, so this is the page's whole body. |
| `pages/BillingPage.tsx`, `pages/AccountPage.tsx` | C/N | Billing is new (N). Account is changed in place (C) to the four `account-panel`s of §8.11, each with a kicker and a per-setting current value. |
| `pages/OverviewPage.tsx` | C | Route kept until Documents, Runs, Verdict and Billing pass §10, then removed (§8.15). |
| Every rendered string containing "corpus" | C | "material" or "material set" (D7). |
| `api/*`, `run/selectors.ts`, `graph/graphStore.ts`, `run/runStore.ts`, `auth/*`, `RequireAuth` | E | Not touched. The tape's series is already built on the client (`convergenceSeries`), so no backend change is needed. |

### 11.2 Phases

Each phase ends with its checks. A phase is not accepted until its checks pass, and the next phase does not start until it is accepted.

| Phase | Work | Checks |
|---|---|---|
| 0 · Decisions | Take D5 to D11 (§12). Decide whether the app is migrated to V7 at all (D11). Update the document of record (D5). | The owner's written answers are recorded in this file. |
| 1 · Tokens and type | Palette, type scale, radii, shadows and the width axis, in CSS only. | `cd frontend && npm run lint`, `npm run build`, and `npx vitest run src/tokens.test.ts src/test/gradients.test.ts`. The contrast script over §6.1 passes. |
| 2 · Primitives | Button, fields, chip, sheet, position mark. | The existing component tests (`Button.test.tsx`, `Field.test.tsx`, `FiledSheet.test.tsx`, `Label.test.tsx`) pass after their assertions are updated. Sign-up screenshot at 390 and 1440. |
| 3 · The convergence rule and the Verdict | The overlay (`components/run/ConvergenceRuleOverlay.tsx`, new), composed into `FlowView` and `AnswerDocument`, and `ResultsPage`. | `ResultsPage.test.tsx` passes. The overlay appears only when the tape shows a pass. The text alternative is present. A reduced-motion check shows the complete rule. The tape's own tests pass unchanged. |
| 4 · Runs and Documents | Ledger rows on the 12-column grid, the material column, the reader as an overlay. No trail. | `RunsPage.test.tsx`, `RunTable.test.tsx`, `DocumentsPage.test.tsx` and `DocumentReader.test.tsx` pass. Keyset paging is unchanged, and an existing test covers it. |
| 5 · Workspace and rail | The top bar with the stage words, the divider check, the rail states and the bottom bar. Step addresses unchanged. | `Workspace.test.tsx`, `AppShell.test.tsx` and `routes.test.tsx` pass. Every `?step=` and `/runs/:id/<tab>` address still resolves. A keyboard-only walk of the divider. |
| 6 · Landing page | The ten sections of §8.2, with the night close band and the Method links. | `Hero.test.tsx` passes. Screenshots at 390, 768, 1024 and 1440 match the wireframe. A copy-law sweep of rendered strings finds no banned word. The four-position legend and the tape read correctly without colour. |
| 7 · Pricing and Method | The four plan cards with Free as one of them, the row-by-row `.cmp-table`, the configured rows, the Method page and its route. | `PricingPage.test.tsx` passes. Each plan value is traced to its source. All four CTAs land on one line. Below `lg` the table stacks instead of scrolling. The Method copy is approved (D9). |
| 8 · Reconcile | Update `PRODUCT.md`, `DESIGN.md` and `docs/DESIGN_SPEC.md` to the approved direction. Remove the retired tokens and the Fraunces package. | The three documents agree with the code. A search finds no reference to a removed token. |

**The copy-law sweep** is a starting point, not a proof. It lists candidate strings in rendered JSX and text, which a person then reads: the banned words, "corpus", and any machinery term. Route paths and identifiers are exempt.

---

## 12. Decisions for the owner

Each open decision lists a recommendation, and the recommendation is what this proposal assumes. Nothing is built until the owner answers.

**Settled by `DESIGN_PRODUCT_V7.html`, and no longer open.** The owner named V7 as the authoritative interface design, so anything V7 answers is decided. These are recorded here so they are not re-litigated:

| Was | Now | Because |
|---|---|---|
| D1 Typeface | **Archivo expanded for display, Archivo for text, JetBrains Mono for figures. No serif in the interface.** | V7 ships exactly these two families; Georgia appears only inside `.paper`. |
| D2 Accent | **Indigo ink `#2D3F9C`.** | It is `--accent` in V7 and `DESIGN_PROPOSAL` line 468 / D2 already. |
| D3 Ground | **`#F1F2EE`.** | It is `--ground` in V7. |
| D4 Surfaces | **Four planes; the panel is the unit; no panel carries a shadow.** | §6.5, measured. |
| D10 NEGATIVE symbol | **The built filled down-pointing triangle.** | V7 uses it, at 12–14px, in both legends. |

**Also settled in this revision:**
- "The map" stays its own step, as built. Its address is unchanged (§8.12).
- The convergence rule is the existing tape with a double-rule overlay. There is no trail, no total track and no convergence visual in Runs (§5.3).
- The Runs page keeps its material column (§8.9).
- **The Free plan is a column on `/pricing`** (§8.3). This reverses the previous revision's decision, on V7's evidence. The signed-in Billing panel keeps three plans.
- The Method page is linked from the header and the footer (§8.2, §8.4).
- **The primary action is a flat accent fill, never a gradient** (§6.9). `DESIGN_SPEC.md` §3's plum action ramp is withdrawn.

**Still open.** D1 to D4 and D10 are answered by V7 and are not repeated here. What follows is what V7 cannot answer.

| # | Decision | Recommendation | Alternative | Why it matters |
|---|---|---|---|---|
| **D5** | Document of record | Adopt this proposal as the successor to `DESIGN.md` and `docs/DESIGN_SPEC.md` once approved. Update the visual-world paragraph of `PRODUCT.md` to match. Until then, all three stay as they are. | Keep `DESIGN.md` as the record and treat this file as an option. | Three documents disagree, and the code follows one of them. Someone has to decide which one is true. |
| **D6** | Pricing rows | Source "Panel size" and "Passes per decision" for each plan from plan configuration, and remove the hard-coded 12 and 4. Confirm the Free allowance before it appears. Decide whether any plan is marked "Recommended". | Keep the fallback values as they are. | The fallback rows show 12 and 4 for every plan. That is a claim, and `PRODUCT.md` bans unsupported claims. |
| **D7** | The word "corpus" | Replace it with "material" or "material set" in every rendered string. | Keep "corpus" as machinery vocabulary the customer already sees. | It is the kind of term the copy law exists to remove. |
| **D8** | The threshold window | Keep the tape as built: each pass is compared with the threshold on its own. Its series is already built on the client, so no backend change is needed. | Compare the threshold with the last two passes, the window that decides the verdict (`CONSENSUS_ROUNDS = 2`). That changes what the tape shows. | A single pass can cross 0.80 while the verdict's window does not. The tape and the verdict can then disagree, which would mislead the customer. |
| **D9** | Method page copy | The owner writes the plain-language weighting paragraph and the "not an adviser" line. A legal read is taken against the Legal pages. | Omit the Method page. | The page makes claims about how verdicts are made, so the wording has to be the owner's and checked. |
| **D11** | **Is the app migrated to V7 at all?** | **Yes.** Treat `DESIGN_PRODUCT_V7.html` as the target and migrate the React app to it, page by page, per §11.2. | Keep the shipped Quiet Room and treat V7 as a design exploration only. | This is the decision every other section depends on. V7 and the shipped app are two different worlds — indigo/`#F1F2EE`/Archivo-only versus evergreen/bone/Fraunces — and today the app a customer uses is the second one. If the answer is "exploration only", then §6, §8 and §11 describe a prototype and should not be built; if it is "migrate", they are the plan. |

**Order.** **D11 first**, because it decides whether any of this is built. Then D5, because it fixes the document the rest are measured against. Then D6 to D9. D6 must be answered before the pricing page changes, and D8 before the tape's overlay is built.

---

## 13. What was not verified, and the limits of this file

- **`DESIGN_PRODUCT_V7.html` was measured statically, not in a browser.** Every token, `clamp()`, grid, radius, shadow and gradient in §6 and §8 was read from its stylesheet (four `<style>` blocks, 125,332 bytes) and its markup (10 views, 10 dialogs), and every contrast ratio was computed from the hex values. I did not render V7 in a browser for this revision, so I have no pixel measurements of it; the wireframes in §8 are V7's own structure, drawn from its markup. It did previously pass a five-width Playwright check (1440/1280/1024/768/390, zero page errors, zero console errors, zero horizontal overflow, exactly one visible plane, ≥44px targets, no duplicate ids, no broken `<use>` or aria references), and that result is what makes it safe to treat as the reference.
- **"Each page and each scenario" is answered as a matrix, not as prose.** §8.14 is the checklist. It names 15 scenarios against 11 pages plus the dialog set, and it says where a scenario does not apply and why. It does not claim that the shipped app implements them — §11.2 is the work of making it do so.
- **The shipped app was not re-captured in this revision.** Its measured values in §3.2 to §3.8 are revision 1's, taken from the dev server at `localhost:5173`. They are the *baseline being replaced*, not the target.
- **The audit findings were not re-verified.** Where a screen in §8 depends on a fix in `run-2/REPORT.md`, the dependency is named. The findings themselves are the report's, not re-tested here.
- **The Chrome extension was not connected.** The gstack headless browser was used on public pages only. No form was submitted and no credential was entered.
- **boxes.dev's hero is a photograph.** Its treatment is described, not reproduced.
- **openrelay.inc's hero animates in.** Its first capture was blank. The recapture waited for the network to go idle and for four further seconds.
- **inkbox.ai's integrations page** was captured for its first viewport only. Its full height was not measured.
- **maritime.sh's security page** was measured in full, but only its first viewport was viewed as an image.
- **The tape's series** is built on the client by `convergenceSeries(run)`. I did not read that selector against `turn_protocol.py`, so the per-pass figures are not checked. The window question is D8.
- **The overlay on the Verdict sheet** assumes the tape accepts the same props there. That is unverified until phase 3.
- **The pricing fallback values** (D6) were observed in code. Their correct values are unknown, and this file does not guess them.
- **No code, test, configuration or other design document was changed.** `DESIGN_PRODUCT_V7.html` was read, never written. The dev server on port 5173 was read only. The only file changed in this revision is `DESIGN_PROPOSAL.md`. `DESIGN.md` and the deleted `docs/DASHBOARD_DESIGN.html` are superseded and neither was edited.
- **No subagents were used.** The owner's instruction about Haiku 5.5 at maximum effort applies only to subagents, so it did not apply to this work.
- **Contrast figures** are computed from hex values with the WCAG 2.2 relative-luminance formula. They are not tested against a rendered page or a colour-vision simulation. The §10.4 checks cover rendered pages.
- **This is a proposal.** Its wireframes show structure and proportion. Final proportions, copy and motion need the owner's review in the browser.

<!-- END OF DOCUMENT -->
