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
| OAuth providers / start / callback | `src/api/oauth_api.py:48`, `:54`, `:98` | **Written, untested, unmigrated.** |
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
| **V7 prototype** | `#2D3F9C` indigo | `DESIGN_PRODUCT_V7.html:42` — the file handed over as the design reference |

**Recommendation: keep the shipped evergreen.** It is the only one with measured contrast assertions already in CI. Changing it invalidates the entire §2.6 matrix and the token test. If the owner prefers V7's indigo, that is a deliberate re-theme (one variable, then re-measure), and it should be its own change before this journey work starts — not smuggled in with it.

### D2. Does the free tier appear on the plans page?

`plans.py` defines `free`; `/billing/plans` does not return it; `DESIGN_PROPOSAL` D6 says the free allowance is unverified and is added to pricing only after D6 is answered. V7 shows **four** cards including Free.

**Recommendation:** free is a **tier in the catalogue but not a card**. The onboarding screen says "Start free — 1,000 units" using the server's `plan_free_units`, and adds a card only once D6 is answered. This preserves V3/V7's honesty about the free path without publishing an allowance nobody has verified.

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

### F5. Kill the transacting fallback — `PricingPage.tsx:29-58` (P10)

`PLANS` currently carries `{ INR: 999, USD: 10 }`, `'8,000'`, `'12'`, `'4'` as a render-time fallback **with live buy buttons**. A user can be shown one number and charged another.

Replace with:

- `plans: BillingPlan[] | null`, initial `null`.
- While `null`: skeleton cards, **no price, no CTA**.
- On fetch failure: a ruled "Pricing unavailable — try again" panel, CTAs absent.
- The `RULES` copy block (`:116-120`) is static prose and may stay; prices and limits never are.

The same rule applies to the enterprise block's `ENTERPRISE_ROWS`.

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

This is the one screen where the prototype has nothing to offer: V7's signup is a two-field mock. Design it in the existing `AuthLayout` idiom — `font-display` heading, one column, `min-h-11` controls.

### F8. Wallet: the onboarding screen — `pages/OnboardingPlanPage.tsx` (new)

**Reads:** `GET /billing/state` only. No `PLANS` constants on this screen, ever.

**Layout** — one column, max ~560px, centred, no rail:

| Band | Content | Design source |
|---|---|---|
| Head | "Choose how you start." + one lead line | V7 `pricing-h1` + `.lead`, re-expressed |
| Cards | Starter, Studio — `PlanCard` from F4 | V7 `.plan-card`, shipped pricing card |
| Free | One ruled line: "Start free — 1,000 units, no card." + **Continue free** | V7's honesty about the free path, without a fourth card (D2) |
| Rules | The three existing `RULES` lines from `PricingPage` | reused verbatim, so the two pages cannot disagree |

**States:**

1. `loading` — skeleton cards, no prices.
2. `error` — "Couldn't load plans." + retry + **Continue free still enabled**. A server outage must never trap a user behind a paywall.
3. `idle` — the three choices.
4. `busy` — the chosen card's button reads "Opening checkout…", siblings disabled.
5. `return` (see F9).

### F9. The return state — the part V7 has no equivalent for

On `?checkout=return`, replace the cards with a **ruled status ledger** in V7's own language (its `.ledger-row` / `.double-rule` / mono figures), not a spinner:

```
CHECKING YOUR PAYMENT
─────────────────────────────
Plan            Studio
Status          Activating…            ← or "Active"
Next charge     30 Dec 2026
─────────────────────────────
We check again in 3s. It usually takes under a minute.
                      [ Check again ]  [ Open the dashboard ]
```

- Poll `GET /billing/state` every 3 s for ≤ 90 s.
- `status === "active"` → success: "Studio is active", the reset date, and **Open the dashboard**.
- `pending`/`authenticated` → "Payment received. Your plan activates shortly." — never an error, never "failed".
- Timeout → stop polling, keep **Check again**, keep the support mailto. Still not an error.
- On success: `POST /billing/onboarding/complete {choice:"paid"}`, then `authMe()` to refresh the store, then `/landing`.
- Strip the query with `history.replaceState` so a refresh does not re-poll.

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

---

### F12. The Overview stops inventing numbers — P30

`OverviewPage.tsx:169-210` derives "25 answers filed", corpus rows joined **by name** (`corpusRows.ts:21-35`) and a permanent `convergence: null` from whatever the client happens to hold.

- **A server aggregate endpoint** (`GET /api/v1/overview`) returns the counts it can actually count. No count is computed on the client from a page of results.
- **Join corpora by `dataset_id`**, never by name. A name match is a guess and it will match the wrong dataset the first time two are called "Q3".
- **Read convergence from run events**, not from a client placeholder.
- If a number is not available, the page says "Not yet" — never `0`, and never a leftover from the last render.

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

### F15. A public worked example — report §11.1

A visitor has no public sample of what an account unlocks, and asking them to sign up to find out is the highest-friction ask in the funnel.

Add a public route `/example` that renders **one authored filed decision** through the existing `VerdictSheet`, labelled "Worked example" exactly as the marketing page labels its examples.

- **Copy, not machinery.** The sheet component, the position marks and the tape already exist; the page is a route and a data fixture.
- **It carries the same label as every other example** (`PRODUCT.md:130`, the copy law — the only surviving authority on copy) and no "real customer" claim.
- Linked from the landing hero and the pricing page, so the visitor can inspect the output before creating anything.

### F16. `next` survives both login paths — report §11.2

`signInTarget` encodes the destination for password login; after **OAuth** the destination comes from the server-stored `next`. The two are consistent only if the frontend passes `next` on the OAuth start URL.

- **Pass `next` explicitly on every OAuth button**, so a deep link (`/runs/<id>/verdict`) round-trips identically through password and provider login.
- **Test both paths to the same destination:** one password login and one OAuth login, both landing on the deep link they started from.

---

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
/api/v1/billing/*     plans, usage, state, checkout, subscription, webhook
/api/v1/legal/*       documents, consent
/api/v1/account/*     deletion, export
/api/v1/ingest/*      files, url, documents
/api/v1/uploads/*     list, delete, preview
/api/v1/simulate/*    debate, debates, graph, stream (WS)
/api/v1/jobs/*        job read, cancel
/operator/*           role-guarded, never versioned, never in the public OpenAPI
/health, /ready       unversioned infrastructure endpoints
```

**The rules that make it enforceable:**

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

**T3. The route-contract test** (§6.2.4). The exact sorted set of registered paths is asserted, so the surface cannot drift from this document.

**T4. The gate test** (§B11). Every state-changing router is enumerated and each spend/enqueue route is asserted to depend on `require_verified_email`, and each read route to not. This is the test that keeps §B11 true in six months, when someone adds a route.

**What T1–T4 cannot prove.** They cannot prove the fixes *work* — that is what §8 and report §11.5's matrices are for. They prove only that nothing on record has been silently dropped, which is the specific thing the owner asked about.

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
24. The route-path set equals the contract in §6.2 (§6.2.4).

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
| Route contract (§6.2.4) | The exact sorted set of registered paths |
| Erasure order (C2) | Deletion that cannot erase the graph does not report the account deleted |

---

## 12. Sequence

The order is the audit's own priority (report §11.11 P0 → P1 → P2), with the deployment gate first because nothing ships until it passes.

| Phase | Work | Exit criterion |
|---|---|---|
| **C2** | The deployment gate: migration `0010`, `ingest_url` gated, `MeOut` test updated, conftest flag, `.env` OAuth vars, lint and boot | `REPORT.md` §10.4's nine reasons are all closed; `ruff check` clean |
| **0** | D1–D8 answered; the accent frozen | No open design fork |
| **1** | B1, B2, F1, F2, F3 — the gate and the flag | A new account is sent to `/onboarding/plan` and cannot skip it |
| **2** | B4, B6, F4, F5, F8, F14 — server plan state, shared card, honest pricing | The screen renders server prices only |
| **3** | B3, B5, B7, B16, F9, F10 — the payment loop, its return, and the outbox | A test-mode payment flips the dashboard within 90 s |
| **4** | B8, B9, B10, B17, B18, B19 — idempotency, period gate, deletion, quota, refunds, PII | The double-charge window is closed |
| **5** | F6, F7, F15, F16 — signup → verify → onboarding wiring, the public example | No unverified user reaches the dashboard; `next` survives both paths |
| **6** | B11, B20, B21, B22, B23, B30, B31, B32, B33, F11, F12, F13 — the auth and contract hardening | The gate test, the enumeration test, the contract test all pass |
| **7** | B12, B13, B14, B25, B26, B27, B28, B29 — MinIO, graph erasure, corpus, RLS, Redis, snapshot, Neo4j | Every data finding P7, P8, P9, P24–P29 is closed with a test |
| **8** | B15, B36, B37, B38, C1 — sessions, email outbox, metrics, OAuth, the operator view | One GitHub and one Google login end to end; the funnel panel shows a real signup |
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

---

## 14. Assumptions and risks

- **The accent decision is real and blocks visual work.** D1 must be answered before F4/F8 are styled, or the work is thrown away.
- **`billing_enabled=false` must still render the free path.** The gate is skipped entirely when billing is off, so a deployment without Razorpay is usable, not a wall.
- **`onboarding_required` on `MeOut` couples auth to billing.** It is a boolean behind a settings check; the alternative — a second request per page load — is worse. If it becomes contentious, move it to `/billing/state` and accept one extra round-trip in the guard.
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
