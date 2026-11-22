# Design Authority — LarkVision

**Status:** the record of record for design questions.
**Date:** 2026-11-22.
**Supersedes as a decision source:** `PRODUCT.md` (design clauses only) and `docs/DESIGN_SPEC.md` (in full).

---

## 0. Why this file exists

Six documents currently answer the question "what should this look like", and **four of them give a different answer**:

| Document | Accent | Ground | Display face | Status |
|---|---|---|---|---|
| `DESIGN.md` | `#1E4B38` evergreen | `#F4EFE6` bone | Fraunces | superseded |
| `docs/DESIGN_SPEC.md` | `#823A86` plum | `#ECEFF4` grey | Archivo + Spectral | **superseded by this file** |
| `frontend/src/index.css` (shipped) | `#1e4b38` evergreen | `#f4efe6` bone | Fraunces | **what customers see today** |
| `DESIGN_PRODUCT_V7.html` | `#2D3F9C` indigo | `#F1F2EE` | Archivo + JetBrains | **the named design reference** |
| `DESIGN_PROPOSAL.md` (rev 2) | `#2D3F9C` indigo | `#F1F2EE` | Archivo + JetBrains | adopted V7 |
| `docs/SIGNUP_TO_DASHBOARD_PLAN.md` | recommends evergreen | — | — | **contradicts the proposal** |

The chain of authority broke at every link. `PRODUCT.md` pointed at `DESIGN_SPEC.md`; `DESIGN_PROPOSAL.md` superseded `DESIGN_SPEC.md` but kept citing `PRODUCT.md`; and the plan cited **neither** of them (`PRODUCT.md` 0×, `DESIGN_PROPOSAL.md` 0×). Two files written thirty minutes apart answer the accent question oppositely.

This file ends that. It is the single place that says **which document answers which question**, and **what the answer is**.

---

## 1. Authority, by question type

One question, one owner. A question not listed here has no owner and must be taken to the owner — do not infer.

| Question | The authority | Why |
|---|---|---|
| What does the customer **do**, and what do they **get**? | **`PRODUCT.md`** | It is the confirmed product truth, settled 2026-10-17, and nothing here contradicts its flow, users or copy law. **It keeps authority on product behaviour; it loses it on design.** |
| What does a surface **look like**, token by token? | **`DESIGN_PROPOSAL.md`** (this revision) | It is a line-by-line re-specification of the named reference, with every value measured from `DESIGN_PRODUCT_V7.html` and every contrast ratio computed. |
| What **structure and layout** does a page have? | **`DESIGN_PROPOSAL.md`** §8, backed by **`DESIGN_PRODUCT_V7.html`** | The proposal names every section in V7's order; V7 is the pixel reference when the two are read side by side. |
| What is the **visual reference**? | **`DESIGN_PRODUCT_V7.html`** — for design only | Named by the owner as the authoritative interface design: colour, structure, layout, type. It is a **prototype**, never a build target (§5). |
| What is **built and running** today? | **`frontend/src/index.css`** and `frontend/src/` | Code is the only truth about the present. A document describing an unbuilt world is a target, not a record. |
| What must be **fixed in the backend**? | `run-2/REPORT.md` (external audit) | 38 findings, P1–P38. Not a design document. |
| **Which order** do we build it in? | **`docs/SIGNUP_TO_DASHBOARD_PLAN.md`** | The journey plan. It inherits its design tokens from `DESIGN_PROPOSAL.md` and its product flow from `PRODUCT.md`. |

**The read order for any new work:**

```
PRODUCT.md          what the customer does and gets   (behaviour authority)
      ↓
DESIGN_AUTHORITY.md the resolved values               ← you are here
      ↓
DESIGN_PROPOSAL.md  tokens, components, every page    (design authority)
      ↓
DESIGN_PRODUCT_V7.html   the pixel reference, for design only
      ↓
docs/SIGNUP_TO_DASHBOARD_PLAN.md   how it gets built, in what order
```

---

## 2. The resolved values

These are decided. Do not re-open them without the owner.

### 2.1 The accent — **UNRESOLVED. This is D15.**

This is the one question this file cannot close, and pretending otherwise would be the exact failure it exists to prevent.

| Candidate | Where it lives | Its standing |
|---|---|---|
| **Evergreen `#1E4B38`** | shipped `index.css:23`; **pinned in CI** by `frontend/src/tokens.test.ts:150` | the colour a customer sees today |
| **Indigo `#2D3F9C`** | `DESIGN_PRODUCT_V7.html:42`; `DESIGN_PROPOSAL.md` §6.1 (listed as settled) | the named design reference |
| Plum `#823A86` | former `DESIGN_SPEC.md` | **withdrawn** — never built |
| Bone-era bone `#F4EFE6` | shipped `index.css:10` | the shipped ground, not an accent |

**Why this is not resolveable by reasoning:** both are defensible and each has a hard commitment behind it. Indigo is what the owner named as the design; evergreen is what ships *and what a passing test asserts.* A test is a contract — if the accent changes, `tokens.test.ts` fails and must be rewritten with re-measured ratios. That is a deliberate re-theme, not a decision this file can take on the owner's behalf.

**Until D15 is answered, the rule is:** the shipped app keeps evergreen; `DESIGN_PROPOSAL.md` specifies indigo as the target; **no new surface introduces a third colour**, and no page mixes the two. Everything in §2.2 below is expressed in V7's tokens because the proposal is the design authority, and every one of them is a one-variable change if D11 goes the other way.

**Recommendation on record:** adopt indigo, because the owner named V7 as the design and a design reference whose accent is discarded is not a reference. Accept the one-time cost: re-pin `tokens.test.ts`, re-measure the contrast suite.

### 2.2 The tokens (from `DESIGN_PROPOSAL.md` §6, measured from V7)

| Role | Token | Value | Note |
|---|---|---|---|
| Ground | `--ground` | `#F1F2EE` | the page |
| Rail | `--rail` | `#E7EAE1` | the navigation plane |
| Sheet | `--sheet` | `#FFFFFF` | panels |
| Panel head | `--panel-head` | `#F3F4EE` | a panel's tinted head and foot |
| Panel line | `--panel-line` | `#C7CDC2` | a panel's own edge |
| Hairline | `--hairline` | `#DDE1D7` | rules inside a panel (decorative) |
| Record rule | `--record` | `#7C848F` | the only grey clearing 3:1 |
| Graphite | `--graphite` | `#15171C` | primary text |
| Accent | `--accent` | `#2D3F9C` | **see D15** |
| Night | `--night` | `#0F1320` | the map and the closing band only |
| Positions | `--pos/--neu/--amb/--neg` | `#1E7A4C / #5B636E / #8A6410 / #A3362B` | frozen order P·N·A·NEG |

**Display faces:** Archivo (with its width axis) + JetBrains Mono for figures. **No serif in the interface.** Georgia survives only inside V7's `.paper` block, which is rendered-document content, not chrome.

**Primary action:** a **flat** accent fill. There is no ramp on it.

### 2.3 The gradients — **exactly one**

This is stated here because three documents disagreed on it.

- **`PRODUCT.md:117`** mandated "the one primary action's ramp".
- **`docs/DESIGN_SPEC.md` §3** specified a plum `#8F3F97 → #823A86 → #6E2F74` action ramp.
- **`DESIGN_PROPOSAL.md` §6.9** withdrew that ramp, and the shipped `index.css` agrees: *"a flat evergreen fill, never a gradient (§4.8 rule 2)"*.

**Resolved: the proposal and the code win, `PRODUCT.md` and `DESIGN_SPEC.md` are corrected.** The product has exactly one gradient:

```
radial-gradient(120% 100% at 50% 0%, #1B2440 0%, #0F1320 72%)   /* the map pane */
```

Three other `linear-gradient()` declarations in V7 are **not** gradients — a 1px hairline, a flat tint strip, and a select chevron. The rule: a control is flat; a large dark instrument may have depth; both stops of a utility gradient must be the same colour; nothing else.

### 2.4 Structure, layout, spacing

| Question | Answer |
|---|---|
| The app shell | three planes: `--rail` 280px (76px collapsed) · `--sheet` utility bar 60px · `.content` 1400px |
| The page's unit | the **panel** — 10px radius, 1px `--panel-line`, tinted head and foot, **no shadow** |
| Marketing container | `.site-wrap` at `min(1280px, 100% - 96px)` |
| Section rhythm | `.site-section` 80px / 60px / 44px of vertical padding, `--hairline` top rule |
| Radius | 0 · 3px chips · 4px controls · 8px sheets · **10px panels** · 999px the live dot |
| Shadows | two only: `--overlay-shadow` for an overlay, one larger modal. **A panel never floats.** |
| Motion | 120 / 180 / 240 / 560ms on `cubic-bezier(0.2, 0, 0, 1)`; the convergence rule is the one authored moment |

**`PRODUCT.md`'s "12-column grid, 1280px, 24px gutters" is withdrawn** in favour of the above: V7 lays out with explicit `minmax()` grids, not a 12-column system, and `.content` is 1400px where `PRODUCT.md` said 1280px. Both were measured; the measurement wins.

### 2.5 Product behaviour — unchanged, and still `PRODUCT.md`'s

Nothing in this file overrides these, and no design work may contradict them:

- **The four moments:** add documents → the material is read → the question is asked → the panel argues → the answer is filed.
- **Three destinations:** Documents is the input, Runs is the process, Verdict is the outcome.
- **The landing rule:** no material → Documents; material but no answer → Runs; a filed answer → Verdict.
- **The copy law:** agent, graph, node, edge, round, retrieval, ontology, model, society, chunk, embedding, vector, LLM, prompt, token, pipeline, job — never rendered to a customer. Replacements as listed in `PRODUCT.md:132`.
- **Pricing:** free to start · Starter $10 / 8,000 units · Studio $20 / 16,000 units · Enterprise custom. One pool per month, no seats, no per-question invoice.
- **Four positions in frozen order:** POSITIVE, NEUTRAL, AMBIVALENT, NEGATIVE — always symbol, colour **and** word.
- **WCAG 2.2 AA**; colour is never the only signal; reduced motion renders the complete result.

### 2.6 Free tier presentation — **one open item**

| Document | Position |
|---|---|
| `PRODUCT.md:110` | "free to start", paid tiers named — **silent** on whether Free is a card |
| `DESIGN_PROPOSAL.md` §8.3 | Free **is** a column on `/pricing` (four cards) |
| `docs/SIGNUP_TO_DASHBOARD_PLAN.md` D2 | free is "a tier in the catalogue but **not** a card" |

Both are defensible: the pricing page is where a free tier is *named*, but a card is also a claim about an allowance nobody has verified. **The proposal's position stands** (it matches the named reference); the plan's D2 is **narrowed to the onboarding screen only**, where a ruled line is correct. Two different surfaces may present the same tier differently as long as neither contradicts the other's numbers.

---

## 3. Supersession record

### 3.1 `docs/DESIGN_SPEC.md` — superseded in full

It was the frontend design authority. It is now **removed from the chain** because:

- Its palette (plum `#823A86`, ground `#ECEFF4`) **describes a world that was never built**. No module imports it; the shipped accent is evergreen.
- Its action ramp was **withdrawn** by measurement (§2.3).
- Its type stack (Archivo + **Spectral**) contradicts the named reference, which has no serif in the interface.
- Its content grid (1280px, 12-column) contradicts the measured shell (1400px, `minmax()` grids).
- It called itself *"a record, not a target"* and *"a defect in this file, not a licence to change the code"* — sound principles, applied to a stale record.

**What survives from it, and where it now lives:**

| Kept | Now in |
|---|---|
| The three destinations and their jobs | `PRODUCT.md:59`, §2.5 above |
| The **E / C / N** implementation markers | `DESIGN_PROPOSAL.md` §11 |
| The copy law | `PRODUCT.md:130`, §2.5 above |
| The four position symbols | `DESIGN_PROPOSAL.md` §6.1 |
| "The code wins over the drawing" | §1 above — the principle is right, only its subject moved |

**Do not cite `DESIGN_SPEC.md` for any design decision.** If a paragraph of it is still needed, quote it into `DESIGN_PROPOSAL.md` and delete the pointer.

### 3.2 `PRODUCT.md` — keeps authority on product, loses it on design

`PRODUCT.md` remains **the** product truth: users, the job, the flow, the copy law, the pricing record, the accessibility floor. Every one of those is unchanged and binding.

It **loses** authority on these four design clauses, each now contradicted by measurement or by the owner's named reference:

| Its clause | Now |
|---|---|
| "Gradients… the one primary action's ramp" (line 117) | **withdrawn** — the action is flat (§2.3) |
| "Kept from them: the three installed faces (**Archivo, Spectral**, JetBrains Mono)" (line 116) | **Spectral leaves the interface** (§2.2) |
| "The content grid is the standard 12-column grid, max **1280px**, 24px gutters" (line 117) | the app is **1400px** with `minmax()` grids (§2.4) |
| "**+ New decision · Documents · Verdict · Runs**" (lines 55, 159) — while lines 59 and 61 say *"Documents = the input, Runs = the process, Verdict = the outcome"* | **Documents · Runs · Verdict.** `PRODUCT.md` contradicted itself; the order now follows its own stated logic (`DESIGN_PROPOSAL.md` §7.11) |

**A fifth clause is a live gap, not a contradiction:** `PRODUCT.md:67` says a new account *"lands on Documents and is asked for exactly one thing: add the first document."* The plan inserts `/onboarding/plan` before the dashboard and mentions "onboarding" 73×, while `PRODUCT.md` mentions it **0×**. That is a **product change** requiring the owner's sign-off — it belongs to `PRODUCT.md`'s authority, not to this file's. **Recorded as open item D16.**

`PRODUCT.md` is edited by amendment, never by silent contradiction: when a design clause is overridden, the clause is struck through with a pointer to the section here.

### 3.3 `DESIGN.md` — retired

The Quiet Room (bone, Fraunces, evergreen). Superseded first by `DESIGN_SPEC.md`, now by this file. It describes the world the shipped code partially implements. **Evidence, not authority.** Kept for history only.

### 3.4 `docs/DASHBOARD_DESIGN.html` — deleted

Removed by the owner. Not referenced anywhere.

---

### 3.5 The application name — **Societas → LarkVision** (2026-11-22)

The brand was renamed across the whole design corpus. Recorded here because a rename that leaves half the files saying one name and half the other is exactly the split §0 exists to prevent.

**Renamed (customer-visible brand, every case variant):** `PRODUCT.md`, `DESIGN_PROPOSAL.md`, `docs/DESIGN_AUTHORITY.md`, `docs/SIGNUP_TO_DASHBOARD_PLAN.md`, `DESIGN_PRODUCT_V7.html` (`<title>`, brand `aria-label`, the footer, the invoice document), `DESIGN.md`, `docs/DESIGN_SPEC.md`, `CLAUDE.md`.

| File | Before | After | LarkVision |
|---|---|---|---|
| `PRODUCT.md` | 4 | 2 (both historical, intentional) | 3 |
| `DESIGN_PROPOSAL.md` | 16 | 0 | 16 |
| `DESIGN_PRODUCT_V7.html` | 37 | 2 (both `societas.rail`) | 25 |
| `docs/SIGNUP_TO_DASHBOARD_PLAN.md` | 6 | 4 (all `societas_app` / `societas-uploads`) | 2 |
| `docs/DESIGN_AUTHORITY.md` | 1 | 0 | 1 |
| `DESIGN.md` / `docs/DESIGN_SPEC.md` | 11 / 11 | 0 | 11 / 10 |

**Deliberately NOT renamed — technical identifiers, not the brand.** Renaming these breaks running infrastructure and buys nothing a customer sees:

| Identifier | Where | Why it stays |
|---|---|---|
| `societas_app` | Postgres least-privilege role | live role; renaming needs a migration and a grant rewrite |
| `societas_retention` | Postgres retention role | same |
| `societas-uploads` | S3 bucket / prefix | live object-storage namespace |
| `societas.rail` | `localStorage` key in V7 | renaming silently resets every returning user's rail state |
| `.../2026-10-17-societas-*.md` | historical plan filenames **that exist on disk** | editing the string would create a dead link |
| `SIMULATION-WORLD` | the checkout directory | the owner's path, outside the product |

**Renamed but needing an action outside the repo — the email domain.** `societas.app` → `larkvision.app` in V7's footer and `mailto:` links, `CLAUDE.md`, `.env.sample` and `src/config/settings.py`. **`larkvision.app` is not registered.** Until DNS, SPF/DKIM and the Resend domain exist, every transactional mail fails silently in prod — `settings.py` refuses to boot without `EMAIL_API_KEY`, but it cannot know the domain is unowned. **Tracked as D19.**

**The half-rename still in the tree.** The design corpus says *LarkVision*; the code and its shell still default to the old strings. None of these is a design decision, so they are logged, not silently fixed:

| File | Still says |
|---|---|
| `frontend/index.html:7,10,13` | `<title>Societas</title>`, `og:title`, the meta description |
| `frontend/index.html:41` | `seed key societas-world-v1` (design-tool seed, harmless) |
| `.env.sample:45,47` | `no-reply@societas.app`, `hello@societas.app` |
| `src/config/settings.py:132,159` | the `email_from` and `legal_contact_email` defaults |
| `src/api/api_server.py:281` | `title="Socirty Simulator API"` — a **typo** for *Societas*; becomes `"LarkVision API"` under the plan §6.2 |

**The rule going forward:** the customer-visible name is **LarkVision** in every document, string and surface. A technical identifier may keep the old token only if it is in the table above; anything else is a miss.

## 4. What each file may and may not claim

| File | May say | May **not** say |
|---|---|---|
| `PRODUCT.md` | who the user is, what they do, what they get, what is banned | a hex, a typeface, a pixel, a gradient |
| `DESIGN_PROPOSAL.md` | every token, component, page and state | a product capability that `PRODUCT.md` has not settled |
| `DESIGN_PRODUCT_V7.html` | the design | anything binding — it is a prototype (§5) |
| `SIGNUP_TO_DASHBOARD_PLAN.md` | order, phases, exit criteria, backend contracts | a design decision (it inherits them) |
| `DESIGN_AUTHORITY.md` | **which file answers what, and the resolved value** | a new design (it records; it does not invent) |

**The one rule that prevents a seventh document:** a new question is added to §1 with an owner. A new value is added to §2. If a fact needs no owner, it is not a design decision.

---

## 5. The prototype boundary

`DESIGN_PRODUCT_V7.html` is **328 KB of one file**: four `<style>` blocks, one `<script>`, 240 element ids, hash routing, a hardcoded `PLANS`/`RUNS`/`DOCS`/`INVOICES`/`VERDICTS` fixture set (~1.6 KB), and `STATE.signedOut` standing in for auth.

**Copied from it, deliberately:** tokens (18 of 19 exact), page structure (41/50 headings, 33/38 margin labels verbatim), customer copy (81 strings), CSS hooks.

**Rejected, deliberately:** hash routing; hardcoded prices and data; the single-file architecture; the fake auth.

**Not yet triaged — the open gap:** ~30 V7 behaviours that look right and are not (cross-links that lose their destination, no session-expiry state, no offline state, no permission state). Recorded as **open item D17**. Until it is closed, V7 is a reference for **appearance only**, and no one may treat it as a specification of behaviour.

---

## 6. Open items

| # | Item | Owner | Blocks |
|---|---|---|---|
| **D15** | **The accent: evergreen `#1E4B38` (ships, pinned in CI) or indigo `#2D3F9C` (the named reference)?** | owner | every visual change; `tokens.test.ts` |
| **D16** | **Is `/onboarding/plan` a product change?** `PRODUCT.md` mandates Documents as the first landing; the plan inserts a plan-choice step. | owner | the plan's phase 1 |
| **D17** | **The V7 behaviour triage** — `KEEP 1:1` / `KEEP BUT WIRE` / `DROP`, per interaction | design + eng | any page port |
| **D18** | **`docs/` is gitignored** (`.gitignore:23`), so this file — like `DESIGN_SPEC.md` and the plan before it — is **not committed**. A design record that does not survive a clone is not a record. Either move it beside `PRODUCT.md` at the repo root, or un-ignore `docs/`. | owner | nothing in `docs/` survives a clone |
| **D19** | **`larkvision.app` is not registered.** The rename reached the email domain, but DNS + SPF/DKIM + the Resend domain are outside the repo. Until they exist, every verification and welcome mail fails silently. | owner + ops | all email; signup verification |

**Numbering.** `DESIGN_PROPOSAL.md` already uses **D1–D11** and `docs/SIGNUP_TO_DASHBOARD_PLAN.md` reuses **D1–D8** for entirely different questions — that collision is a live hazard and is fixed here by continuing at **D15**, leaving D12–D14 unused rather than re-numbering either file. From now on, a new decision number is allocated **here first**, in this table, and nowhere else.

D5 (document of record) in `DESIGN_PROPOSAL.md` §12 is **answered by this file's existence** — this *is* the document of record's index. The proposal's own D1–D4 and D10 are marked settled there; D6–D9 remain open and unaffected. **D11** in the proposal ("is the app migrated to V7 at all?") is distinct from **D15** here ("which accent") and both are live.

---

## 7. How to change a decision here

1. **Find the question in §1.** If it has no owner, stop — it is not a design decision, it is a product gap.
2. **Check §2.** If the value is resolved, it may only be changed by a deliberate re-theme: one variable, then re-measure every contrast pair, then update the pinned test.
3. **If it is open (§2.1, §6),** the owner answers it and the answer is written here **first**, then propagated.
4. **Propagate in this order:** this file → `DESIGN_PROPOSAL.md` → `SIGNUP_TO_DASHBOARD_PLAN.md` → the code. Never the reverse; a document that chases the code is already stale.
5. **Record the supersession** in §3, saying what changed and why. A silent change is how the six-way split happened.

**Note on version control.** See **D18** in §6: `docs/` is gitignored, so this file will not survive a clone until it moves or `docs/` is un-ignored.

---

<!-- END OF DOCUMENT -->
