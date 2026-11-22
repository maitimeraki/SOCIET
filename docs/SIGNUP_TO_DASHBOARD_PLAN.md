# LarkVision — Sign-up to Dashboard: the onboarding and plan journey

**Status:** proposed, not started.
**Date:** 2026-11-22
**Sources reconciled:**

- `security-audit-skill/SIMULATION-WORLD/run-2/REPORT.md` — the payment/auth/data findings, and report §11.5's target flow.
- `DESIGN_PRODUCT_V7.html` — a static design prototype: landing, plans, method, signup, and the signed-in surfaces.
- The repository as it stands: `src/` (FastAPI), `frontend/src/` (React + Tailwind v4), `frontend/src/index.css`.
- **`docs/DESIGN_AUTHORITY.md`** — the design record of record. It fixes the order this plan inherits its design from, and it supersedes `PRODUCT.md`'s design clauses and `docs/DESIGN_SPEC.md` in full. **Read it before any visual work.** This plan owns no design decision; it consumes them.

**What this plan is.** One journey, end to end: an anonymous visitor arrives, signs up, proves the address, **chooses a plan before ever reaching the dashboard**, optionally pays, and lands in the app with the account showing the plan they chose. For every hop it states what the backend must expose and what the frontend must render, expressed in this repo's existing components and tokens.

**What this plan is not.** It is not a port of `DESIGN_PRODUCT_V7.html`. That file is a prototype — vanilla JS, hash routing, hardcoded prices and illustrative data. Copying it into React would import exactly the class of bug the audit calls P10 (a client price that can differ from the charged amount). V7 is the **design reference**; the repo is the **implementation**.

---

## 0. The one-line problem

A new account lands in the dashboard on the free plan and is never asked to choose anything. Payment has no return path, so even a user who pays can be left looking at "Free". The product has a plans page and a billing screen, but **no moment where choosing a plan is part of becoming a user** — and no guarantee the dashboard agrees with what billing says.

---

## 1. Ground truth — what actually exists today

Verified by reading the tree, not assumed.

### 1.1 Backend: already built

| Surface | Where | State |
|---|---|---|
| `UserOut.email_verified` | `src/api/auth_api.py:84`, `:94` | **Shipped.** Derived from `email_verified_at is not None`. |
| `require_verified_email` | `src/auth/deps.py:137-152` | **Shipped.** Returns `403 {code: "email_unverified"}`. |
| Code send / confirm | `src/api/auth_api.py:218`, `:263` | **Shipped.** `POST /auth/verify/code/send` (202), `/verify/code/confirm` (200 `MeOut`). |
| OAuth providers / start / callback | `src/api/oauth_api.py:48`, `:54`, `:98` | **Written; migration `0010_oauth_accounts` now exists; untested; no client caller** (R41/R42). |
| Plan catalogue with a free tier | `src/billing/plans.py:37` | **Shipped.** `free`, `starter`, `studio`, `enterprise`; free units from settings. |
| Rate card | `src/api/billing_api.py:109-128` | **Shipped.** `/billing/plans` returns starter, studio, enterprise. **No free row.** |
| Usage / entitlements | `src/api/billing_api.py:131-151` | **Shipped.** `/billing/usage`: plan, units, limits, `billing_enabled`. |
| Subscription read / cancel | `src/api/billing_api.py:261`, `:270` | **Shipped.** |
| `app_base_url` | `src/config/settings.py:126` | **Shipped.** Prod-validated to a non-localhost origin. |

### 1.2 Backend: genuinely absent

| Gap | Evidence | Audit ID |
|---|---|---|
| No `callback_url` on subscription create | `src/billing/razorpay_client.py:60-83` — payload is `plan_id, total_count, expire_by, customer_notify, notes` | P1 |
| No onboarding concept anywhere | `grep -i onboarding` over `src/` and `frontend/src/` → no hits | report §11.5 |
| No `/billing/state` | — | report §11.5 |
| Grant depends on the RQ worker | `src/api/billing_api.py:383-399` returns 200 even when dispatch fails | P2 |
| No `current_period_end` check on grant | `src/billing/entitlements.py` | P5 |
| Deletion cancels only the newest subscription | `src/api/account_api.py:91-117` | P4 |
| Checkout inserts the mirror row **after** the provider call | `src/api/billing_api.py:224-254` | P3 |

### 1.3 Frontend: the implementation

| Piece | Where | Relevant fact |
|---|---|---|
| Route tree | `frontend/src/App.tsx:52-102` | Three layout routes: `MarketingLayout`, `AuthLayout`, `RequireAuth`→`AppShell`. `/landing` is a **sibling of the shells** (`:77`) — the pattern onboarding should copy. |
| Guard logic | `frontend/src/auth/guard.ts:13-17` | `resolveGuard(status)` → `splash` \| `redirect` \| `outlet`. **Reads no user field.** |
| Guard component | `frontend/src/auth/RequireAuth.tsx:70-99` | Bootstraps the session; no verification or onboarding branch. |
| `User` type | `frontend/src/api/types.ts:4-16` | Has `plan` and `entitlements`; **missing `email_verified`** despite the server sending it. |
| Sign-up | `frontend/src/pages/SignUpPage.tsx:70-72` | On success → `safeNext(next)`. Never routes to verify. |
| Verify page | `frontend/src/pages/VerifyEmailPage.tsx:103-133` | Reads `?token=` only. **No code entry.** |
| Pricing | `frontend/src/pages/PricingPage.tsx:29-58` | `PLANS` hardcoded price/limit fallback rendered with live buy buttons. |
| Checkout call | `frontend/src/pages/PricingPage.tsx:151-161` | `billingCheckout(...)` then `window.location.assign(url)` — the SPA is gone, nothing receives the return. |
| Plan usage card | `frontend/src/components/overview/PlanUsage.tsx:18-26` | Hardcoded `LIVE_STATUSES`; `created`/`paused` map to `'choose'` → a guaranteed 409. |
| Account | `frontend/src/pages/AccountPage.tsx:79-89` | Renders `user.plan` / `user.entitlements` from the **login-time snapshot**, never re-read. |
| Post-auth redirect | `frontend/src/pages/LandingPage.tsx:15-19` | `landingTarget(uploads, runs)` → documents \| runs \| results. |
| Rail | `frontend/src/components/shell/Rail.tsx:13-18` | Overview, Documents, Runs, Verdict. Plan lives at `/pricing`, outside the rail. |

### 1.4 A naming trap worth recording

`pages/LandingPage.tsx` is **not** the marketing homepage. It is the post-auth redirect stub. The homepage is `marketing/Hero.tsx`, mounted at `/` (`App.tsx:53`). Anyone reading "show the landing page" without this will edit the wrong file.

---

## 1.5 The completeness ledger — every flaw in `REPORT.md`, and where this plan closes it

`REPORT.md` is the source of record: **38 findings (P1–P38)**, **8 upgrade suggestions (§5)**, and an **auth addendum (§10)** with 7 parts and 15 security invariants. This plan now closes all of them, or states plainly which are deployment steps rather than code. Nothing is left as a pointer.

Read the table by its last column: `where` is a section of this plan. If a finding appears here, that section specifies the fix.

### 1.5.1 The 38 findings

| ID | Sev | Area | The flaw | Closed in |
|---|---|---|---|---|
| **P1** | High | Payments | No `callback_url`, no return route, no poll/success state | §B5, §F9, §10.3 |
| **P2** | High | Payments/ops | Grant depends on RQ worker; reconcile only in RQ; webhook acks 200 on dispatch failure | §B7 |
| **P3** | High | Payments | Provider-success/local-failure creates a second live subscription; no idempotency; no one-live constraint | §B8 |
| **P4** | High | Payments | Deletion cancels only the newest open subscription; reconcile re-grants to disabled users | §B10 |
| **P5** | High | Entitlement | No local `current_period_end` check; a stale `active` row grants a paid plan forever | §B9 |
| **P6** | High | Config | USD plan IDs are numeric placeholders; unknown plan IDs downgrade a paying user to `free` | §B24.1–B24.2 |
| **P7** | Critical | Data | MinIO published on 9000/9001 with default root credentials | §B12 |
| **P8** | High | Data lifecycle | Account deletion never deletes Neo4j; chunk nodes store full text | §B13 |
| **P9** | High | Frontend/data | Full extracted text stored in `sessionStorage` and round-tripped for graph build | §B14, §F13 |
| **P10** | High | Frontend | Client fallback prices/limits can be shown while a different amount is charged | §F5 |
| **P11** | High | Auth | Email verification never enforced (`ingest_url` ungated) | §B11, §F2, §F6 |
| **P12** | High | Auth | Raw session ID **is** the DB primary key and is returned by `/auth/sessions` | §B15 |
| **P13** | Medium | Payments | Abandoned checkout locks retry ~2 h; `paused` blocks indefinitely; 409 message is wrong | §B7 item 4, §10.3 |
| **P14** | Medium | Frontend | `created`/`paused` show “Choose a plan” → guaranteed 409; `halted` cancel is hidden | §F11 |
| **P15** | Medium | Payments | Failed webhook redelivery is acked and never re-enqueued; payload hash unused | §B16 |
| **P16** | Medium | Quota | Mid-cycle upgrade mints a second full allowance; `pending`/`paused` fall back to calendar month | §B17 |
| **P17** | Medium | Billing | Refunds/disputes/`payment.failed` unhandled; tax always 0; no invoice record; no checkout/cancel audit | §B18 |
| **P18** | Medium | Privacy | Webhook bodies stored verbatim 365 days (customer PII) | §B19 |
| **P19** | Medium | Auth | No Origin/Referer check; login CSRF via exempt paths | §B20 |
| **P20** | Medium | Auth | Signup enumeration via 409 + timing (duplicate skips argon2) | §B21 |
| **P21** | Medium | Auth | Rate-limit identity fragile: no proxy trust = one global bucket; `*` is spoofable | §B22 |
| **P22** | Medium | Auth | 30-day absolute sessions, no idle timeout, no cap; a write per authenticated request | §B23 |
| **P23** | Medium | Ops/config | `Settings` freezes before `dotenv.load_dotenv()`, so `.env` billing config may be inert | §B24.3 |
| **P24** | High | Data | No RLS; runtime Postgres role is the owner; least-privilege role wired nowhere; audit/ledger mutable | §B25 |
| **P25** | Low | Data | Chunk→entity link is unscoped (UUID4 makes it theoretical, the predicate should still exist) | §B26 |
| **P26** | High | Data/Redis | Redis has no auth and RQ payloads carry full document text; failed jobs persist for a long TTL | §B27 |
| **P27** | Medium | Data | Graph snapshots ship every LLM-emitted entity/relation property; only lineage keys stripped | §B28 |
| **P28** | Medium | Data | Neo4j runs as a single admin over plaintext `neo4j://` and holds the full chunk text | §B29 |
| **P29** | Medium | Frontend | Account page and run form use a stale login snapshot | §F10 |
| **P30** | Medium | Frontend | Overview invents counts/aggregates and joins corpora by name | §F12 |
| **P31** | Medium | Frontend | Draft store reuses old job IDs for a new dataset; “map built” without a build | §F13 |
| **P32** | Low | Auth | Verify/reset/WS tokens in query strings | §B30 |
| **P33** | Low | Auth | No password max length; a 1 MB password forces argon2 work | §B31 |
| **P34** | Low | Auth | Auth JSON lacks `no-store` except `/me` | §B32 |
| **P35** | Low | Data | Neo4j/Postgres no TLS internally; API port + `FORWARDED_ALLOW_IPS=*` on loopback | §B24.4, §B29 |
| **P36** | Low | Info | `/docs` and `/openapi.json` public; `/ready` unmetered LLM probe | §B24.5 |
| **P37** | Low | Contract | Run doc returns `user_id`; event key drift; `text: null` vs `string` | §B33 |
| **P38** | Low | Frontend | Hardcoded enterprise copy/units/legal links/mailto | §F14 |

**Count: 38 of 38 named.** Of these, 29 are code changes and 9 are deployment or configuration steps — marked **DEPLOY** in their section, so nobody schedules them as a sprint.

### 1.5.2 The 8 upgrade suggestions from §5

| # | Upgrade | Closed in |
|---|---|---|
| U1 | **Payment outbox** — persist every checkout/webhook, process with retries, a dead-letter view | §B16 (outbox), §B18 (audit) |
| U2 | **One entitlement resolver** — a single server function every route uses | §B34 |
| U3 | **Database-enforced tenancy** — RLS on `runs`, `uploads`, `datasets`, `jobs`, `usage_*` | §B25 |
| U4 | **Session tokens as secrets** — hash at rest, rotate on login, idle expiry, a sessions list | §B15, §B23 |
| U5 | **Email as a job, not a request** — outbox or `BackgroundTasks`, persisted `sent_at`, resend endpoint | §B36 |
| U6 | **Structured billing audit** — checkout, cancel, webhook receipt, refund, plan change + correlation IDs | §B18, §B37 |
| U7 | **Remove client fallbacks that can transact** | §F5, §F8 |
| U8 | **Observability for the payment path** — one dashboard, alert on p95 > 2 min and stale `pending` | §B37, §C1 |

**Count: 8 of 8.** U3, U4 and U7 partly restate findings; they are listed because `REPORT.md` lists them as upgrades, and each now has its own section.

### 1.5.3 The auth addendum (§10)

| Item | Closed in |
|---|---|
| §10.3 A — six-digit code signup | §B11 (gate), §F7 (the screen) — **backend already shipped**, see §1.1 |
| §10.3 B — GitHub/Google OAuth | §B38 (migration, credentials, redirect URIs) |
| §10.3 C — Enforcement, not just UX | §B11 |
| §10.3 D — Frontend plan | §F6, §F7, §F15, §F16 |
| §10.3 E — **Configuration** | §B24.6, §D5 below |
| §10.3 F — **15 security invariants to test** | report §11.4 — all 15 enumerated |
| §10.3 G — Test matrix for the next session | report §11.5 |
| §10.4 — **“do not deploy this tree”** | §C2 — a hard gate, first item in §12 |
| §10.5 — **Completion checklist (9 steps)** | §C2.1 — reproduced in order |
| §10.6 — What changed in that session | *(context only; no action)* |
| §10.7 — Note on the earlier report | *(context only; no action)* |

### 1.5.4 The 12 journey stages (§11)

| Stage | Closed in |
|---|---|
| 11.1 Stage 0 — anonymous visitor | §B24.5 (`/docs`, `/ready`), §F15 (public worked example) |
| 11.2 Stage 1 — gated route signed out | §F16 (`next` survives both login paths) — guard already correct |
| 11.3 Stage 2 — signup | §F6, §B21 (enumeration), §B36 (mails off the request path) |
| 11.4 Stage 3 — email verification | §F7, §B36 |
| 11.5 Stage 4 — choose a plan → dashboard | §B1–B6, §F8, §F9 |
| 11.6 Stage 5 — first work | §B14, §F13 |
| 11.7 Stage 6 — abuse controls | §B21, §B22, §B11 |
| 11.8 Stage 7 — session lifetime | §B15, §B23 |
| 11.9 Stage 8 — pay, cancel, delete | §B10, §B13, §B18 |
| 11.10 Stage 9 — operator visibility | §C1 |
| 11.11 Ordered implementation plan (20 items) | §12 — remapped, every item scheduled |
| 11.12 Definition of done | §13 |

### 1.5.5 What this plan adds that `REPORT.md` does not cover

`REPORT.md` is a backend audit. It has **no** finding on the shape of the API surface or the frontend route tree, and that is not an oversight — it was out of scope. Two things are therefore new here rather than reconciled:

- **§R1–R7, the route structure.** Three addressing schemes, a doubled mount, and inconsistent prefixes. This is the owner's own question, and nothing in `REPORT.md` answers it.
- **§F5/§F8's render rules** — the audit says “render only server values”; this plan says what the screen shows while the server has not answered yet.

Both are marked as additions in their sections, never as audit findings, so no credit is taken for work the audit did not do.

---

## 2. Decisions the owner must make first

These are blocking. Each is a real fork, not a formality.

### D1. Which accent is the product?

Three exist, and none is a shade of another.

| Source | Value | Where |
|---|---|---|
| **Shipped** | `#1E4B38` evergreen | `frontend/src/index.css:23` — what the app renders today, with a passing contrast suite (`tokens.test.ts:75-79`) |
| ~~`DESIGN_SPEC.md`~~ | `#823A86` plum | **Withdrawn** — superseded by `docs/DESIGN_AUTHORITY.md` §3.1. Listed for history only; do not build against it |
| **V7 prototype** | `#2D3F9C` indigo | `DESIGN_PRODUCT_V7.html:51` and `:1051` (`--accent` in the two `:root` blocks) — the file handed over as the design reference |

**Recommendation: keep the shipped evergreen.** It is the only one with measured contrast assertions already in CI. Changing it invalidates the entire §2.6 matrix and the token test. If the owner prefers V7's indigo, that is a deliberate re-theme (one variable, then re-measure), and it should be its own change before this journey work starts — not smuggled in with it.

### D2. Does the free tier appear on the plans page?

`plans.py` defines `free`; `/billing/plans` does not return it; `DESIGN_PROPOSAL` D6 says the free allowance is unverified and is added to pricing only after D6 is answered. V7 shows **four** cards including Free.

**Recommendation:** free is a **tier in the catalogue but not a card**. The onboarding screen says "Start free — 1,000 units" using the server's `plan_free_units`, and adds a card only once D6 is answered. This preserves V3/V7's honesty about the free path without publishing an allowance nobody has verified.

> **⚠️ This recommendation now conflicts with the design authority, and D2 must be re-answered.** `DESIGN_PROPOSAL.md:1671` states *"The Free plan **is** a column on `/pricing`"*, calling it a reversal on V7's evidence — while `DESIGN_PROPOSAL.md:1614` still says the pricing page ships *"without a Free column"*. **The proposal contradicts itself on this row**, and this plan's recommendation sides with line 1614 against line 1671. V7 is unambiguous: four cards, Free first, `$0 / month`. Resolve in `DESIGN_AUTHORITY.md` §2.6 (*"Free tier presentation — one open item"*) before F5 or F8 is built, or the pricing page will be built one way and the onboarding screen the other.

### D3. Does onboarding block the dashboard, or nudge it?

- **Hard block** (recommended): `RequireAuth` sends an un-onboarded account to `/onboarding/plan` and nowhere else is reachable.
- **Soft nudge**: a banner on Overview.

The audit's report §11.5 argues for the block — one conversion number, one return target, one place to record "free". A hard block is also the only version where "the dashboard shows the plan you chose" is *guaranteed* rather than hoped for.

### D4. Is email verification enforced for existing accounts?

`require_email_verification` defaults to `true` (`settings.py:139`), and `tests/conftest.py` does not set it false. Turning it on in production gates every spend route for every account that never verified — including the seeded demo account if its `email_verified_at` is null.

**Recommendation:** before deploying the gate, backfill `email_verified_at` for accounts older than the gate, or ship the gate with a config flip and a one-time backfill. This is a deployment step, not a code step, and it belongs in the plan rather than in a surprise during rollout.

---

## 3. The target journey

```
 匿名 visitor
   │  /
   ▼
 homepage (marketing/Hero)  ──── "Start free" ────┐
   │                                              │
   │  /pricing (public rate card) ────────────────┤
   │                                              ▼
   │                                    /auth/signup
   │                                       │  password OR GitHub/Google
   │                                       ▼
   │                              /auth/verify   ← only when email_verified === false
   │                                 │  6-digit code  ·  resend (60s)  ·  "use the link"
   │                                 │  OR provider-proved → already verified
   │                                 ▼
   │                       /onboarding/plan    ← NEW · no rail · one decision
   │                                 │  server prices only · free path always available
   │                                 │
   │        ┌────────────────────────┴────────────────────────┐
   │        │ "Continue free"                                  │ "Start with Studio"
   │        ▼                                                  ▼
   │   POST /billing/onboarding/complete          POST /billing/checkout
   │        │                                    (callback_url → /onboarding/plan?checkout=return)
   │        │                                                  │
   │        │                                                  ▼
   │        │                                          Razorpay hosted page
   │        │                                                  │ pays
   │        │                                                  ▼
   │        │                                     /onboarding/plan?checkout=return
   │        │                                       poll /billing/state every 3s ≤ 90s
   │        │                                       ├ active  → success panel
   │        │                                       ├ pending → "activating…" + retry
   │        │                                       └ timeout → keep waiting, never "failed"
   │        ▼                                                  ▼
   │     POST /billing/onboarding/complete {choice:"paid"}  (idempotent)
   │        └────────────────────────┬─────────────────────────┘
   ▼                                 ▼
 /landing  ──►  landingTarget(uploads, runs)  ──►  /documents | /runs | /results
                                                  (AppShell · the rail · the plan band)
```

**Why `/landing` and not `/overview` at the end:** `landingTarget` already decides between documents, runs and results from the account's real state (`LandingPage.tsx:15-19`). Hardcoding `/overview` would make a brand-new account land on an empty dashboard, which is the exact thing that function exists to prevent.

### 3.1 The owner's requirement, stated in one place

The journey above is not negotiable and every clause is now testable:

1. **Password sign-up** → email + password → a **verification window** where the user enters a 6-digit code mailed to them, **or** opens the link in the same mail.
2. **GitHub / Google sign-in** → an alternative to the password path, available on both `/auth/signup` and `/auth/signin`. A provider-proved address is **already verified**, so this path skips the verification window.
3. **Either path, once verified** → an **onboarding plan page**, on its own address with no rail, where the user chooses free or paid.
4. **Only then** → the dashboard.

**The gate rule that makes 3 meaningful:** `RequireAuth` refuses every app route while an account is un-onboarded, so the plan page is a step, not a suggestion. That is D3's hard block, and it is the recommendation.

**What "verified" gates, precisely.** It is **not** a gate on reaching the dashboard — a user who has verified but not chosen a plan still cannot pass. The verify gate blocks only the spend routes (`ingest_files`, `ingest_url`, `ontology`, `build_graph`, `debate`), returning `403 email_unverified` from `deps.py:150`. The onboarding gate blocks the shell. Two gates, two failure modes, two screens — do not collapse them into one.

### 3.2 The three screens, and how each one is specified

| Screen | Route | V7 equivalent | Source of truth for its look |
|---|---|---|---|
| Verification | `/auth/verify` | **none** | **F7** → `DESIGN_PROPOSAL.md` **§8.16** (ruled `.field` baseline, mono code field, `.auth-grid` at 430px + 72px gap) |
| Provider buttons | on `/auth/signup` and `/auth/signin` | **none** | **F17** → `DESIGN_PROPOSAL.md` **§8.17** (`.btn-secondary` at 48px, 4px radius, above the form) |
| Plan choice | `/onboarding/plan` | **none** | **F8** → `DESIGN_PROPOSAL.md` **§8.18** (V7's `.plan-card` at 10px, `.plan-badge`, free as one ruled line) |

**This is the single most important V7 finding in the plan.** V7 answers **none** of the three screens the owner requires. Its `signup` is a single static form whose own copy says *"this preview creates the account on this page; nothing leaves it"* — it has no verification step, no provider buttons and no post-signup redirect. Its plan cards live at `/pricing` (a marketing page any visitor can read) and its Billing view (a signed-in page for an account that already has a plan).

**Now closed on the design side.** `DESIGN_PROPOSAL.md` **§8.16, §8.17 and §8.18** specify all three, built from V7's own stylesheet values rather than from a V7 drawing — V7 has no drawing to trace. The exact CSS in those sections is quoted from `DESIGN_PRODUCT_V7.html`, so the screens match V7's language even though V7 never contained them. **F7/F8/F17 must be built to those sections, not invented at implementation time.**

**The three rules that keep them V7-faithful:**

1. **Fields are ruled baselines, never boxes.** `.field input` is `border:0; border-bottom:1.5px solid var(--graphite); border-radius:0; padding:8px 0`, with a 2px `--accent` bottom rule on focus. A boxed input anywhere on these three screens is off-spec.
2. **Two radii, never mixed.** Controls are **4px** (`--r-1`). Cards and panels are **10px** (`.panel`, `.plan-card` — a literal, not `--r-2`). Sheets are **8px** (`--r-2`). A control never takes a card radius, and a card never takes a control radius.
3. **Auth buttons are 48px.** `.auth-form .btn` is `min-height:48px`; provider buttons must match it exactly, or the stack reads as two different sizes of the same thing.

---

## 4. Backend plan

Ordered. Each item is independently shippable.

### B1. Record that onboarding happened — migration `0011_onboarding`

```
users
  + onboarding_completed_at  timestamptz NULL
  + onboarding_choice        text NULL   -- 'free' | 'paid'   (analytics, not authority)
```

Nullable, additive, no backfill needed (existing accounts predate the gate). Downgrade drops both columns.

**Why a column and not a table:** one timestamp and one enum do not earn a join. It also keeps the guard's identity read to a single row.

### B2. Expose the flag on the session — `src/api/auth_api.py`

Add to `EntitlementOut`:

```python
onboarding_required: bool
```

Resolved as:

```python
onboarding_required = (
    user.onboarding_completed_at is None
    and settings.billing_enabled          # no billing → nothing to choose
    and not user_has_blocking_subscription # a paying user is never asked
)
```

**Why on `MeOut` and not only on a new endpoint:** `RequireAuth` already makes exactly one call (`authMe`) to decide where a session goes (`guard.ts:49-63`). Putting the flag there keeps the guard at one round-trip. A separate read would add a render-blocking waterfall to every authed page load, for a boolean that changes twice in a lifetime.

Keep `/billing/state` (B4) for the **screen**, which needs prices and subscription action — things the guard does not.

### B3. Record the free choice — `src/api/billing_api.py`

```
POST /api/v1/billing/onboarding/complete
body: { "choice": "free" | "paid" }
→ 200 { "onboarding_required": false }
```

- Idempotent: a second call with the same choice is a no-op 200; never re-opens the gate.
- `choice: "paid"` is only accepted when a blocking subscription exists; otherwise `409 {code: "no_subscription"}`. The client cannot mark itself paid.
- `verify_csrf` dependency, like every other state-changing billing route.
- Audit row: `onboarding_completed` with the choice.

**The rule:** this endpoint records a fact, it never grants entitlements. `plan_key` stays derived from the provider object in `src/billing/webhook.py`, as it already is.

### B4. One server-owned plan state — `src/api/billing_api.py`

```
GET /api/v1/billing/state     (auth, Cache-Control: private, no-store)
{
  "plan": "starter",
  "billing_enabled": true,
  "onboarding_required": false,
  "subscription": {
     "status": "active",
     "action": "cancel",                  // server-decided, never a client status set
     "current_period_end": "2026-12-30T00:00:00Z",
     "cancel_at_period_end": false
  },
  "limits": { "max_agents": 12, "max_rounds": 4 },
  "units": { "total": 8000, "used": 3420, "remaining": 4580 },
  "period": { "start": "...", "end": "..." },
  "prices": [
     { "key": "starter", "INR": 999, "USD": 10 },
     { "key": "studio",  "INR": 1999, "USD": 20 }
  ],
  "currencies": ["INR", "USD"]
}
```

`subscription.action` is the whole point: it replaces `PlanUsage.tsx`'s hardcoded `LIVE_STATUSES` (P14). The server returns one of `cancel`, `scheduled`, `choose`, `resume` — and the client switches on it without knowing any status names.

### B5. Close the payment loop — `src/billing/razorpay_client.py`

```python
"callback_url": f"{get_settings().app_base_url.rstrip('/')}/onboarding/plan?checkout=return",
```

Add `return_to` to the checkout request, validated against a **closed allowlist**:

```python
_ALLOWED_RETURN = {"/onboarding/plan", "/overview"}
```

Anything else falls back to `/onboarding/plan`. Never echo a client URL into a redirect. **The query string grants nothing** — the webhook remains the only authority.

### B6. Make the grant observable — `src/billing/webhook.py`

On `subscription.activated`, alongside `plan_key`, write `plan_activated_at`. The return page needs to distinguish "paid, not yet active" from "active", and it must not guess from a status string.

### B7. Fix the operational chain so the dashboard actually updates — P2

Four changes, all small:

1. Register reconcile **and** the lease sweep in the API lifespan when `queue_mode == "inline"`, so the documented Windows dev path has the same retry as compose.
2. Stop returning `200` from `/webhook` when dispatch failed. Record `dispatch_failed` and let reconcile own it; the handler still returns `200` to Razorpay **only** when the event is stored *and* dispatched.
3. Alert when a `pending` webhook is older than 10 minutes.
4. Bound the `created` blocking check by local `created_at` against `AUTHORISATION_WINDOW_SECONDS` (already defined, `razorpay_client.py:27`), so an abandoned checkout does not lock retries for two hours (P13).

### B8. Idempotent checkout — P3

- Insert the `subscriptions` row with `status="creating"` and a `client_request_id` from the request **before** calling Razorpay.
- On provider success, update that row with the provider id and status.
- On provider failure, mark the row failed; if the provider *did* create it, cancel it.
- Treat `creating` as blocking.
- Add a partial unique index: **one blocking subscription per user.**

### B9. Grant only while the period is live — P5

`resolve_entitlements` resolves a paid plan only when the mirror is `active` **and** `current_period_end > now`; otherwise `free`. This is the difference between a lapsed subscription ending and one granting a paid plan forever.

### B10. Deletion cancels everything — P4

Iterate **all** `OPEN_SUBSCRIPTION_STATUSES` rows and cancel each; refuse the deletion if any cancel fails. Skip grants when `user.disabled_at` is set.

### B11. Finish the auth gate — the last inconsistency

`ingest_url` is not gated while `ingest_files` is (`src/api/ingest_api.py`). Add `Depends(require_verified_email)` to it, then add a test that enumerates every state-changing router and asserts each spend/enqueue route *depends on the gate* and each read route *does not*. That test is the deliverable; the one-line fix is incidental.

---

### B12. Lock down object storage — P7 **DEPLOY**

MinIO is the only browser-reachable datastore, and it currently publishes `9000` and `9001` on every interface with the root credentials still `minioadmin` because `.env` does not override `MINIO_ROOT_PASSWORD`.

```yaml
minio:
  # no ports: the app and minio-init reach it on the compose network
```

1. **Remove the published ports.** `9000` and `9001` both. Nothing outside the compose network has a reason to open S3.
2. **Set real credentials** from a secret manager. `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` must be non-default, and boot must refuse `minioadmin` in `prod` (§B24.4).
3. **Stop using the root principal for the app.** Create a dedicated S3 user limited to `societas-uploads/*` and `exports/*`; the app gets that user, never root.
4. If the console must be reachable, bind it to `127.0.0.1:9001` and put it behind the reverse proxy with its own auth — never on the public interface.

**Why this is first in the data block:** an export zip contains the full extracted text of every document. Port `9000` plus root credentials is the shortest path to all tenant data, and it needs no application bug to exploit.

### B13. Delete the graph on account deletion — P8

Deletion today removes Postgres rows and S3 objects and leaves Neo4j untouched, so "delete my account" leaves the most sensitive copy behind. `tasks.py:410-424` records this as an explicit KNOWN GAP.

New `src/graph/erasure.py`:

```cypher
MATCH (d:Document {dataset_id: $dataset_id}) DETACH DELETE d
```

Then delete entities and chunks left with no remaining `DERIVED_FROM`/`MENTIONS` edge, so orphan nodes do not accumulate.

- Call it from `_delete_graph_data` in `src/jobs/tasks.py`.
- **Fail loudly** if it cannot run: the account is *not* reported deleted while its graph survives. Deletion is a 202 that reports progress; the final note says what was removed.
- Add a regression test against a dummy dataset: seed three documents, delete, assert zero nodes for that `dataset_id` and that another dataset is untouched.
- Run it **before** the Postgres rows are dropped, so a partial failure is retryable from the audit trail rather than orphaned.

### B14. Stop shipping the corpus to the browser — P9

This is one change that closes four problems at once: the `sessionStorage` quota failure, the XSS/extension exposure, the "client can change what the graph is built from" hole, and the metering bypass.

1. **`GET /api/v1/ingest/documents` returns metadata only** — `{upload_id, title, word_count, source_type, mime_type}`. No `text` field, ever.
2. **`POST /simulate/ontology|build_graph` accepts `upload_ids: list[UUID]`** and loads `extracted_text` server-side, owner-checked. A build from an id the caller does not own is a 404, not a 403 — the same rule the run routes already follow.
3. **The draft store keeps names and status only** (`draftStore.ts`): delete the `text` field and every round-trip of it.
4. **The wizard stops posting text.** `GraphPage.tsx` posts ids.
5. Add `GET /api/v1/uploads/{id}/preview` returning a bounded, truncated excerpt, so the reader can render a document without the full text (§B35).

**The test that proves it:** a graph build with a `upload_ids` list succeeds; the same build with a text body and no ids fails validation; `/ingest/documents` response JSON contains no field whose value exceeds 4 KB.

### B15. Session tokens as secrets — P12, P22, U4

The `sid` cookie value **is** the `sessions` primary key, and `GET /auth/sessions` returns each row's `id` — so a DB read, a support screenshot, or an XSS that calls that endpoint yields live bearer tokens for every device.

Migration `0012_session_secret`:

```
sessions
  + token_hash  bytea NOT NULL          -- sha256(token); the lookup key
  + public_id   uuid NOT NULL           -- non-secret, what /sessions returns
  ~ id           stays the PK, no longer the token
```

- **Look up by `token_hash`**, never by the raw token. `deps.py` hashes the cookie value and compares.
- **`/auth/sessions` returns `public_id`**, plus device/last-seen. Never `token_hash`, never the raw token.
- **Rotate on privilege change:** password change and email verification both issue a new token and revoke the others.
- **Migrate and rotate:** existing sessions cannot be hashed in place, so the migration expires every current session once (an acceptable one-time logout) rather than leaving raw tokens valid.

**The test:** `/auth/sessions` response contains no value equal to any `Cookie` header; a forged `sid` that is not in `sessions` gets 401; reading the `sessions` table does not yield a usable cookie.

### B16. The webhook is never silently dropped — P15, U1

Three failures today: a duplicate delivery is acked and never re-enqueued; the payload hash is computed and unused; a dispatch failure returns `200`.

1. **On duplicate delivery, read the row.** If `status != 'processed'` or the payload hash differs, **re-enqueue** rather than returning early.
2. **Use `payload_hash`** as the idempotency key it was built to be: same hash + processed → 200 no-op; same hash + unprocessed → re-enqueue; different hash → log `webhook_conflict` and process both, since a provider may legitimately send a different event for the same subscription.
3. **The payment outbox (U1).** A `billing_events` row per checkout, webhook receipt and cancel, with `status ∈ {pending, processing, processed, failed}`, `attempts`, `last_error`, `next_attempt_at`. Processing is a worker task with retries and backoff. This replaces "`create_task` or hope reconcile runs" and gives an auditable payment timeline with a dead-letter view (`status='failed' AND attempts >= N`).
4. Never return `200` when the event is stored but not dispatched — that is §B7.2.

### B17. One allowance per period — P16

A mid-cycle upgrade mints a second full unit allowance, and `pending`/`paused` fall back to the calendar month.

- **Carry `units_used` forward** when the period key changes, instead of resetting the meter. The meter is keyed by `(user_id, period_start)`; a plan change must not create a new key.
- **Key the meter to the subscription's period**, not to the calendar month, for every status — `pending`, `paused` and `active` alike. One function decides the period bounds and every caller uses it.
- An upgrade grants `new_total - used` for the remainder of the current period, never a fresh `new_total`. A downgrade never reclaims below what is already used.

**The test:** upgrade on day 15 after using 6,000 of 8,000 → the new allowance is 16,000 total with 6,000 used, not 16,000 with 0 used.

### B18. Refunds, failures, tax, invoices and audit — P17, U1, U6

Five separate gaps, one section, because they are one missing surface: the money timeline.

1. **Handle the events that are ignored today:** `payment.failed`, `refund.created`, `refund.processed`, `subscription.halted`, `subscription.paused` and `subscription.resumed`. Each writes the mirror row and an audit row.
2. **A refund is not a cancellation.** A refund sets `subscription.refunded_at`; the plan ends at `current_period_end` unless the operator also cancels. Never silently re-grant after a refund — this is the same rule as §B9.
3. **Real tax configuration.** `tax.py:5` is `{"IN": 0}` with a "set 1800 once registered" comment. Either configure the rate per country and send `tax_amount`, or remove the field — a `0` that means "unknown" is a false claim on an invoice. **Owner decision, §D6.**
4. **Persist invoice facts** on every successful charge: `invoices{user_id, provider_payment_id, amount, currency, tax_amount, period_start, period_end, status, issued_at, pdf_url}`. An invoice the customer cannot retrieve is not an invoice.
5. **Audit every money action:** `checkout_created`, `checkout_returned`, `webhook_received`, `plan_activated`, `cancel_requested`, `cancel_effective`, `refund_received`, `plan_change`. Today only `plan_change` is audited.

### B19. Stop retaining customer PII — P18

Webhook bodies are stored verbatim for 365 days, and Razorpay payloads can carry the customer's contact fields.

- **Store only the fields the sync needs** — `entity`, `event`, `subscription_id`/`payment_id`, `status`, `current_period_end`, the plan id. Drop `notes`, contact fields and customer objects into a redacted column or drop them entirely.
- **Shorten retention** to 90 days for the body and 400 days for the audit row that references it, which is what an accountant actually needs.
- A test asserts the stored body contains no key from a denylist: `email`, `contact`, `phone`, `name`, `address`, `notes.customer`.

### B20. CSRF gets an Origin check — P19

`verify_csrf` exempts login when no CSRF cookie is present, which lets a cross-site form put a victim inside the attacker's workspace.

In `src/auth/cookies.py`, **before** the exempt fall-through:

```python
origin = request.headers.get("origin") or request.headers.get("referer")
if origin and origin.rstrip("/") not in settings.cors_allowed_origins:
    raise HTTPException(status_code=403, detail="CSRF origin mismatch.")
```

- An absent `Origin` **and** absent `Referer` is allowed only for non-browser clients on non-exempt paths; the exempt list stays as small as it is today.
- The same check applies to the **WebSocket** routes (`graph_stream_api.py`, `debate_api.py`), which today accept any origin.
- Test: a POST from an unlisted origin → 403; the same POST with no origin header → unchanged behaviour.

### B21. Duplicate signup is indistinguishable — P20

A duplicate email returns `409` *before* the argon2 hash while a new email pays ~64 MiB of hashing, so both status **and** latency reveal whether an account exists.

- **Return the same 202 shape** on both paths.
- **Run the dummy-hash work on the duplicate path**, so the timing matches.
- **Notify the existing address** — "someone tried to sign up with your email", with a password-reset link. That turns an enumeration attempt into a useful signal for the real owner.
- Normalise `+tag` addresses (`a+x@x.com` ≡ `a@x.com`) **for the uniqueness check only**, never for delivery.
- Reject disposable domains against a maintained list, and check the domain has an MX record before the account commit (§B35).

### B22. Rate-limit identity is trustworthy — P21

`FORWARDED_ALLOW_IPS=*` in compose makes the client address spoofable, and with no proxy trust every request lands in one global bucket.

- **Configure the proxy CIDR explicitly** (`FORWARDED_ALLOW_IPS=172.18.0.0/16` for the compose network). Never `*`.
- **Refuse to boot in prod with `*`** (§B24.4) — this is the same class of error as a localhost `APP_BASE_URL`.
- **Bucket by `(ip, normalized_email)`** for signup and code sends, so one address cannot be mailed repeatedly and one network cannot farm many addresses.
- Keep the per-IP bucket for everything else.

### B23. Sessions expire from idleness — P22

30-day absolute sessions with no idle check, no cap, and a write on every authenticated request.

- **Idle expiry 12 h:** compare `last_seen_at` in `deps.py` (it is already written; nothing reads it).
- **Throttle the write:** update `last_seen_at` at most once per 5 minutes per session, so an authenticated request is not a DB write.
- **Cap live sessions at 10.** Signing in past the cap revokes the least-recently-seen device and says so in the response.
- **Audit `login_failed`** with a hashed identifier, and add a per-account Redis counter that returns 429 after N failures.
- **A new-sign-in notice** on a new UA/IP combination, shown in `/auth/sessions` (§B15 supplies the list).

### B24. Configuration that fails loudly — P6, P23, P35, P36

**B24.1 Validate plan IDs at boot.** `re.fullmatch(r"plan_[A-Za-z0-9]+", value)` for every Razorpay plan id. A one-character numeric placeholder fails at import, not at a customer's checkout.

**B24.2 An unknown plan id never downgrades.** `webhook.py:138-153` resolves `free` when the id is unrecognised. Change it: **keep the current plan and alert.** A misconfigured `.env` must not silently un-pay a paying customer. Create the real USD plans before enabling USD.

**B24.3 Load `.env` in `settings.py`.** `api_server.py:35` builds `Settings` before `:45-51` calls `load_dotenv()`, so under plain `uvicorn` the `.env` billing config is inert. Load it inside `settings.py` (or document `uvicorn --env-file .env` as the only supported launch), then assert `billing_enabled` on `/health`.

**B24.4 Boot refuses an unsafe production config.** In `prod`, refuse to start when any of these is true — each is one line, and each has caused a real incident class:

| Condition | Why |
|---|---|
| `app_base_url` points at localhost | `callback_url` would be unreachable |
| `allowed_hosts` or `cors_allowed_origins` still contains a localhost entry | the API 400s and the SPA is blocked |
| `forwarded_allow_ips == "*"` | the rate-limit bucket is spoofable |
| `MINIO_ROOT_PASSWORD in {"", "minioadmin"}` | §B12 |
| `database_url` has `sslmode=disable` | §B35 |
| `neo4j_uri` starts with `neo4j://` | §B29 |

**B24.5 Close the reconnaissance surface.** `FastAPI(...)` currently sets no `docs_url`, so `/docs` and `/openapi.json` are public in every environment, and `/ready` fires an unmetered LLM call once a minute.

- `docs_url=None, redoc_url=None, openapi_url=None` when `env == "prod"`; keep all three in dev.
- **Protect `/ready`** with a shared token or make the LLM probe cron-only. A readiness probe must not cost money.
- `/health` stays open and cheap — it is the liveness contract, and it must never probe.

**B24.6 The auth-addendum configuration (§10.3 E).** Add to `.env.sample` with real defaults:

```env
REQUIRE_EMAIL_VERIFICATION=true
EMAIL_CODE_TTL_SECONDS=600
EMAIL_CODE_RESEND_SECONDS=60
EMAIL_CODE_MAX_ATTEMPTS=5
EMAIL_CODE_HOURLY_LIMIT=5
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
OAUTH_REDIRECT_BASE=            # defaults to APP_BASE_URL
OAUTH_STATE_TTL_SECONDS=600
```

Provider consoles must register exactly these two URIs, or the callback 404s:

```
https://<app-origin>/api/v1/auth/oauth/github/callback
https://<app-origin>/api/v1/auth/oauth/google/callback
```

### B25. Database-enforced tenancy — P24, U3

Isolation is application-level only. The runtime connects as the Postgres **owner** because compose builds `DATABASE_URL` from `POSTGRES_USER`; the least-privilege `societas_app` role created by `scripts/setup_db_roles.sql` appears in no Python module and no compose service.

1. **Wire `societas_app`** as the runtime role; keep the owner for migrations only.
2. **Add RLS** on `runs`, `uploads`, `datasets`, `jobs`, `usage_*`, `subscriptions`, `invoices`, `sessions`, `audit_log`.
3. **Set `app.current_user_id` per transaction** — a connection-level `SET LOCAL` in the session dependency, so every query is scoped by the database and not only by the ORM.
4. **Keep the application filter** as defense in depth, never as the only wall.
5. **Mount `scripts/db_roles.sql`** so the ledger split is real; revoke `UPDATE`/`DELETE` on `audit_log` and `usage_events` from the app role so "append-only" exists in the database, not in a comment. `societas_retention` owns age-based deletes.

**The test:** with RLS on, an ORM query with the *wrong* `user_id` returns zero rows. That is the assertion that proves the wall exists.

### B26. Scope the chunk→entity link — P25

`_LINK_CONCEPTS_TO_DOCUMENTS` matches a chunk by global `id` without `dataset_id` (`graph_build.py:60-65`). Chunk ids are server-minted UUID4, so a cross-tenant effect needs a UUID collision — theoretical, but the predicate costs nothing.

Add `dataset_id` to the `MATCH`. Keep the `public_events` allowlist entry under review (§B33).

### B27. Redis holds no corpus — P26, U1

Redis is unauthenticated, carries full document text in RQ payloads, and persists failed jobs for a long default TTL.

- **Pass `upload_ids` in job payloads, never text** (§B14 makes this possible).
- **Redis AUTH + TLS**, and a **namespace split** (`auth:`, `jobs:`, `cache:`) so a job payload read is not a credential read.
- **Set short `result_ttl` / `failure_ttl`** on the queue, so a failed job does not leave the corpus in Redis for a day.
- Compose must not publish `6379` — it does not today; keep it that way.

### B28. Project graph properties through an allowlist — P27

`graph_snapshot.py:36-96` ships every entity and relation property the model emitted, stripping only lineage keys. Open-ended properties can carry emails, phone numbers or verbatim passages into every graph read.

Replace the deny-list with a **per-label allowlist with length caps**, deny by default. A new property is invisible to clients until someone adds it deliberately. Cap each string at 512 characters and each list at 32 items.

### B29. Neo4j is not the corpus store — P28, P35

- **`neo4j+s://`**, not plaintext `neo4j://`.
- **Stop storing chunk text in Neo4j** — the graph needs structure, not prose. This also shrinks every snapshot (§B28).
- **A dataset-scoped read factory**, so graph reads cannot forget the scope.
- **A non-admin Neo4j account** for the application; admin only for bootstrap.

### B30. Secrets out of query strings — P32

Verification, reset and WebSocket tickets travel in query strings, so proxies and APM URL capture retain them.

- **Move single-use tokens to the URL fragment**, which is not sent to the server on navigation, and have the client POST them.
- **Keep the WS ticket TTL at 30 s** and pass it as a subprotocol header, not a query parameter.
- Keep `?token=` **working** for links already in the wild for one release, with a deprecation log, then remove it.

### B31. Password length is bounded — P33

No maximum length means a 1 MB password forces argon2 work on a request thread.

`max_length=1024` on every password field — `ChangePasswordRequest`, `LoginRequest`, `SignUpRequest`, `ResetConfirmRequest` — and the same bound on the JSON body middleware, which already exists (§`JSONBodySizeLimitMiddleware`).

### B32. Auth responses are not cached — P34

`/auth/*` and `/account/*` return JSON without `Cache-Control`, except `/me`.

Set `private, no-store` on **every** `/api/v1/auth/*` and `/api/v1/account/*` response — one middleware rule keyed on the path prefix, so a new endpoint cannot forget it.

### B33. One client contract — P37

- **Strip `user_id` from the client projection** in `run_doc.py:400-421`. The client never needs it; the server scopes by it.
- **Align the event key set** between `public_events.py:50` and what the WS actually emits, and make `text` consistently `string | null` rather than sometimes missing.
- Add a test that asserts the exact key set of a run document and of a WS event, the way `test_auth_api.py` asserts `MeOut`'s keys. A contract test is what stops drift.

### B34. One entitlement resolver — U2

`plan_key`, the period, the limits and the units are currently read from `users.plan_key`, the subscription mirror and settings in several ad-hoc places.

One function, `resolve_entitlements(user) -> Entitlements`, is the **only** way to obtain a plan. Every route uses it, including the debate cap, the graph reserve, the verdict retry and `/billing/state`. `users.plan_key` becomes a write-only cache that nothing reads directly.

**The test:** `grep` finds no read of `user.plan_key` outside that function. That is a mechanical, enforceable definition of done.

### B35. Signup abuse controls — report §11.7

The server-side substitutes for a challenge widget, in the order they pay off. Every one sits **at or before** verification, never after it.

| Control | Stops | Where |
|---|---|---|
| Verification gate on every spend path | throwaway accounts consuming units | §B11 |
| Disposable-domain list + MX check | mass signup to `mailinator`-class domains | §B21, before the account commit |
| Per-address + per-network limits | one network farming addresses; one address being mailed | §B22 |
| Free units only **after** `email_verified_at` | scripted signups that never verify | §B11 + `resol` |
| Code send budgets (60 s + 5/h) | mailbox bombing via resend | already designed; §F7 |
| `+tag` normalisation | `a+x@x.com` farming | §B21 |
| Action audit + alerting | detecting a wave after it starts | §C1 |
| `Origin` check in `verify_csrf` | cross-site form-driven signup | §B20 |

**What must not be done:** added friction on the verified path. Once the address is proved, the product feels instant.

### B36. Email leaves the request path — U5

Two mails are sent inline, so a slow provider adds up to ~10 s to signup after the account is already committed, and a client that times out retries into a 409 for the account it just created.

- **Persist then send:** write `email_outbox{id, to, template, payload, status, attempts, sent_at, next_attempt_at}` and process it in a worker with retries, exactly like §B16's payment outbox.
- **Persist `sent_at`** so a lost mail is visible and re-sendable.
- **Add a resend endpoint** for the welcome mail, not only the verification code.
- **Verify the Resend domain** (SPF/DKIM) and set `EMAIL_FROM` to a monitored mailbox, with `Reply-To` as support. Without `EMAIL_API_KEY` the code only logs (§B24.6) — correct in dev, a silent failure in prod, which is why boot refuses to start without it in `prod`.

### B37. Observability for money and auth — U6, U8, report §11.10

One funnel metric set, so the operator can answer "how many signups reached verification, plan choice and an active plan?" without ad-hoc SQL:

```
signup_created · email_verified · onboarding_plan_viewed · checkout_created
webhook_received · plan_activated · plan_activate_latency_p95
```

Plus counters for `email_unverified` 403s, `code_throttled` 429s, `webhook_pending_age`, `reconcile_failures` and `dead_letter_depth`.

- **Alert** when `plan_activate_latency_p95 > 2 min`, or when any `pending` webhook is older than 10 minutes (§B7.3).
- **A read-only operator view** of one account's auth and billing timeline from `audit_log`, so support can answer "did this user verify?" without reading Redis.

### B38. Finish the OAuth work — report §10 addendum, report §10.5

Backend code is written, untested and unmigrated. This section is the gate that makes it real; §C2 is the order.

1. **Review and apply migration `0010_oauth_accounts`** on a scratch database; verify `oauth_accounts` exists and `users.password_hash` is nullable; test the downgrade.
2. **Test state binding and PKCE** — a callback with a missing or mismatched state cookie is rejected (login CSRF, report §11.4 invariant 5).
3. **Test identity parsing** for Google and GitHub: verified / unverified / missing email.
4. **Boot test:** import the app, hit `/api/v1/auth/oauth/providers`, assert the shape.
5. **`ruff check src/auth/oauth.py src/api/oauth_api.py`** — they were never linted.

## 5. Frontend plan
### B39. Payment method, read-only — `src/api/billing_api.py` — `DESIGN_PROPOSAL.md` §8.10 panel 4

```
GET /api/v1/billing/payment-method     (auth, Cache-Control: private, no-store)
{ "card": { "brand": "visa", "last4": "4242", "expiry": "12/2027" } | null,
  "country": "IN" | null }
```

- **A read of what the provider holds, never a write.** The card is changed at Razorpay; the `card` dialog (design §8.13) is a **deep link to the provider's own page**, not a form. Never accept a PAN, a CVV or a raw card object anywhere in this API.
- **`card: null` is a first-class answer** — the design renders *"Add a card"* for it (§8.10 states). An account on the free plan has no card and must not see an empty box.
- **Absent when the provider is unconfigured.** With `billing_enabled=false` the route 404s with `{code: "not_found"}`, and F19 omits the panel with one sentence.
- **No stored card data in Postgres, ever.** `last4`/`brand`/`expiry` are cached display values refreshed from the provider on read; nothing is trusted from the client.

### B40. Invoices — `src/api/billing_api.py` + the `invoices` table — `DESIGN_PROPOSAL.md` §8.10 panel 5

**B18.4 already says the row shape; this item makes it readable.** An invoice the customer cannot retrieve is not an invoice.

```
GET /api/v1/billing/invoices?limit=&cursor=    (auth, private, no-store)
{ "items": [ { "number": "INV-2026-0031", "issued_at": "...",
               "period_start": "...", "period_end": "...",
               "amount": 1000, "currency": "INR", "tax_amount": 180,
               "status": "paid" | "open" | "refunded",
               "download_url": "https://..." | null } ],
  "next_cursor": null }
```

- **`download_url` is minted at read time, short-lived** — the same pattern the export uses (`jobs_api.get_job` presigns on read). Never a permanent public link, never a URL stored in the row.
- **Same pagination as runs** — `{items, next_cursor}`, keyset on `(issued_at, id)` DESC. That is R21's rule applied to the second list surface, so the API does not grow a third pagination style.
- **Rows come from B18.4's write path**; the webhook is the only writer. A refunded charge stays in the list with `status: "refunded"` — the record is not deleted.
- **Owner-scoped, like every other read.** A foreign invoice id is absent, never 403.

---


**The design-plan rule, stated once.** `DESIGN_PROPOSAL.md` owns appearance; this file owns order and behaviour. Every `F` item below is one of two kinds, and it says which:

| Kind | What it does | Where its look comes from |
|---|---|---|
| **Design-bearing** — F4, F5, F7, F8, F9, F11, F12, F14, F15, F17, F18, F19, F20, F21, F22, F23 | adds or changes a visible surface | **cites a DESIGN_PROPOSAL.md section**, and that section is the spec. Do not invent layout at build time |
| **Logic-only** — F1, F2, F3, F6, F10, F13, F16 | (unchanged) changes a type, a guard, a route, a store, an error path | **inherits** the surrounding design; adds no new surface |

The seven logic-only items touch no new pixels: F1 widens a TS interface, F2 adds guard branches, F3 places a route the design already draws, F6 redirects after submit, F10 clears a draft store, F13 stops three states lying, F16 carries `next`. **If an implementer finds themselves styling anything while doing one of those seven, something has gone wrong** — the design for that surface already exists in §8.

**Where the twelve design-bearing items point:**

| Item | Surface | Design section |
|---|---|---|
| F4 | the shared plan card | §8.3 (content anatomy) + §8.18 (outer frame) |
| F5 | `/pricing` honest figures | §8.3 |
| F7 | `/auth/verify` | §8.16 |
| F8 | `/onboarding/plan` | §8.18 |
| F9 | `/onboarding/plan?checkout=return` | §8.18 state 5 |
| F11 | the plan card's four actions | §8.10 |
| F12 | `/overview` truthfulness only | §8.15 (retired — no new design) |
| F14 | enterprise block, legal links | §8.3, §8.4, §8.19 |
| F15 | `/example` | §8.19 |
| F17 | provider buttons | §8.17 |
| F18 | `/method` | §8.4 |
| F19 | `/billing` | §8.10 (+ §8.10 panels 4–5 contracts) |
| F20 | `/auth/forgot`, `/auth/reset` | §8.21 |
| F21 | `/legal`, `/legal/:slug` | §8.20 |
| F22 | account panel 2, password dialog | §8.11 panel 2, §8.13 |
| F23 | stop + remove controls | §8.12 |

### F1. The `User` type finally reads what the server sends — `frontend/src/api/types.ts`

```ts
export interface User {
  …
  email_verified: boolean          // add
  entitlements: {
    …
    onboarding_required: boolean   // add
  }
}
```

`UserOut.email_verified` has been on the wire since the auth work landed (`auth_api.py:84`); the client simply never declared it. This is the smallest change in the plan and it unblocks everything else.

### F2. The guard grows two branches — `frontend/src/auth/guard.ts`

Keep the existing three-state decision and add a pure resolver above it, so it stays DOM-free and testable exactly as `resolveGuard` is today:

```ts
export type GateDecision =
  | { go: 'outlet' }
  | { go: 'signin'; target: string }
  | { go: 'verify'; next: string }
  | { go: 'onboarding' }

export function resolveGate(
  status: AuthStatus,
  user: User | null,
  pathname: string,
): GateDecision
```

Rules, in order:

1. `unknown` → splash (unchanged; never bounce).
2. `anon` → signin with `next` (unchanged).
3. `authed` and `email_verified === false` → **verify**, carrying `next`.
4. `authed` and `entitlements.onboarding_required` → **onboarding**, *unless* already on `/onboarding/plan`.
5. otherwise → outlet.

Two carve-outs that must be explicit, or the app deadlocks:

- `/auth/verify` and `/onboarding/plan` must not re-trigger their own redirect.
- `/account` and `/legal/*` stay reachable while un-verified, so a user can sign out or read the terms.

`RequireAuth.tsx` renders the four cases. The `unreachable` retry path is untouched.

### F3. Onboarding is a sibling of the shells — `frontend/src/App.tsx`

```tsx
<Route element={<RequireAuth />}>
  <Route path="/landing" element={<LandingPage />} />
  <Route path="/onboarding/plan" element={<OnboardingPlanPage />} />   {/* NEW */}
  <Route element={<WorkspaceShell />}> … </Route>
  <Route element={<AppShell />}> … </Route>
</Route>
```

Deliberately **not** inside `AppShell`: the rail offers four destinations and every one of them is the wrong next step. This mirrors the existing `/landing` decision at `App.tsx:75-77` — "a sibling of the shells, so no rail flashes before the account state picks a destination."

Lazy-loaded like every other page (`const OnboardingPlanPage = lazy(() => …)`), so it costs the entry chunk nothing.

### F4. The plan card becomes one component, two callers

`PricingPage.tsx` currently owns the card markup inline (`:230-269`). Extract it, because onboarding needs the identical card with a different action.

```
components/billing/PlanCard.tsx
  props: { plan, currency, action, onAction, busy, badge? }
```

`PricingPage` passes `link → /auth/signup` for anonymous visitors and `button → buy()` for signed-in ones. `OnboardingPlanPage` passes `button → buy()` always. One card, one set of styles, no drift.

**One card, two design sources, and they must not diverge.** `DESIGN_PROPOSAL.md` **§8.3** draws the pricing card as `.plan-option` — *"name, price (`numeral-sm`), a units line, three `plan-facts` rows, and the action"*, action at `margin-top:auto` so all four buttons land on one line. **§8.18** draws the onboarding card as V7's `.plan-card` — `26px 22px 22px`, 10px radius, `.plan-badge` at `top:-11px`. **They are the same component with different shells around it**: the card's *content* anatomy comes from §8.3, its *outer frame* (badge, radius, padding) from §8.18. `PlanCard` takes both, and neither page re-draws the other's part.

### F5. Kill the transacting fallback — `PricingPage.tsx:29-58` (P10)

`PLANS` currently carries `{ INR: 999, USD: 10 }`, `'8,000'`, `'12'`, `'4'` as a render-time fallback **with live buy buttons**. A user can be shown one number and charged another.

Replace with:

- `plans: BillingPlan[] | null`, initial `null`.
- While `null`: skeleton cards, **no price, no CTA**.
- On fetch failure: a ruled "Pricing unavailable — try again" panel, CTAs absent.
- The `RULES` copy block (`:116-120`) is static prose and may stay; prices and limits never are.

The same rule applies to the enterprise block's `ENTERPRISE_ROWS`.

**Design source: `DESIGN_PROPOSAL.md` §8.3**, which already specifies the honest-pricing rules this item enforces — *"`[config]` cells come from plan configuration, never from constants"* and *"a price that appears nowhere in configuration does not appear on the page"*. F5 is the implementation of §8.3's two rules, not a separate policy. The three states F5 names (skeleton, unavailable panel, loaded) map to §8.14's S6 / S7 / S4 for the pricing page.

### F6. Sign-up routes to verification — `SignUpPage.tsx:70-72`

```ts
await signup(...)
const dest = safeNext(params.get('next'))
setRedirectTo(user.email_verified ? dest : `/auth/verify?next=${encodeURIComponent(dest)}`)
```

OAuth returns already verified, so the provider path skips straight to onboarding. Password sign-up always visits verify first.

### F7. The verification screen grows the code form — `VerifyEmailPage.tsx`

Keep the `?token=` link handling exactly as it is (`:103-133`); add alongside it:

- The address, from `authStore`, so the user knows which inbox.
- A 6-digit input — `inputMode="numeric"`, `autoComplete="one-time-code"`, `maxLength={6}`, monospace, letter-spaced.
- **Confirm** → `authVerifyCodeConfirm(code)` → `setUser(verified)` → `next`.
- **Resend** with a 60 s countdown, then "Send a new code"; `429` shows the server's wait, not a client timer guess.
- **"Use the link instead"**, which is what already exists.
- Error copy for `invalid_code`, `code_throttled`, `code_attempts_exhausted` — each its own sentence, not one generic "wrong code".

This is the one screen where the prototype has nothing to offer: **V7 contains no verification view at all** (`data-site` is one of `landing|pricing|method|signup|signin`; no verify page, and V7's signup copy says *"this preview creates the account on this page; nothing leaves it"*).

**The design is now written: `DESIGN_PROPOSAL.md` §8.16.** Build to it exactly — the `.auth-grid` split, V7's `.field` ruled baseline (1.5px graphite, no box, 2px accent on focus), the mono code field, the 48px primary action, and the six named states. Those values are quoted from `DESIGN_PRODUCT_V7.html:161-167` and `:1657-1670`, so this screen matches V7's language even though V7 never contained it. Do not invent a layout at implementation time.

**Why this screen is not optional (the verification window the owner asked for).** It is the *only* place a user can satisfy the gate that `deps.py:150` already enforces on five spend routes. Ship F7 no later than B11 or every new account is locked out of ingest and debate with no way forward. See §3.1 and §14.5.6.3.

### F8. Wallet: the onboarding screen — `pages/OnboardingPlanPage.tsx` (new)

**Reads:** `GET /billing/state` only. No `PLANS` constants on this screen, ever.

**The design is written: `DESIGN_PROPOSAL.md` §8.18.** Build to it. The card is V7's `.plan-card` **verbatim** — 10px radius, `1px solid --panel-line`, `26px 22px 22px` padding, `16px` internal gap — with the badge absolute at `top:-11px; left:22px`, and the card's button at **44px** with **4px** radius. The r-2 card radius and the r-1 button radius never cross.

**Layout** — one column, max ~720px, centred, no rail (wider than 560px because two cards must sit side by side at `.plans-grid`'s 14px gap):

| Band | Content | Design source |
|---|---|---|
| Head | "Choose how you start." + one lead line | V7 `.page-head` — `border-bottom:1px solid --record`, `padding-bottom:22px`, h1 `clamp(30px,2.4vw+10px,40px)` |
| Cards | Starter, Studio — `PlanCard` from F4 | V7 `.plan-card` (`:1773-1791`), quoted in §8.18 |
| Badge | "Recommended" on Studio only | V7 `.plan-badge` — mono 10px uppercase, `--graphite` pill, `top:-11px` |
| Free | One ruled line: "Start free — {plan_free_units} units, no card." + **Continue free** | `border-top:1px solid --hairline`, `.rule-note` + `.btn-secondary`. No fourth card unless D2 says so |
| Rules | The three existing `RULES` lines from `PricingPage` | reused verbatim, so the two pages cannot disagree |

**States:**

1. `loading` — skeleton cards, no prices.
2. `error` — "Couldn't load plans." + retry + **Continue free still enabled**. A server outage must never trap a user behind a paywall.
3. `idle` — the three choices.
4. `busy` — the chosen card's button reads "Opening checkout…", siblings disabled.
5. `return` (see F9).

### F9. The return state — `DESIGN_PROPOSAL.md` §8.18 state 5

On `?checkout=return`, the cards are replaced by a **ruled status ledger** — V7's `.ledger-row` / `.double-rule` / mono figures, never a spinner. **The design is written in `DESIGN_PROPOSAL.md` §8.18, state 5**; build to it rather than to this paragraph.

**The behaviour this item owns — the part the design cannot specify:**

- Poll `GET /billing/state` every 3 s for ≤ 90 s.
- `status === "active"` → reveal **Open the dashboard**, then `POST /billing/onboarding/complete {choice:"paid"}`, `authMe()` to refresh the store, then `/landing`.
- `pending` / `authenticated` → *"Payment received. Your plan activates shortly."* — never an error, never "failed".
- Timeout → stop polling, keep **Check again** and the support mailto. Still not an error.
- `history.replaceState` strips `?checkout=return` so a refresh does not re-poll.

**The rule this screen must obey:** it reports the server's state and never infers one. A false "upgraded" is worse than an honest wait.

### F10. Clear the stale snapshot — P29

After checkout, cancel, or onboarding completion, call `authMe()` and adopt the result. Today `AccountPage.tsx:79-89` and `SocietyPage.tsx:64` render login-time values, which is how one app ends up showing two different plans. `AccountPage` should read `/billing/state` for the plan block and keep `user` only for email/role.

### F11. `PlanUsage` stops guessing — P14

`LIVE_STATUSES` and `planAction()` (`:18-26`) are deleted. The card renders `subscription.action` from `/billing/state`:

| `action` | Rendered |
|---|---|
| `cancel` | "Cancel plan" |
| `scheduled` | "Ends on 30 Dec" + "Resume" |
| `choose` | link to `/pricing` |
| `resume` | "Resume plan" |

`created` and `paused` now say something true instead of routing the user into a 409.

**Design source: `DESIGN_PROPOSAL.md` §8.10**, which owns the four actions and their words. §8.10 specifies the plan ledger's action states — *"the current plan is marked three ways: the chip 'Your plan', the `--accent-soft` strip at the top of the card, and its action replaced by a state"* — and names the cancel flow as a dialog that says what stops, what stays and what is charged. **F11 must use §8.10's words, not the table above**: the table is the mapping from `subscription.action` to behaviour, §8.10 is the copy and layout. Where `PlanUsage` (the Overview card) and `/billing` (the ledger) both show a plan, they show the same four actions from the same server field.

---

### F12. The Overview stops inventing numbers — P30

`OverviewPage.tsx:169-210` derives "25 answers filed", corpus rows joined **by name** (`corpusRows.ts:21-35`) and a permanent `convergence: null` from whatever the client happens to hold.

- **A server aggregate endpoint** (`GET /api/v1/overview`) returns the counts it can actually count. No count is computed on the client from a page of results.
- **Join corpora by `dataset_id`**, never by name. A name match is a guess and it will match the wrong dataset the first time two are called "Q3".
- **Read convergence from run events**, not from a client placeholder.
- If a number is not available, the page says "Not yet" — never `0`, and never a leftover from the last render.

**This is a truthfulness fix on a page that is being retired — and both documents must say so.** `DESIGN_PROPOSAL.md` §8.15 retires Overview: *"not part of V7 and has no equivalent in it… the route stays until Documents, Runs, Verdict and Billing pass §10 in the browser, and it is removed after that. Nothing in this proposal rebuilds it."* So F12 is **not** a rebuild and must not become one: it stops the page **lying** while it still exists. Two consequences the design and this plan agree on:

- `GET /api/v1/overview` is a **temporary endpoint with the same lifetime as the route.** It is added to the route contract under a **removal condition**: it is deleted in the same change that deletes `OverviewPage.tsx`. It carries no design and gets no design section — the design never specifies its panels, only that the numbers must be true.
- **No new visual work lands on Overview.** F12 changes what a number *is*, never how a panel looks. Anything that would restyle it is out of scope; the page is on its way out.

### F13. The wizard tells the truth about its own state — P31, P9

Three defects, one component.

1. **The draft store reuses the previous dataset's job ids.** `draftStore.ts:53-54` keeps `ontologyJobId`/`graphJobId` across `setDatasetId`, so the UI can report "map built" without a build ever running. **Null every job id on `setDatasetId`**, and reset the document list when a new map starts.
2. **Removing a card is local-only.** `DELETE /uploads/{id}` exists and is never called, so the row and the object both stay. Call it from `removeDoc`, and handle its failure by restoring the card rather than pretending it went away.
3. **The run form submits caps from the stale snapshot** and the server answers `403 plan_limit_exceeded`. Submit **no** caps; let the server clamp (`debate_api.py:634-657`) and log the clamp. A form that pre-clamps is a second source of truth.

### F14. Nothing transactional is hardcoded — P38

`PricingPage.tsx:60-66,284-302` hardcodes the enterprise copy, the unit figures, the legal links and a `mailto:`. `legalLinks.ts` hardcodes the same links again.

- **Enterprise copy and units render from server settings** — `plan_enterprise_units`, the price label, and the contact address from `LEGAL_CONTACT_EMAIL`.
- **Legal links come from the legal registry** (`/api/v1/legal/documents` already exists, §`legal_api.py`), so a renamed or added document does not need a deploy.
- A `mailto:` is only rendered when the address is configured; otherwise the contact line is omitted rather than showing a dead link.

**Design sources:** `DESIGN_PROPOSAL.md` **§8.3** (the pricing page's `[config]` rule and the traceability rule), **§8.4** (the Method page's legal read, D9), and **§8.19** (the worked example's "no fabricated claim" rule). F14 is the same principle applied to three more surfaces, so it cites the sections rather than inventing a fourth wording.

### F15. A public worked example — report §11.1

A visitor has no public sample of what an account unlocks, and asking them to sign up to find out is the highest-friction ask in the funnel.

Add a public route `/example` that renders **one authored filed decision** through the existing `VerdictSheet`, labelled "Worked example" exactly as the marketing page labels its examples.

**The design is written: `DESIGN_PROPOSAL.md` §8.19.** Build to it exactly — the `.site-wrap` column, the `.sheet` at 760px with its **8px** radius (`.sheet` uses `--r-2`; this is the one page where the sheet radius is the right one), `.sheet-q`/`.sheet-pos-row`/`.sheet-numeral`, the `.tape` with its 0.80 threshold rule, `.dissent`, and the `.rule-note` footnote. Those values are quoted from `DESIGN_PRODUCT_V7.html:331-351` and `:1496-1503`.

**Three rules the design makes binding, and each is testable:**

1. **The "Worked example" label appears three times** — sheet head, page lead, footnote — because a screenshot of this page travels without its context.
2. **The page is static**: no fetch, no session, no loading state, no failed state. The page that proves the product must not depend on the product being up.
3. **Its figures must be internally consistent** with the documented weighting: the per-pass shares average to the filed figure, and the position counts sum to the roster. A worked example whose arithmetic does not close teaches the wrong thing.

- **Copy, not machinery.** The sheet component, the position marks and the tape already exist; the page is a route plus one authored typed constant.
- **It carries the same label as every other example** (`PRODUCT.md:130`, the copy law — the only surviving authority on copy) and no "real customer" claim.
- **Linked from three places**: the landing hero's secondary action and section 7, the pricing page under the cards (§8.3), and the Method page's threshold row (§8.4). Those links are specified in the design sections, so F15 also touches `marketing/Hero.tsx`, `PricingPage.tsx` and the new `MethodPage.tsx`.
- **Banned on the page:** any real company, person, logo or quotation; the words *sample*, *demo*, *preview*, *mock*; a second example; a sign-up wall over the content.

### F16. `next` survives both login paths — report §11.2

`signInTarget` encodes the destination for password login; after **OAuth** the destination comes from the server-stored `next`. The two are consistent only if the frontend passes `next` on the OAuth start URL.

- **Pass `next` explicitly on every OAuth button**, so a deep link (`/runs/<id>/verdict`) round-trips identically through password and provider login.
- **Test both paths to the same destination:** one password login and one OAuth login, both landing on the deep link they started from.

### F17. `OAuthButtons` — the component the plan assumed — `components/auth/OAuthButtons.tsx` (new)

**Why this item exists.** §C2 reason 4 says *"the frontend cannot … start OAuth"* and closes it with §F7 + §F6. Neither builds a provider button, and `OAuthButtons` appears in this plan only once — as a checklist noun in §C2.2 step 5, as though it were already shipped. It is not: `grep OAuthButtons frontend/src` is **0 hits**. Without this item, `GET /auth/oauth/providers` and `/oauth/{provider}/start` stay unreachable, migration `0010` buys nothing, and a configured provider still never appears. That is R41/R42 in §14.5.6.1.

**Reads:** `GET /api/v1/auth/oauth/providers` → `{github: boolean, google: boolean}`. Render **only** the configured ones, so a deployment with no credentials shows nothing rather than a dead button. This is a request, not a build-time constant: the answer changes per deployment, never per release.

**Behaviour:**

- Each button is an `<a>` to `/api/v1/auth/oauth/{provider}/start?next=<safeNext>`, **not** a fetch — the server answers with a redirect to the provider, and a full navigation is the point (the `oauth_state` cookie must ride the top-level request). Do not open it in a new tab.
- `next` is `safeNext`ed on the client before it enters the URL, and re-validated on the server (F16). One validator, both ends.
- Label each with the provider name (`Continue with GitHub`), verb-first, matching the copy law.
- Hidden entirely when the fetch fails: a provider list that will not load must not block the password form beside it.

**The test that stops the old behaviour recurring:** `SignUpPage.test.tsx:23` currently asserts *"offers no social sign-in until a provider is configured"* and passes **vacuously** — no component reads `/providers`, so the buttons can never appear *even after* an operator configures one. Rewrite it to mock `/providers` twice: empty → assert no buttons; `{github: true}` → assert the GitHub button and its `?next=` round-trip. The gate must be data-driven, not hardcoded.

**Placement:** inside `AuthLayout`, above the email field, separated by a rule, on both `SignInPage` and `SignUpPage`. Not on `VerifyEmailPage`.

**The design is written: `DESIGN_PROPOSAL.md` §8.17.** Build to it exactly. The button is V7's `.btn-secondary` at `min-height:48px` (matching `.auth-form .btn`), `border-radius:4px`, `border:1px solid --record`, full width, 16px icon with an 8px gap; the group is a `grid` with `gap:10px`; the separator is a `1px --hairline` rule with a centred `.hint`. Those values are quoted from `DESIGN_PRODUCT_V7.html:131-142` and `:1657-1670`.

**V7 has no equivalent — and that is a warning, not a blank cheque.** `DESIGN_PRODUCT_V7.html` contains no OAuth markup: zero occurrences of `GitHub`, `Continue with`, `oauth` or `provider`; the two `Google` hits are a verdict-export link, not a sign-in button. So V7 cannot say what these buttons look like. Do **not** invent a new visual idiom for them, and do **not** let them dominate the password form (which remains the primary path per V7's *"An email and a password. No more."*).

**The conditional-render rule that keeps V7's zero-config appearance exact.** With no provider configured — the default, since `OAUTH_ENABLED` is false (plan D5) — the block, the rule **and** the "or with your email" line are all absent, so sign-up looks exactly as V7 draws it. A skeleton is never shown while `/providers` loads.

### F18. The Method page — `pages/MethodPage.tsx` (new) — `DESIGN_PROPOSAL.md` §8.4

**Why it is in this plan at all.** The design specifies `/method` in full (§8.4) and the landing and pricing pages link to it, but **no plan item builds it** and `frontend/src/pages/` has no `MethodPage.tsx`. It is a route the design and the copy both reference and the code cannot serve — a dead link the day F15's "How a panel is checked" button ships.

**It is nearly static.** No fetch, no session, no account data: six definitions and one inline tape. That is the design's whole point (§8.4: *"a page about the mechanism must not depend on the account"*), and it is why the page can be built without any backend work.

- **Form:** one column of `min(704px, 100%)`, six `.method-row`s on a `140px | 1fr` grid, `--hairline` separators, a `--graphite` rule above the first. No imagery, no tabs, no cards.
- **The threshold row carries the worked example** — the tape with its 0.80 double rule, inline. `ConvergenceTape` exists; reuse it, do not re-create it.
- **Copy is owner-blocked on two paragraphs** — the plain-language weighting paragraph and the "not an adviser" line need the owner's wording and a legal read against the Legal pages (**D9**). **Build the page with the four mechanism rows and the tape; hold the two blocked paragraphs behind D9** rather than inventing copy, which §9.2 forbids.
- **Route:** `/method` in `App.tsx`, inside `MarketingLayout` beside `/` and `/pricing`.
- **Linked from:** the site header and footer (§8.2 rule 5) and `/example`'s secondary action (§8.19).

### F19. The Billing page — `pages/BillingPage.tsx` (new) — `DESIGN_PROPOSAL.md` §8.10

**Why it is in this plan at all.** The design specifies `/billing` in full (§8.10) and the account popover links to it (§8.5 gives the rail three items, not four), but `frontend/src/pages/` has no `BillingPage.tsx`. Today `PlanUsage` is a **component inside `OverviewPage`** — the plan's own §1.3 records this. So the plan's B4 (`GET /billing/state`) has no consumer until this page exists, and F11 ("`PlanUsage` stops guessing") has no home.

**It consumes TWO contracts, not one — and the earlier draft of this paragraph was wrong about that.** §8.10 has six panels. **Four** of them (this period, what the units bought, the plans, the cancel/change action) come from `GET /billing/state` (B4). The other **two** — payment method and invoices — are *not* B4 fields, and pretending otherwise is what hid the gap below:

- **Panel 4, Payment method** needs `GET /api/v1/billing/payment-method` (**B39**).
- **Panel 5, Invoices** needs `GET /api/v1/billing/invoices` (**B40**), whose rows **B18.4** already persists.

Neither endpoint is in B4 and neither existed in this plan before this correction. **If B39/B40 are deferred, F19 ships four panels and the other two are omitted with a sentence** — never mocked (`DESIGN_PROPOSAL.md` §8.10).

- **Reads `GET /billing/state` for panels 1–3 and 6, plus `GET /billing/payment-method` (B39) for panel 4 and `GET /billing/invoices` (B40) for panel 5.** No `PLANS` constant, no hardcoded unit count, and **no invented card digits or invoice rows** — a panel whose endpoint is absent is omitted with one sentence.
- **The invoice download is a short-lived signed URL minted at read time** (B40), opened directly; never a permanent link, never a PDF regenerated per click.
- **`subscription.action` drives the controls** — `cancel`, `scheduled`, `choose`, `resume` — and the client never switches on a status string. That is B4's whole purpose and P14's fix.
- **Reuse the plan card from F4** for the plans panel, so `/pricing`, `/onboarding/plan` and `/billing` cannot drift.
- **States:** S6 loading, S7 failed (a billing outage shows the last known figures with a stale marker, never zeros), S8 partial, S9 free, S10 paid, S11 payment problem, S12 at the limit, S13 restricted.
- **Route:** `/billing` in `App.tsx` inside `AppShell`. **It is NOT a rail item** — `DESIGN_PROPOSAL.md` §8.5 gives the rail exactly three: Documents, Runs, Verdict. Billing is reached from the **account popover**, which §8.5 specifies as *"name, email, plan and price, a units meter, payment method, next charge, then links to Billing, Account settings and Sign out"*. Put the link there. A fourth rail item would be a design change and is not in this plan.
- **Sequencing:** F19 depends on **B4** (the contract) and **F4** (the shared card). It does not depend on B5/B7 (the payment loop), so it can ship showing correct read-only state before checkout returns work.

---

### F20. Password recovery — `pages/ForgotPasswordPage.tsx` + `pages/ResetPasswordPage.tsx` — `DESIGN_PROPOSAL.md` §8.21

**Why it is in this plan at all.** The backend has had `POST /auth/reset/request` and `/reset/confirm` all along, and both pages exist in `frontend/src/pages/` — but **neither design file nor this plan ever specified them** until §8.21 was written. A customer who forgot a password had a route, a page and no spec, which is how a page drifts into whatever the last person typed.

**Both pages are `AuthLayout` with no aside**, at V7's `.auth-col` width (`min(430px,100%)`) — recovery is a two-step errand, not a sales moment.

- **`/auth/forgot`** — one email field on V7's ruled baseline, **Send the link** at 48px. On submit, **always** the same sentence: *"If that address has an account, a link is on its way."* The page must never reveal whether an address exists; the server already answers 202 for both cases and the copy has to match it.
- **`/auth/reset?token=…`** — new password + confirm, both on the ruled baseline, separated by `.auth-form`'s 18px gap. `POST /reset/confirm` returns 204 and revokes the other sessions; then `authMe()` and `safeNext`, so the user lands where they were going, already signed in.
- **Six states each** (idle, submitting, invalid, expired, 5xx, and the token-less landing): never clear a typed password on failure; an expired token routes back to `/auth/forgot` rather than dead-ending.
- **The token never reaches a header or a log.** It rides the URL once and posts once.
- **Banned copy:** *forgot*, *invalid token*, *credentials*, *OTP*. The design's words are in §8.21.

**This unblocks a real dead end**, so it is not deferrable behind the journey work: any account that forgets its password today has no designed way back in.

### F21. Legal pages — `pages/LegalIndexPage.tsx` + `pages/LegalPage.tsx` — `DESIGN_PROPOSAL.md` §8.20

**Why it is in this plan at all.** `GET /legal/documents` and `/{slug}` exist, the footer links to them from every page, and signup records consent against their `content_sha256` — but the design had no section for the pages that serve them. The one surface with a **legal** obligation was the one left unspecified.

- **Both pages are V7's `.method` idiom** (§8.4): one column, `margin-label` head, `--ink-3` metadata, `--hairline` rules, no cards, no imagery. They are the same object, so they share it.
- **The version and effective date are always shown.** A customer must be able to see *which* version they are reading, because that is the version their consent points at.
- **Content is served, never bundled** — a copy change is a server publish, not a deploy. A failed fetch says so; **never render a cached legal text**.
- **`/privacy`, `/terms`, `/refund` are permanent redirects** to `/legal/:slug`, kept because those addresses are in the footer, in mails and in old links.
- **The re-consent band (§8.20)** belongs to this item: when a published `content_sha256` differs from the version the account accepted, a **`.reader-banner`** strip above `.content` on every authed page says what changed, links to the document, and offers **Accept** → `POST /api/v1/legal/consent`. That closes **R43**, which recorded the endpoint as orphaned.
- **Print cleanly.** `@media print` hides the shell chrome; no dark surfaces, no gradients.
### F22. Account panel 2 — password and sessions — `pages/AccountPage.tsx` — `DESIGN_PROPOSAL.md` §8.11 panel 2, §8.13 `password` dialog

**Why it is in this plan at all.** §8.11 panel 2 specifies the whole surface — *"the password line and its action, then `.session-row`s: device, browser, when, and a Sign out per session"* — and §8.13 specifies the `password` dialog. **No plan item delivered either.** The backend has `POST /auth/password`, `GET /auth/sessions` and `DELETE /auth/sessions/{id}`; the design has the panels; the join is this item.

- **The password row states its current value in text** — *"Password · Last changed 12 Sep 2026"* + **Change password** (§8.11's rule: a settings row states its value in text, not in a control's position). The dialog is §8.13's: current password, then the new one twice.
- **`POST /auth/password` returns 204 and revokes every other session** (B15). The copy says so before the action, not after.
- **The session rows** are `.session-row`s: device, browser, when, and **Sign out** per row. `DELETE /auth/sessions/{id}` revokes one. A revoked row leaves immediately; the current session's row says *"This device"* and carries no Sign out.
- **B15 lands in the same phase**, so the UI is never built against the old `SessionOut` shape — it is built once, against `public_id`.
- **States:** S6 loading, S7 failed per row (a failed revoke restores the row and says why), S8 partial. Never show a session list built from guesswork: if the read fails, the panel says so.
- **Closes R38 (change-password) and R39 (session list/revoke).**

### F23. Stop a decision, and remove material — `components/workspace/*`, `pages/IngestPage.tsx` — `DESIGN_PROPOSAL.md` §8.12

**Why it is in this plan at all.** §8.12 now specifies both controls, and both have backend routes nothing calls: `DELETE /api/v1/jobs/{id}` (**R44**) and `DELETE /api/v1/uploads/{id}` (**R37**, partly covered by F13.2).

- **Stop this decision** — a `.btn-ghost` in the `.ws-flow` head, opening §8.13's `stopped` dialog: what stops, what is kept, danger-tone confirm. Then `DELETE /api/v1/jobs/{id}` and the flow pane reflects the stopped state. **It is a dialog, not a one-click button**, because a run costs units.
- **Remove** — one control per material row in `?step=ingest`, revealed on hover/focus, confirming inline (not a dialog per row). Then `DELETE /api/v1/uploads/{id}`; on failure the row is **restored** and the reason shown. **No undo toast** — a toast that said "Undone" would claim something the backend does not honour.
- **Neither control appears while the flow is read-only** — a finished decision has nothing to stop, and its material is baked into the map.
- **F13.2 and F23 overlap deliberately on the remove path.** F13.2 is the state-truthfulness fix (the draft store must not claim a removal it did not make); F23 is the control itself. Ship them together or the row will lie for one phase.
- **Closes R44**; completes **R37**.

## 6. Route and URL structure — the production-grade contract


**This section is an addition, not an audit finding.** `REPORT.md` is a backend audit and contains no finding on API or frontend route shape. The owner asked for it directly, and the code has real defects here that nothing else on record describes.

### 6.1 The frontend route tree

Three addressing schemes currently coexist for the same concept — "which part of this page am I looking at":

| Surface | Scheme today | Example | Verdict |
|---|---|---|---|
| Run tabs | **path segment** | `/runs/abc/verdict` | **correct** |
| Workspace steps | **query parameter** | `/new?step=ingest` | **convert to a path** |
| Landing sections | **fragment** | `/pricing#compare` | **correct** for scroll |

**The rule, applied uniformly:**

1. **A path segment when it changes what resource you are looking at.** It must survive a reload, a share, and the back button. Tabs on a run are the canonical case: `/runs/:runId/:tab`.
2. **The bare path when it is the destination itself.** `/runs`, `/documents`, `/billing`.
3. **A fragment only for scroll position within one page** (`#compare`, `#how`), because a fragment is resolved client-side after load and cannot carry an identity.

**A fragment is the wrong tool for a tab, and this is worth stating because it looks right:** `/runs#verdict` has no run id, so it is not shareable and it cannot survive a reload into the right run. The path segment carries the identity; the fragment cannot.

**What already upholds the rule.** `RunPage.tsx:59` navigates `\`/runs/${runId}/${key}\``, routed at `App.tsx:88` as `/runs/:runId/:tab`; `:300` redirects a bare `/runs/:id` to a smart default. Two details the plan requires everywhere:

- **Label ≠ slug.** `TAB_LABELS` shows "Report" while the path stays `verdict`, and "Record" while the path stays `artifacts`. Renaming UI copy must never break a URL.
- **Real tablist semantics.** `SectionNav.tsx:119-147` sets `role="tab"`, `aria-selected`, `aria-controls`, and the panel names itself back with `aria-labelledby`.

**What must change:**

1. **Workspace steps become path segments.** `/new?step=ingest` → `/new/ingest`, and alike for `graph`, `society`. The alias routes at `App.tsx:84-86` (`/new/ingest` → `/new?step=ingest`) **already exist** and simply become the real routes; `?step=` becomes a deprecated redirect that logs one warning. This deletes three redirect routes and one addressing scheme.
2. **Landing fragment ids are documented and stable.** `#how`, `#compare`, `#enterprise-band`, `#questions` — one list, in the spec, so copy edits cannot silently rename them.
3. **`/demo-home` is retired.** It duplicates the landing page's section ids (`HomeDemo.tsx` and `Hero.tsx` both define `how-it-works`, `answer`, `questions`), so nothing may ever render both in one document.

### 6.2 The API surface

| Defect | Evidence | Fix |
|---|---|---|
| **Every main router is mounted twice** — bare legacy path *and* `/api/v1` — so `/api/v1` is decorative and the old surface never sunsets | `api_server.py:325-333`, `:1044-1050` | Mount once under `/api/v1`. Keep the legacy aliases as **explicit redirects** with a deprecation log, scheduled for removal, not as a second mount of the same router |
| **Version location is inconsistent** — some routers carry `/api/v1` in their own prefix, others get it from `include_router`, and `/operator` + `/jobs` carry none | `auth_api.py:34` vs `api_server.py:329` vs `operator_api.py:18` | **Every router declares its full prefix itself.** `include_router` never adds one. One grep must find every path |
| **Two pagination contracts** — Runs is cursor-based; `/ingest/documents` is `limit`-only with no cursor, so paging is unstable | `debate_api.py:806` vs `ingest_api.py:303` | `/ingest/documents` gains `cursor`, returning the same `{items, next_cursor}` as runs |
| **No idempotency key on the public write routes** | — | `Idempotency-Key` on `checkout` and `onboarding/complete` (§B8 supplies the same key for the provider call) |
| **`/docs` and `/openapi.json` public in every environment** | `api_server.py:280-285` | §B24.5 |
| **The public API title is misspelled** | `api_server.py:281` — `title="Socirty Simulator API"` | `"LarkVision API"` |

**The route contract, once:**

```
/api/v1/auth/*        accounts, sessions, verification, oauth
/api/v1/billing/*     plans, usage, state, checkout, subscription, webhook, onboarding,
                      payment-method (B39), invoices (B40)
/api/v1/legal/*       documents, consent
/api/v1/account/*     deletion, export
/api/v1/overview      TEMPORARY — F12's aggregate; deleted with OverviewPage.tsx (§8.15)
/api/v1/ingest/*      files, url, documents
/api/v1/uploads/*     list, delete, preview
/api/v1/simulate/*    debate, debates, graph, stream (WS)
/api/v1/jobs/*        job read, cancel
/operator/*           role-guarded, never versioned, never in the public OpenAPI
/health, /ready       unversioned infrastructure endpoints
```

**The three rules that make it enforceable:**

1. **One mount per router.** A router appears in `api_server.py` exactly once.
2. **A router owns its full path.** `include_router` is called with no `prefix`.
3. **`/operator` is excluded from the public OpenAPI schema** (`include_in_schema=False`), because a documented admin surface is a reconnaissance win.
4. **The contract is tested.** A test asserts the exact sorted set of registered paths, so a new route cannot appear unnoticed and a removed one cannot linger. This is the route-layer equivalent of the `MeOut` key test in §B33.
5. **Deprecation is a redirect with a log, never a second mount.** Two mounts means two contracts to keep.

### 6.3 What `REPORT.md` did and did not say about this

Stated plainly, so no credit is misassigned:

- **The audit has 0 findings on routing.** Zero mentions of dual-mount, pagination shape, error envelope or deprecation across all 916 lines.
- **It has 1 route-adjacent finding:** P36 (`/docs` and `/openapi.json` public), which §B24.5 closes.
- **The error contract and cursor pagination already exist and are correct** (`errors.py`; `run_doc.py:509-561`). Both are **undocumented in either file**, which is why this section records them: an undocumented invariant is one refactor away from deletion.

## 7. How V7's design transfers — concrete mapping

The prototype's language is mostly already the repo's language. The differences are named below rather than "made to match".

| V7 (prototype) | Repo equivalent | Action |
|---|---|---|
| `.plan-card` — 10px radius, 1px border, inset ring when recommended | `article` `rounded-xl border border-hairline bg-paper p-8`; featured uses `bg-[image:var(--gradient-marked)] shadow-sheet` | **Reuse the repo's**, add the ring only if D1 keeps both accents calm |
| `.plan-badge` — dark pill, `position:absolute; top:-11px` | no equivalent | **Add.** `rounded-full bg-ink px-2.5 font-mono text-micro uppercase tracking-[0.08em] text-on-accent` |
| `.price` — `clamp(34px,3vw,44px)` mono tabular | `tnum font-mono text-[56px] leading-none tracking-[-0.05em]` (`PricingPage.tsx:238`) | **Keep the repo's 56px.** It is the established display numeral. |
| `.plan-label` — mono uppercase, letter-spaced | `font-ui text-label uppercase tracking-[0.1em] text-ink-3` | already identical in intent |
| `.plan-list` with check ticks | no equivalent on pricing | **Add**, with `CheckCircle` from `@phosphor-icons/react` (already a dependency, used in `Rail.tsx`) |
| `.cmp-table` — ruled comparison, stacks below 767px | none | **Add** to `/pricing`. `<table>` at `md+`, per-plan `<dl>` below — V7's stacking, in repo markup |
| `.rule-note`, `.compare-hint` — mono footnote | `font-mono text-micro text-ink-3` | identical |
| Ledger rows + double rule (billing panels) | `DefinitionList`, `border-rule` | reuse |
| Convergence tape | the app's real tape, already built | **do not** re-create for marketing |
| Hash routing, hardcoded `$10` / `₹999` / `8000` | React Router + `/billing/plans` | **discard** — this is P10 |

Two things in V7 must **not** cross over: its `#2D3F9C` accent (D1) and every hardcoded number (F5).

---

---

## 8. Deployment gates, the operator view, and the decisions this plan adds

### C1. Stage 9 — what the operator must be able to see — report §11.10

Today the operator cannot answer "how many signups reached verification, plan choice and an active plan?" without ad-hoc SQL, and a silent revenue leak looks exactly like normal traffic.

**C1.1 The funnel.** One metric set (§B37), one panel, one alert. The five numbers that matter: `signup_created` → `email_verified` → `onboarding_plan_viewed` → `checkout_created` → `plan_activated`, plus `plan_activate_latency_p95`.

**C1.2 The silent failures, made loud.** Payment dispatch failures return `200` today (`billing_api.py:395-399`), reconcile failures are log lines, and `pending` webhooks have no age metric. Each becomes a counter and an alert (§B7.3).

**C1.3 A read-only account timeline.** One screen per account, read from `audit_log`: signup, verification, code sends, plan choices, checkouts, webhook receipts, plan changes, cancels, refunds. Support can answer "did this user verify?" without reading Redis, and **nothing on it is mutable** — it is a view, not an editor.

**C1.4 The dead-letter view.** Outbox rows with `status='failed' AND attempts >= N`, with a retry action. This is what turns "a webhook was lost" from an invisible incident into a one-click repair (§B16).

### C2. The deployment gate — §10.4, §10.5

`REPORT.md` §10.4 says in terms: **"Do not deploy this tree."** Nine specific reasons, every one still true. This is the gate that must pass before *any* of this plan reaches an environment.

**C2.1 The nine reasons, and what closes each.**

| # | Why the tree must not deploy | Closed by |
|---|---|---|
| 1 | `MeOut` has `email_verified`; the auth test asserts the exact old key set and will fail | §B11 — update the test, report §11.4 |
| 2 | `require_email_verification` defaults true but `tests/conftest.py` never sets it false, so DB tests create unverified users and get 403 | §B11 — add `REQUIRE_EMAIL_VERIFICATION=false` to conftest plus one true-gate test |
| 3 | `ingest_url` is ungated, so enforcement is inconsistent | §B11 |
| 4 | The frontend cannot enter or resend a code and cannot start OAuth | §F7, §F6 |
| 5 | OAuth credentials and redirect URIs do not exist in `.env`, so the buttons are untestable | §B38, §B24.6 — **DEPLOY** |
| 6 | Migration `0010` has never been reviewed or applied; `oauth_accounts` does not exist in any database | §B38 — **DEPLOY** |
| 7 | `src/auth/oauth.py` and `oauth_api.py` have never been linted or boot-tested | §B38 |
| 8 | No test for state binding, PKCE, identity parsing, code throttling or the gate | report §11.4, report §11.5 |
| 9 | `.env` has no `EMAIL_API_KEY`, so code mail is a log sink | §B24.6 — **DEPLOY** |

**C2.2 The completion checklist, in order (§10.5).** Reproduced because the order is the point:

1. **Migration** — review `0010_oauth_accounts.py`, `alembic upgrade head`, verify `oauth_accounts` and nullable `password_hash`, test downgrade on a scratch DB.
2. **Tests** — `REQUIRE_EMAIL_VERIFICATION=false` in conftest, a dedicated true-gate test asserting 403, `test_auth_api.py` keys updated.
3. **Finish gating** — `ingest_url` gated; enumerate every router and assert spend routes depend on the gate and reads do not.
4. **Backend tests** — code issue/redeem/limits with a fake Redis; OAuth identity parsing; state/PKCE; link/create; callback error redirects.
5. **Frontend** — `User.email_verified`, `rest.ts` calls, `OAuthButtons`, the code form, the guard redirect, signup/signin redirects, error copy.
6. **Config** — OAuth vars in `.env.sample`, real values, both redirect URIs registered, Resend domain verified.
7. **Boot + lint** — `ruff check`, import the app, hit `/api/v1/auth/oauth/providers`, run the targeted auth suites.
8. **Manual provider test** — GitHub and Google each once; replay callback; tamper state; wrong code; resend throttle; unverified gate.
9. **Deploy** — migration, then API, then frontend; watch `oauth_*`, `email_verified`, 403 `email_unverified`, 429 `code_throttled`.

**C2.3 The one thing that must never happen.** Do **not** blanket `git restore` `src/email/service.py` or `src/api/auth_api.py` while reverting: both contain the completed, tested welcome-email feature. Revert only the OAuth/code hunks (§10.4 Option 2 lists the nine files exactly).

### D. The decisions this plan adds

D1–D4 are in §2. Four more are needed, because the report raises forks it does not answer, and one of them (§D6) is a legal question:

| # | Decision | Recommendation | Why it blocks |
|---|---|---|---|
| **D5** | Do the OAuth routes ship in this pass, or stay dark behind a flag? | **Ship behind a flag.** `OAUTH_ENABLED=false` by default; `/providers` returns `[]`, the buttons hide themselves. The code is written but has never run, and a half-configured provider is a support ticket. | §B38 cannot be scheduled without it |
| **D6** | Tax: configure it per country, or remove the field? | **Remove `tax_amount` until registered.** `{"IN": 0}` is a false claim on an invoice. A missing field is honest; a zero is not. | §B18 item 3 — it is a legal surface |
| **D7** | Session migration: expire every session once, or keep raw tokens valid until they lapse? | **Expire once.** A one-time logout is a better cost than leaving every device's bearer token in the database as a primary key. | §B15 cannot ship without it |
| **D8** | `/operator`: keep it versioned or exclude it from the public schema? | **Exclude from the OpenAPI schema.** A documented admin surface is reconnaissance. It stays reachable and role-guarded. | §6.2 |

---

## 9. The completeness test — how we know no flaw is left

A plan claiming "every flaw is covered" must be checkable rather than asserted. Four mechanical tests, all runnable:

**T1. The P-id test.** Every one of P1–P38 appears in §1.5.1 with a closing section, and every closing section it names exists in this file. `grep -o 'P[0-9]\+' docs/SIGNUP_TO_DASHBOARD_PLAN.md | sort -u` yields at least 1–38.

**T2. The section test.** Every section reference in §1.5.1 resolves. A reference to a section that does not exist is a broken promise, and this is the failure mode of a coverage table.

**T3. The route-contract test** (§6.2, rule 4). The exact sorted set of registered paths is asserted, so the surface cannot drift from this document.

**T4. The gate test** (§B11). Every state-changing router is enumerated and each spend/enqueue route is asserted to depend on `require_verified_email`, and each read route to not. This is the test that keeps §B11 true in six months, when someone adds a route.

**T5. The reachability test** (§14.5.6.4). Every registered path is either called by `frontend/src`, or listed in §14.5.6.1 as intentionally backend-only with a reason. Enumerate both sides mechanically: the same route inventory the §6.2 test builds, cross-referenced against every fetch/WebSocket call site. A route with no caller and no reason is a capability the customer paid for and cannot use — the failure mode that produced the whole of §14.5.6.

**T6. The shape test** (§14.5.6.4). For every outbound model, the serialised backend key set equals the TS union's keys. `_PROFILE_KEYS` and `_VERDICT_KEYS` in `public_events.py` already give the pattern; `R45` is the first case to close.

**What T1–T6 cannot prove.** They cannot prove the fixes *work* — that is what §8 and report §11.5's matrices are for. They prove only that nothing on record has been silently dropped, which is the specific thing the owner asked about. T5 and T6 extend that from "no flaw dropped" to "no surface unreachable and no shape disagreeing" — the two things a backend-only audit structurally could not see.

---

## 10. Contracts

### 10.1 `POST /api/v1/billing/onboarding/complete`

```
auth: session · csrf: required
{ "choice": "free" | "paid" }
200 { "onboarding_required": false }
409 { "code": "no_subscription", "message": "No paid plan to confirm." }
```

### 10.2 `GET /api/v1/billing/state`

As B4. `Cache-Control: private, no-store`. Every field the onboarding screen and the plan card render comes from here.

### 10.3 `POST /api/v1/billing/checkout` (extended)

```
{ "plan": "starter"|"studio", "currency": "INR"|"USD", "country": "IN",
  "return_to": "/onboarding/plan" }        // allowlisted; default /onboarding/plan
200 { "url": "https://rzp.io/…" }
409 { "code": "already_subscribed", "message": …, "status": …, "expires_at": … }
```

The 409 gains `status` and `expires_at` so the screen can say "you already have a plan in flight, it expires at 14:20" instead of a message that contradicts reality (P13).

---

## 11. Test matrix

**Backend**

1. `onboarding_required` is true for a fresh verified account, false once completed, false for a blocking subscriber, false when `billing_enabled=false`.
2. `/onboarding/complete` is idempotent; `choice:"paid"` without a subscription → 409; the endpoint never writes `plan_key`.
3. `/billing/state` returns a `subscription.action` for each of `active`, `authenticated`, `created`, `paused`, `halted`, `cancelled`, and `null`.
4. Checkout sends a `callback_url`; `return_to` outside the allowlist falls back to the default.
5. A `creating` row blocks a concurrent checkout; a stale `creating` row (past the authorisation window) does not.
6. `resolve_entitlements` returns `free` when `current_period_end` is in the past, even with `status="active"`.
7. Account deletion cancels every open subscription, and fails loudly if one cancel fails.
8. The gate test: every spend/enqueue route depends on `require_verified_email`; every read route does not.
9. A webhook whose dispatch fails is **not** recorded as complete.

**Frontend**

10. `resolveGate`: anon → signin with `next`; unverified → verify with `next`; `onboarding_required` → onboarding; verified and onboarded → outlet.
11. `/onboarding/plan` does not redirect to itself; `/account` stays reachable while unverified.
12. Pricing with a failed `/billing/plans` renders **no** price and **no** buy button.
13. Onboarding with a failed `/billing/state` still offers Continue free.
14. The return state: `active` → success; `pending` → waiting; 90 s timeout → still waiting, never an error.
15. Reloading the return page 5× creates no second subscription and re-polls idempotently.
16. `PlanUsage` renders the server's `action` and nothing from a client status set.
17. After checkout, `AccountPage` and the rail agree on the plan.

**Manual, once**

18. One live Razorpay test-mode checkout: pay → return → dashboard shows the paid plan; `AccountPage` agrees.
19. Webhook delayed 2 minutes: the return screen flips to active without a manual reload.
20. Gift-route: sign up with a disposable-domain address → rejected before the account exists.
21. A refund and a `payment.failed` each move the mirror row and write an audit row (§B18).
22. Delete an account with two open subscriptions: both are cancelled, and the graph is gone (§B10, §B13).
23. Read `/api/v1/auth/sessions` while holding a cookie: no returned value is the cookie (§B15).
24. The route-path set equals the contract in §6.2 (rule 4).

### 11.4 Security invariants — all 15 from `REPORT.md` §10.3 F

Each is a test, not a checklist item. Numbered as the audit numbers them so the two files can be read side by side.

| # | Invariant | Test |
|---|---|---|
| 1 | A code is never stored in plaintext and cannot be replayed after success | Read the Redis key: it is a hash. Confirm twice → the second fails |
| 2 | Five wrong attempts delete the code; a sixth is not allowed | Five bad confirms exhaust it; the sixth returns `code_attempts_exhausted`, not a bypass |
| 3 | Resend cannot spam a mailbox | Two sends inside 60 s → 429 with `Retry-After`; six in an hour → 429 on the sixth |
| 4 | An unverified session gets `403 email_unverified` on every spend/enqueue route **and nowhere else** | The §B11 enumeration test, run in both directions |
| 5 | The OAuth callback rejects a missing or mismatched state cookie (login CSRF) | Callback with no cookie and with a tampered cookie → 4xx, and no session is created |
| 6 | `next` is a same-origin relative path; no open redirect | `next=//evil.com`, `next=https://evil.com`, `next=/\\evil.com` all resolve to the safe default |
| 7 | A Google identity without `email_verified === true` is rejected; a GitHub identity without a verified primary email is rejected | Fixture per provider, each the unverified shape |
| 8 | The provider **subject**, not the email, keys the link; a provider email change cannot re-point a login | Change the fixture email, keep the subject → same account |
| 9 | Linking to an existing local account requires the provider's verified email | Unverified link attempt → refused |
| 10 | Disabled users cannot log in through OAuth | `disabled_at` set → login refused, same as password |
| 11 | OAuth-only users cannot password-login (same 401, same argon2 cost) | `password_hash IS NULL` → 401, timing equal to a wrong password |
| 12 | No provider access token, code or client secret is logged or stored | Capture the log during a full flow; assert no token substring; assert the DB has no token column |
| 13 | The callback cookie is HttpOnly / SameSite=Lax / Secure in prod; the session cookie is set on the redirect | Inspect `Set-Cookie` on the callback response in a prod-like config |
| 14 | OAuth start/callback are rate limited | Exceed `rate_limit_oauth` → 429 |
| 15 | The `users.password_hash` nullable migration is exercised and the downgrade is safe | Apply, roll back, re-apply on a scratch DB |

### 11.5 Test matrix — `REPORT.md` §10.3 G

| Layer | Tests |
|---|---|
| **Pure** | `safe_next`, the PKCE pair, the authorize URLs, Google/GitHub identity parsing (verified / unverified / missing email) |
| **Redis** | issue → redeem → replay; a wrong code; attempt exhaustion; the resend throttle; the hourly cap; expiry at the TTL |
| **DB** | signup → code confirm → `email_verified_at` set; the gate 403 before and 202 after; OAuth link/create against a dummy fixture; the unique-link race |
| **API** | code send/confirm status codes; `MeOut` includes `email_verified`; the link route still works |
| **Frontend** | code form states, the resend countdown, OAuth button visibility and consent, the guard redirect, `next` preserved |
| **Provider sandbox** | one GitHub and one Google login with a test account; check the redirect URI, the state cookie and the verified email |

### 11.6 Additional backend tests this plan adds

For the sections that had no test at all. Each is one assertion per logical check, matching `CLAUDE.md`.

| Area | Test |
|---|---|
| Storage (§B12) | Compose config: MinIO publishes no host port; boot refuses `minioadmin` in prod |
| Graph erasure (§B13) | Seed a dataset, delete the account, assert zero nodes for it and another dataset untouched |
| Corpus (§B14) | `/ingest/documents` JSON contains no value exceeding 4 KB; a build by `upload_ids` succeeds, a build by text body fails validation |
| Sessions (§B15) | `/auth/sessions` returns no value equal to any cookie; a forged `sid` is 401; the table yields no usable cookie |
| Webhook (§B16) | A failed dispatch is not recorded `processed`; a duplicate with a different hash re-enqueues |
| Quota (§B17) | Upgrade on day 15 after 6,000/8,000 used → 16,000 total with 6,000 used |
| Billing events (§B18) | `payment.failed`, refund and `halted` each write the mirror row and an audit row; a refund does not re-grant |
| PII (§B19) | The stored webhook body contains no denylisted contact key |
| CSRF (§B20) | A POST from an unlisted origin → 403; no-origin behaviour unchanged |
| Signup (§B21) | Duplicate and new signups return the same status **and** a latency within a tolerance |
| Rate limit (§B22) | `*` in prod refuses boot; the bucket key includes the normalised email |
| Sessions idle (§B23) | A session idle past 12 h → 401; the 11th login revokes the oldest |
| Config (§B24) | Each of the six unsafe prod values refuses boot; `/docs` is 404 in prod |
| Tenancy (§B25) | With RLS on, an ORM query with the wrong `user_id` returns zero rows |
| Redis (§B27) | A job payload contains ids only, no text; `failure_ttl` is short |
| Snapshot (§B28) | An unknown property does not appear in the projection; a 5 KB property is capped |
| Contract (§B33) | The exact key sets of a run document and a WS event |
| Entitlements (§B34) | `grep` finds no read of `user.plan_key` outside the resolver |
| Route contract (§6.2 rule 4) | The exact sorted set of registered paths |
| Erasure order (C2) | Deletion that cannot erase the graph does not report the account deleted |

---

## 12. Sequence

The order is the audit's own priority (report §11.11 P0 → P1 → P2), with the deployment gate first because nothing ships until it passes.

| Phase | Work | Exit criterion |
|---|---|---|
| **C2** | The deployment gate: migration `0010`, `ingest_url` gated, `MeOut` test updated, conftest flag, `.env` OAuth vars, lint and boot | `REPORT.md` §10.4's nine reasons are all closed; `ruff check` clean |
| **0** | D1–D8 answered; the accent frozen | No open design fork |
| **1** | B1, B2, F1, F2, F3 — the gate and the flag | A new account is sent to `/onboarding/plan` and cannot skip it |
| **2** | B4, B6, F4, F5, F8, F14, **R46, R47** — server plan state, shared card, honest pricing, and the two dead request fields | The screen renders server prices only; `context` and `selected_domains` are either sent or removed from the contract |
| **3** | B3, B5, B7, B16, F9, F10 — the payment loop, its return, and the outbox | A test-mode payment flips the dashboard within 90 s |
| **4** | B8, B9, B10, B17, B18, B19 — idempotency, period gate, deletion, quota, refunds, PII | The double-charge window is closed |
| **5** | F6, F7, F15, F16, **F18, F20, F21** — signup → verify → onboarding wiring, the public example, the Method page, password recovery, legal pages | No unverified user reaches the dashboard; `next` survives both paths; `/example` and `/method` are reachable pages, not dead links |
| **6** | B11, B20, B21, B22, B23, B30, B31, B32, B33, F11, F12, F13, **F23, R37, R45, R48** — the auth and contract hardening | The gate test, the enumeration test, the contract test all pass; **F7 has already shipped, so B11's gate cannot lock anyone out** |
| **7** | B12, B13, B14, B25, B26, B27, B28, B29, **B39, B40, F19** — MinIO, graph erasure, corpus, RLS, Redis, snapshot, Neo4j, the Billing page | Every data finding P7, P8, P9, P24–P29 is closed with a test; `/billing` renders `/billing/state` with no hardcoded figure |
| **8** | B15, B36, B37, B38, C1, **F22** — sessions, email outbox, metrics, OAuth, the operator view, account panel 2 | One GitHub and one Google login end to end; the funnel panel shows a real signup |
| **9** | §6 — the route contract: one mount per router, full prefixes, stable pagination, idempotency keys, `/docs` off, the path test | The path-set test passes; `/api/v1` is the only surface |
| **10** | B34, F14, the copy sweep, the §9 tests | No client status set remains; §9's four tests pass |

**Phase C2 is not optional and not parallel.** It is the difference between a tree that must not be deployed and one that can be.

**Why §6 is phase 9 and not phase 1.** It is a refactor of a working surface, so it must not compete with the journey work for the same reviewer. Nothing else in the plan depends on it except the idempotency key, which §B8 already supplies internally.

---

## 13. Definition of done

A visitor can, with no support contact:

1. land, and see one worked example before signing up;
2. sign up with a password **or** GitHub/Google;
3. enter a code, or click the link in the same mail;
4. **choose a plan on one screen before the dashboard** — paid or free, both first-class;
5. pay, be returned automatically, and watch the dashboard show the plan they chose, with the account page agreeing;
6. continue free and never be asked again;
7. upload material, build the map, run a decision, export the verdict;
8. cancel and see the plan end at the period end;
9. delete the account and know Postgres, S3 **and** Neo4j no longer hold the material.

Items 1–6 are this plan. 7 exists. 8–9 depend on B9/B10 and the audit's P7/P8.

**The synchronization condition, stated as a done-criterion:** no item here is "done" while its route has no caller and no reason, or while its two sides declare different shapes. §14.5.6's rows are the current detritus of exactly that; T5 and T6 are how it stops recurring.

---

## 14.5 The remediation register — every known-broken thing, and the phase that fixes it

This plan closes the audit's 38 findings (§1.5). It must also close **the defects the rename and the document consolidation exposed**, which no audit found. Each row is verified, located, and assigned to a phase in §12. Nothing here is "clean up later" — a row is closed when its test passes.

Read the table by the **Fix** column: that is what an implementing agent does.

### 14.5.1 The name — `Societas` → `LarkVision` (**domain `larkvision.com`**)

The brand was renamed across the design corpus on 2026-11-22. The design documents say *LarkVision*; the application does not.

| # | Location | Still says | Fix | Phase |
|---|---|---|---|---|
| R1 | `frontend/index.html:7` | `<title>Societas</title>` | `<title>LarkVision</title>` | 2 |
| R2 | `frontend/index.html:10` | meta description "*Societas* convenes your panel…" | "*LarkVision* convenes…" | 2 |
| R3 | `frontend/index.html:13` | `og:title content="Societas"` | `LarkVision` | 2 |
| R4 | `frontend/index.html:41` | seed key `societas-world-v1` | **keep** — an internal design-tool seed, not rendered | — |
| R5 | `.env.sample:45` | `EMAIL_FROM=no-reply@societas.app` | `no-reply@larkvision.com` | 3 |
| R6 | `.env.sample:47` | `LEGAL_CONTACT_EMAIL=hello@societas.app` | `hello@larkvision.com` | 3 |
| R7 | `src/config/settings.py:132` | `email_from: "no-reply@societas.app"` | `"no-reply@larkvision.com"` | 3 |
| R8 | `src/config/settings.py:159` | `legal_contact_email: "hello@societas.app"` | `"hello@larkvision.com"` | 3 |
| R9 | `src/api/api_server.py:281` | `title="Socirty Simulator API"` — **a typo for Societas** | `title="LarkVision API"` | 9 |
| R10 | `src/config/settings.py:84` | `s3_bucket: "societas-uploads"` | **keep** — a live object-storage namespace; renaming needs a bucket migration, not a find/replace | — |
| R11 | DB roles `societas_app`, `societas_retention` | live Postgres roles | **keep** — renaming needs a grant rewrite; no customer sees them | — |

**R5–R8 are gated on a fact outside this repo:** `larkvision.com` must be registered, with SPF/DKIM configured and the sending domain verified in Resend. `settings.py` refuses to boot in prod without `EMAIL_API_KEY`, but it cannot know the domain is unowned — so a wrong domain fails **silently**. **D19.**

### 14.5.2 The documents — what is tracked, visible and citable

| # | Defect | Effect | Fix | Phase |
|---|---|---|---|---|
| R12 | `docs/DESIGN_AUTHORITY.md` and `docs/SIGNUP_TO_DASHBOARD_PLAN.md` were whitelisted in `.gitignore` but **not committed** | a clone had no design authority and no plan | **fixed** — both are tracked (`git ls-files docs` returns them); the rest of `docs/` stays intentionally untracked | done |
| R13 | `DESIGN.md` is untracked; `docs/DESIGN_SPEC.md` is gitignored | two dead design worlds sit where an agent will read them | both now carry a **⚠️ SUPERSEDED / RETIRED** banner at the top; delete them once §11 passes | 10 |
| R14 | `.gitignore:28` `*.txt` and `:35` `tests/` | `requirements.txt` is tracked (predates the rule) but **the whole test tree is ignored** — a clone has no tests | narrow `tests/` to `tests/**/__pycache__/`, or remove the rule; `*.txt` must not swallow future requirement files | **now** |
| R15 | `CLAUDE.md` named `docs/DESIGN_SPEC.md` as "Frontend design authority" | **every coding agent read the plum world that was never built** | **fixed** — read order is `PRODUCT.md` → `DESIGN_AUTHORITY.md` → `DESIGN_PROPOSAL.md` → `DESIGN_PRODUCT_V7.html`; both dead files struck through | done |
| R16 | `docs/` was ignored as a directory | `DESIGN_SPEC.md`'s successor could not be committed | **fixed** — `docs/*` + the two negations that track the authority file and this plan | done |
| R17 | Decision numbers collide: `D5`–`D8` mean different things in the proposal and the plan | "answer D7" is ambiguous and will be answered wrongly | the authority file allocates new numbers at **D15+**; the two files' `D1`–`D8` are disambiguated by filename in any citation | 0 |
| R18 | The plan cited neither `PRODUCT.md` (0×) nor `DESIGN_PROPOSAL.md` (0×) | it was written in isolation, so it contradicted both | **fixed** — it now cites the authority file and inherits its design | done |

### 14.5.3 The route surface (§6) — structural, not cosmetic

| # | Defect | Fix | Phase |
|---|---|---|---|
| R19 | Every main router is mounted **twice** (bare legacy + `/api/v1`), so versioning is decorative | one mount per router; legacy paths become logged redirects with a removal date | 9 |
| R20 | Version location is inconsistent — some routers carry `/api/v1` in their prefix, others get it from `include_router`, `/operator` and `/jobs` carry none | every router declares its full prefix; `include_router(..., prefix=)` is never used | 9 |
| R21 | Two pagination contracts — Runs is cursor-based, `/ingest/documents` is `limit`-only | `/ingest/documents` gains `cursor` and returns `{items, next_cursor}` | 9 |
| R22 | No idempotency key on public write routes | `Idempotency-Key` on `checkout` and `onboarding/complete` | 9 |
| R23 | `/docs`, `/openapi.json` public in every environment; `/operator` in the public schema | `docs_url=None` in prod; `/operator` `include_in_schema=False` | 9 |
| R24 | `/new?step=ingest` uses a query param where every other surface uses a path segment | promote to `/new/ingest`; the alias routes at `App.tsx:84-86` already exist | 9 |
| R25 | The route set has no contract test | assert the exact sorted path set, so the surface cannot drift | 9 |

### 14.5.4 What V7 gets wrong about being a product (**D17**)

`DESIGN_PRODUCT_V7.html` is the appearance reference. These are its prototype-only behaviours, verified in the file — an implementing agent must **not** copy them, and the design side must decide each one's production form.

| # | In V7 | Why it cannot ship | Required production behaviour |
|---|---|---|---|
| R26 | `STATE.signedOut` flag; sign-in password preseeded `"design-preview"`; *"nothing leaves this page"* | there is no auth — it is an honour system | the real guard (`RequireAuth` + `resolveGate`); the demo flag is `?demo=1`, **dev builds only** |
| R27 | Three marketing sections link to app routes (`#/verdict`, `#/runs`, `#/account`); the footer links five | clicking as a visitor bounces to sign-in and **drops the destination** | every app link carries `next`; the guard preserves it through sign-in **and** sign-up |
| R28 | No session-expiry state | a stale tab looks live and every action 401s | a "signed out — sign in again" state that keeps the typed work |
| R29 | No offline state; no permission-denied state; no validation state | the only failures modelled are none | the four states from §11's matrix: S7 failed, S13 restricted, plus offline and field-invalid |
| R30 | Hardcoded `PLANS`, `RUNS`, `DOCS`, `INVOICES`, `VERDICTS`, `STATE` (≈1.6 KB of fixtures) | the price on screen can differ from the amount charged (audit **P10**) | render server values only; no transacting fallback (**F5**) |
| R31 | Hash routing (`#/signup`) | cannot be server-routed, cannot be deep-linked cold, collides with `#section` anchors | `BrowserRouter` + real paths (**§6**) |
| R32 | One 328 KB file: four `<style>` blocks, one `<script>`, 240 element ids | unmaintainable; no tree-shaking; no per-page code split | the component inventory in §5 and the file map in the Appendix |
| R33 | Section anchors and route hashes share `#`; `href="#how"` parses as the route `how` | a "scroll to section" link breaks the router | fragments for scroll, paths for destinations — **never both on one scheme** |

**The rule this table encodes:** V7 is a reference for **appearance**. Its structure and copy are copied deliberately (41/50 headings, 33/38 margin labels, 18/19 tokens). Its **behaviour is not** — every row above is a decision that must be made on purpose, not inherited by accident.

### 14.5.5 Known bugs with no assigned owner yet

| # | Defect | Evidence | Suggested phase |
|---|---|---|---|
| R34 | `index.html:41` seed key and the `.impeccable/` state are development-only; neither is rendered, but both ship in the repo | `frontend/index.html:41` | 10 |
| R35 | `tests/` being gitignored means CI on a clean clone has **no tests to run** — the suite passes only on a machine that already has the files | `.gitignore:35` | **now** |
| R36 | `api_server.py` mounts `simulate_router` and `jobs_router` at the bottom of the module, after ~700 lines of endpoint definitions | `api_server.py:1044-1050` | 9 |

### 14.5.6 Frontend/backend synchronization — what the client cannot reach, and what it mis-declares

This sub-section exists because the audit was a **backend** audit and the rename sweep was a **document** sweep. Neither could see the seam. Every row below was found by enumerating the backend's registered routes and comparing them against every fetch/WebSocket call site in `frontend/src`; a row is closed only when its test passes.

Read the **Kind** column first: `ORPHAN` is a capability no screen can use; `MISMATCH` is a shape two sides declare differently; `GAP` is a screen the plan already assigns but must not lose; `OK` is recorded so it is not "fixed" away.

#### 14.5.6.1 Orphaned backend capability — no frontend caller

Verified: zero non-test references in `frontend/src`.

| # | Endpoint | Consequence | Fix | Phase |
|---|---|---|---|---|
| **R37** | `DELETE /api/v1/uploads/{upload_id}` | **ORPHAN.** A card can be removed locally while the row and the stored object survive. Already caught at F13.2 — recorded here so the route inventory is complete | call it from `removeDoc`; restore the card on failure | 6 |
| **R38** | `POST /api/v1/auth/password` | **ORPHAN.** A user cannot change their password. B15 rotates sessions on a password change, so the rotation is unreachable | a change-password form in `/account`, calling it, then treating the 204 as "all other sessions revoked" | 8 |
| **R39** | `GET /api/v1/auth/sessions` + `DELETE /api/v1/auth/sessions/{id}` | **ORPHAN in the plan, NOT a design gap.** `DESIGN_PROPOSAL.md` §8.11 panel 2 already specifies `.session-row`s — *"device, browser, when, and a Sign out per session"* — and the `password` dialog is specified in §8.13. So the design is done and **no plan item delivers it**. An earlier draft of this row wrongly claimed the design had no device list | a session list in `/account` panel 2 with one Sign out per row, plus the change-password dialog; the B15 `public_id` change lands in the same phase so the UI is never built against the old shape. Owned by **F22** | 8 |
| **R40** | `POST /api/v1/auth/verify/code/send` + `/verify/code/confirm` | **ORPHAN today; GAP in plan.** The server can issue and redeem a 6-digit code; the client cannot enter one. F7 owns the screen | build F7 **before** B11 closes the gate (see §14.5.6.4) | 5 |
| **R41** | `GET /api/v1/auth/oauth/providers` + `/oauth/{provider}/start` | **ORPHAN.** 545 backend lines and migration `0010` are unreachable. `RequireAuth` has no provider branch; no `OAuthButtons` component exists | see R42 — the component is the fix | 8 |
| **R42** | — (**missing client piece**) | **GAP.** `OAuthButtons` is named only in §C2 step 5 as though it already exists. No `F` item creates it, so §C2 reason 4 is "closed" by F6+F7, which do not close it | add **F17**, below | 8 |
| **R43** | `POST /api/v1/legal/consent` | **ORPHAN, low severity.** First consent **is** recorded — `auth/service.py:153` writes it inside the signup transaction and rolls back if it fails; `oauth.py:342` does the same. This route is **re-consent** for a new legal version, and nothing re-prompts on version change | a version-aware re-consent banner on next authed load when `content_sha256` differs from the recorded version | 10 |
| **R44** | `DELETE /api/v1/jobs/{id}` | **ORPHAN.** No cancel action on a queued or running job, so a mistaken upload or graph build can only be waited out to its terminal state | a cancel action on the in-flight job surfaces (`IngestPage`, `GraphPage`) | 9 |

**Correctly not a client surface, and must stay off it:** `POST /api/v1/simulate/normalize_graph` (a pipeline stage the graph job calls internally), `GET /ready` (infrastructure probe; `/health` is the client's read), and `GET /operator/runs/{run_id}/agents/{node_id}` (role-guarded, audited, `include_in_schema=False` per R23). An agent must **not** add UI for these three.

#### 14.5.6.2 Contract mismatches — both sides exist and disagree

| # | Contract | Backend | Frontend | Consequence | Fix | Phase |
|---|---|---|---|---|---|---|
| **R45** | `pair_turn` event | `public_events.py:50` allows only `{type, pair_id}`; `round_runner.py:320` sends exactly that | `run/events.ts:155` declares `response` and `error`; `reducer.ts:169` reads neither | a per-pair success/failure signal is advertised and can never arrive. A failed turn is invisible until the round event | drop the two fields from the TS union **and** add a type-level test that every key in `_EVENT_KEYS` matches the TS union | 6 |
| **R46** | `DebateRequest.context` | accepted, capped at `CONTEXT_MAX_BYTES = 4096` (`debate_api.py:101`), serialised into the prompt as `scenario` (`orchestrator.py:529`) | nothing ever sets it — `grep 'context:'` in `frontend/src` is 0 hits | the strongest prompt input the API supports is permanently empty: verdicts are weaker than the product promises | capture the scenario in the wizard's question step (a bounded textarea, live byte counter) and send it | 2 |
| **R47** | `selected_domains` | used for domain filtering and the intent fallback (`utils/queryIntend.py:131,140`) | hardcoded `[]` at `SocietyPage.tsx:52` | a live filter is silently disabled | let the question step pick from the map's domains, or **remove the parameter** so the contract stops implying a capability no screen offers | 2 |
| **R48** | Error `code` vocabulary | 20 codes emitted (`email_unverified`, `plan_limit_exceeded`, `code_throttled`, `code_attempts_exhausted`, `already_subscribed`, `rate_limited`, `payment_required`, `job_limit_exceeded`, `no_corpus`, `corpus_gone`, …) | 4 handled. `rest.ts:41` documents "branch on `code`, never on `detail`" and then almost nothing branches | `plan_limit_exceeded` reaches the user as a raw server sentence with no upgrade path | a `copies/errorCode.ts` map: every code → one sentence, defaulted by status. One table, one test asserting every backend code has an entry | 6 |

#### 14.5.6.3 The sign-up → verify → plan → dashboard chain, end to end

The owner's requirement, stated once: **a new user enters email and password, sees a verification step, then chooses a plan on its own page, and only then reaches the dashboard.**

Today that chain does not exist at any layer. Recorded as the reference for the phases that build it:

| Leg | Backend | Frontend | State | Owning item |
|---|---|---|---|---|
| email + password → account | `POST /auth/signup` (201, sets `sid` + `csrf`) | `SignUpPage` → `safeNext(...)` → `/landing` | **built** | — |
| …but the user is signed in **before** verifying | consent written inline (`service.py:153`); `email_verified` returned on `MeOut` | `User` type omits `email_verified`; `resolveGuard` has no verify branch | **broken** | B11 + F1 + F2 + F6 |
| verification screen | `/verify/send` (204), `/verify/code/send` (202), `/verify/code/confirm` (200), both gated routes return `403 email_unverified` (`deps.py:150`) | `VerifyEmailPage` reads `?token=` **only**; no code form; `RequireAuth` never routes here | **missing** | F7 (+ F2) |
| plan page | **absent**: no `onboarding_completed_at` column, no `onboarding_required` flag, no `POST /billing/onboarding/complete`, no `GET /billing/state` — `grep -i onboarding` over `src/` is **0 hits** | **absent**: no `OnboardingPlanPage`, no `/onboarding/plan` route, `grep onboarding` is **0 hits** | **missing at both layers** | B1 + B2 + B3 + B4 + F8 |
| → dashboard | `GET /billing/usage` reports the entitlement | `LandingPage.landingTarget(uploads, runs)` → documents \| runs \| results | built, but **unreached**: `/landing` is only the `safeNext` default | F2, F8 |

**Order is not negotiable.** The gate must open **after** the screen that satisfies it exists, or every new account is locked out of ingest and debate with no way forward. The sequence already honours this — **F7 is phase 5, B11 is phase 6** — and that ordering is now a **hard constraint, not a preference**: any re-plan that moves B11 earlier must move F7 with it, or demote B11 to "gated on F7 shipped".

#### 14.5.6.4 The four drift classes, and the test that stops each recurring

A synchronization section that is not enforced is a snapshot. Each class below gets a test, and the test is the deliverable:

| Class | How it drifts | The test that stops it | Phase |
|---|---|---|---|
| **Route drift** | a route is added, renamed or mounted twice; no client ever learns | the §6.2 path-set test — assert the exact sorted set of registered paths | 9 |
| **Shape drift** | a pydantic model gains a field, or the TS interface invents one | a **contract test** per outbound model: serialise the backend response and assert its key set equals the TS union's keys. `R45` is the first case; `_PROFILE_KEYS`/`_VERDICT_KEYS` already give the pattern | 6 |
| **Reachability drift** | a route exists with no caller (this whole of §14.5.6.1) | an **inventory test**: assert every registered path is either called by `frontend/src`, or listed in this file as intentionally backend-only (`normalize_graph`, `/ready`, `/operator`) | 9 |
| **Code drift** | the server adds an error code the client renders as a raw string | `R48`'s test — every backend `code` has an entry in the copy map | 6 |

**The rule.** A new route or a new outbound key is not done when the server returns it. It is done when the inventory test passes with the caller registered, or when this section records the route as intentionally unreachable with a reason.

#### 14.5.7 Document-level breaks found while writing §3.1 and F17

Not frontend/backend seams — these are defects in the design and plan corpus itself. Recorded because each one causes a build decision to be made against wrong information.

| # | Defect | Evidence | Fix | Phase |
|---|---|---|---|---|
| **R49** | **`DESIGN_PROPOSAL.md` contradicted itself on the Free pricing column.** §11's file map said `/pricing` ships "without a Free column"; §12 said "The Free plan **is** a column". Both were live text in the same committed file | `DESIGN_PROPOSAL.md:1614` vs `:1671` | **FIXED 2026-11-22** — the file map now reads "with a Free column", the losing sentence is deleted, and §12 records the reversal once. D2 in this plan no longer conflicts | done |
| **R50** | **V7 could not be the appearance reference for three required screens.** Its `data-site` set is `landing, pricing, method, signup, signin` — no verify view, no onboarding view, no OAuth buttons | `DESIGN_PRODUCT_V7.html`: 5 site views; signup copy says "nothing leaves this page" | **FIXED 2026-11-22** — `DESIGN_PROPOSAL.md` now specifies all three: **§8.16** verify, **§8.17** provider buttons, **§8.18** plan choice. Every value is quoted from V7's own stylesheet, so they match its language without pretending V7 contained them | done |
| **R51** | **`R67` is a dangling reference.** `SignUpPage.tsx:26` and `SignUpPage.test.tsx` cite `R67` as the reason the sign-up form has no name field. No `R67` exists in any document, and this register stops at R66 | `grep '\bR67\b'` over all docs → 0 hits outside the citing files | write the finding into this register, or renumber the citation to whichever row actually records it. An agent following `R67` finds nothing | 2 |
| **R52** | **Design decisions D1–D8 are re-used across two files for different questions.** `SIGNUP_TO_DASHBOARD_PLAN.md` §2's D1–D8 and `DESIGN_PROPOSAL.md` §12's D1–D11 collide; "answer D5" is ambiguous | authority file already fixes forward numbering at D15+ | **cite by filename** (`plan D2`, `proposal D6`) until one list is retired. `DESIGN_AUTHORITY.md` §6 records the hazard; this row records the residue | 0 |
| **R53** | **`docs/DESIGN_SPEC.md` is the only *un*tracked design document** and still carries live-looking content under a supersession banner. `git ls-files docs` returns two files; this is not one of them | `.gitignore:23` + two negations | delete it once §11 passes, as R13 already says. Until then it is an untracked file an agent can read and mistake for current | 10 |
| **R54** | **`/method` was designed and linked but no plan item built it.** `DESIGN_PROPOSAL.md` §8.4 specifies the page in full; the landing and pricing pages link to it; `frontend/src/pages/` has no `MethodPage.tsx`. A dead link the day F15 ships | design §8.4 vs no page file | **FIXED 2026-11-22** — **F18** added, phase 5, with the D9 copy block held behind the owner's wording | done |
| **R55** | **`/billing` was designed but no plan item built it.** `DESIGN_PROPOSAL.md` §8.10 specifies six panels; §8.5 reaches the page from the **account popover**; B4's `GET /billing/state` had **no consumer**. `PlanUsage` is a component inside `OverviewPage` | design §8.10 vs no page file | **FIXED 2026-11-22** — **F19** added, phase 7, reading `/billing/state` only and reusing F4's card | done |
| **R56** | **`/example` was a plan item (F15) the design never specified** — the inverse of R54/R55. It was also absent from the landing and pricing specs that were supposed to link to it | plan F15 vs 0 design mentions | **FIXED 2026-11-22** — **`DESIGN_PROPOSAL.md` §8.19** added, plus the link rules in §8.2 rule 6 and §8.3 | done |
| **R57** | **§8.18's wireframe hardcoded the figures its own text bans** (`$10`, `8,000`, `12 experts`, `4 passes`) — the exact defect P10/F5 exists to remove — **and contradicted §8.3's Free row** (10 experts / 3 passes) | design §8.18 wireframe vs §8.3 table vs `settings.plan_*_max_agents` | **FIXED 2026-11-22** — every digit replaced by a `{token}` placeholder naming its `/billing/state` field, and a consistency rule tying both pages to the same source | done |
| **R58** | **Design drew a Payment-method panel and a `card` dialog; the plan had no endpoint.** §8.10 panel 4 and §8.13's `card` dialog need the card's brand/last4/expiry; B4's `/billing/state` has no such field and no `B` item supplied one | design §8.10 panel 4 vs B1–B38 | **FIXED 2026-11-22** — **B39** added (read-only `GET /billing/payment-method`, card data never stored, `card:null` first-class), route added to §6.2, and **F19** consumes it | done |
| **R59** | **Design drew an Invoices panel; B18.4 persisted the rows but nothing could read them.** No `GET /invoices` route existed in §6.2, and no `F` item rendered the panel — invoices were written to a table with no read path | design §8.10 panel 5 vs B18.4 | **FIXED 2026-11-22** — **B40** added (`GET /billing/invoices`, keyset paging, signed download URL minted at read), route added to §6.2, **F19** renders it | done |
| **R60** | **`F19` falsely claimed B4 supplied all six billing panels.** It listed "payment method, invoices" among *"exactly the fields B4 already returns"* — B4 returns neither, which hid R58 and R59 | plan F19 vs B4's payload | **FIXED 2026-11-22** — F19 now says it consumes **three** contracts (B4 + B39 + B40), and names which panels come from which | done |
| **R61** | **Legal pages had no design section.** The backend publishes legal documents, the footer links to them from every page, and signup records consent against their `content_sha256` — but §8 had no section for `/legal`, `/legal/:slug`, `/privacy`, `/terms`, `/refund`, and no `F` item built them | design §8 had 0 legal sections | **FIXED 2026-11-22** — **`DESIGN_PROPOSAL.md` §8.20** added (index + detail in §8.4's `.method` idiom, version/date always shown, served never bundled, aliases as redirects, re-consent band), and **F21** builds it | done |
| **R62** | **Password recovery had no design section and no plan item — in either document.** `POST /auth/reset/request` and `/reset/confirm` existed, `ForgotPasswordPage.tsx` and `ResetPasswordPage.tsx` existed, and **neither this plan nor the design ever specified them**: `forgot`/`reset` appeared 0 times in both | 0 hits in both docs | **FIXED 2026-11-22** — **`DESIGN_PROPOSAL.md` §8.21** added (two pages, V7's ruled field, six states each, no account enumeration), and **F20** builds them | done |
| **R63** | **Sessions and change-password were designed but no plan item delivered them — and `R39` wrongly called it a design gap.** §8.11 panel 2 already specifies `.session-row`s with a Sign out per row, and §8.13 the `password` dialog | design §8.11 vs no `F` item | **FIXED 2026-11-22** — **F22** added (account panel 2: password row + session rows, built against B15's `public_id` in the same phase); **R39** corrected to *"ORPHAN in the plan, NOT a design gap"* | done |
| **R64** | **Stop-a-decision and remove-material had backend routes nothing called, and §8.12 drew neither control.** `DELETE /jobs/{id}` (R44) and `DELETE /uploads/{id}` (R37) were reachable by no screen, and the workspace spec had no stop affordance | design §8.12 vs R37/R44 | **FIXED 2026-11-22** — §8.12 now specifies both controls (stop as a dialog, remove as an inline confirm with **no undo toast**), and **F23** builds them | done |


**What R49–R64 have in common:** each one makes an implementing agent act on a document that is wrong about its own subject, or build a screen the other document never drew. They are cheap to fix and expensive to leave, because a design corpus is only as useful as its worst-contradicting file.

**The pattern R54–R56 describes** is worth naming, because it is how the six-way split happened: a page can be **designed without being planned** (R54, R55) or **planned without being designed** (R56). Both produce the same outcome — a route in no build order, or a build with no spec. **The rule that prevents it:** a page is only real when `DESIGN_PROPOSAL.md` §8 has a section for it **and** this plan has an `F` item that builds it **and** the two cite each other. Every entry in §8's page list and every `F` item that adds a route should satisfy all three.

---

## 14. Assumptions and risks

- **The accent decision is real and blocks visual work.** D1 must be answered before F4/F8 are styled, or the work is thrown away.
- **`billing_enabled=false` must still render the free path.** The gate is skipped entirely when billing is off, so a deployment without Razorpay is usable, not a wall.
- **`onboarding_required` on `MeOut` couples auth to billing.** It is a boolean behind a settings check; the alternative — a second request per page load — is worse. If it becomes contentious, move it to `/billing/state` and accept one extra round-trip in the guard.
- **The public domain is `larkvision.com`**, and it is not yet registered. Every email address in the repo must use it (register R5–R8), and SPF/DKIM plus the Resend domain must be verified before any transactional mail works. **D19.**
- **`callback_url` depends on `APP_BASE_URL` being correct in each environment.** Settings already refuse a localhost origin in prod (`settings.py:202-205`), which is the guard that makes this safe.
- **Migration 0010 (OAuth) has never run.** Phase 7 cannot start until it is reviewed and applied on a scratch database.
- **The V7 prototype is not a source of truth for copy.** Its marketing strings are drafts; **`PRODUCT.md:130`'s copy law** governs what ships. Where V7 and the copy law disagree, the law wins and V7 is corrected.
- **This plan owns no design decision.** Tokens, structure and layout come from `DESIGN_PROPOSAL.md`, whose values come from `DESIGN_PRODUCT_V7.html`. `docs/DESIGN_AUTHORITY.md` is the record of which document answers what — cite it, not this file, when a design question arises.

---

## Appendix — file change map

**Backend**

```
alembic/versions/0011_onboarding.py          NEW
src/api/auth_api.py                          EntitlementOut.onboarding_required
src/api/billing_api.py                       /state, /onboarding/complete, return_to, 409 detail
src/billing/razorpay_client.py               callback_url
src/billing/webhook.py                       plan_activated_at; disabled-user guard
src/billing/entitlements.py                  current_period_end rule
src/api/account_api.py                       cancel every open subscription
src/db/models.py                             users.onboarding_*; one-live-sub index
src/jobs/*                                   inline reconcile; dispatch-failure record
src/api/ingest_api.py                        gate ingest_url
tests/api/test_onboarding.py                 NEW
tests/api/test_billing_state.py              NEW
tests/api/test_route_gate.py                 NEW — the enumeration test
```

**Frontend**

```
src/api/types.ts                             User.email_verified; entitlements.onboarding_required
src/api/rest.ts                              billingState, onboardingComplete; checkout return_to
src/auth/guard.ts                            resolveGate
src/auth/RequireAuth.tsx                     render verify/onboarding branches
src/App.tsx                                  /onboarding/plan sibling route
src/components/billing/PlanCard.tsx          NEW — extracted from PricingPage
src/components/billing/PlanComparison.tsx    NEW — table ⇄ stacked dl
src/pages/OnboardingPlanPage.tsx             NEW
src/pages/PricingPage.tsx                    no transacting fallback; shared card
src/pages/SignUpPage.tsx                     → /auth/verify
src/pages/VerifyEmailPage.tsx                code form, resend, link fallback
src/pages/AccountPage.tsx                    plan block from /billing/state
src/pages/MethodPage.tsx                    NEW — §8.4, D9 copy held
src/pages/BillingPage.tsx                   NEW — §8.10, reads B4 + B39 + B40
src/pages/ForgotPasswordPage.tsx            §8.21 — email step
src/pages/ResetPasswordPage.tsx             §8.21 — new password + token
src/pages/LegalIndexPage.tsx                §8.20 — document index
src/pages/LegalPage.tsx                     §8.20 — one served document
src/pages/ExamplePage.tsx                   NEW — §8.19, one authored constant
src/pages/OverviewPage.tsx                  F12 truthfulness only; retired with the route
src/components/auth/OAuthButtons.tsx        NEW — §8.17, reads /auth/oauth/providers
src/components/legal/ReconsentBanner.tsx    NEW — §8.20, posts /legal/consent

src/components/overview/PlanUsage.tsx        server-driven action
```

**Docs**

```
docs/DESIGN_AUTHORITY.md                     READ FIRST — authority index, resolved tokens, supersession
                                              record, and open items D15–D18 (accent, onboarding, V7 triage, docs/ tracking)
DESIGN_PROPOSAL.md                           tokens + every page (design authority); §8.8 is the onboarding screen
docs/DESIGN_SPEC.md                          SUPERSEDED — do not edit; see DESIGN_AUTHORITY.md §3.1
docs/BILLING_AND_COMPLIANCE_PLAN.md          §6 return URL and onboarding completion
```
