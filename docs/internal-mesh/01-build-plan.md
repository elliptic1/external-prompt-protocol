# 01 — Build Plan

A phased delivery plan for the platform team. Each phase has explicit acceptance criteria. **Do not move to the next phase until the current phase's criteria are met.**

## Phase 0 — Foundation (week 1–2)

**Goal:** Choose the canonical infrastructure substrates so all later work plugs into them.

**Deliverables:**
- Decision recorded: which KMS backs team-AI signing keys.
- Decision recorded: which Postgres / managed SQL hosts the registry and receipt index.
- Decision recorded: which Redis cluster hosts the nonce registry and rate limiter.
- Decision recorded: which object store hosts receipt blobs.
- Decision recorded: which service-identity system anchors team-AI identity (see [05](05-key-management.md), Option B).
- Decision recorded: which observability stack receives metrics/traces/logs.
- A `platform-decisions.md` doc checked in with each decision and its rationale.

**Acceptance:**
- Every later doc in this set can name the actual service, not "your KMS." A platform engineer can read the decisions doc and provision dev/staging/prod accounts for each.

## Phase 1 — Core protocol surface (week 3–4)

**Goal:** A reference inbox container that any team can deploy and that exchanges envelopes correctly with itself.

**Deliverables:**
- Containerized inbox image built from `epp/inbox/server.py` with the executor swapped for `LoggerExecutor`.
- Image published to internal registry, signed.
- Helm chart (or equivalent) for deploying the inbox into a team's namespace.
- A loopback test deployment: one inbox, one CLI sender, envelopes flow, receipts return.
- All Layer 1 and Layer 2 tests from the [testing guide](../testing-guide-enterprise-ai-mesh.md) passing in CI.

**Acceptance:**
- A platform engineer can `helm install` the inbox into a fresh namespace and have it accept signed envelopes within 10 minutes.

## Phase 2 — Identity and trust (week 5–7)

**Goal:** A central identity registry plus a working trust-registry pattern such that two team-AIs can be wired up to talk to each other.

**Deliverables:**
- Identity registry service (see [03](03-api-contracts.md) — Identity Registry API). Backs onto Postgres. Stores team-AI metadata + active pubkeys + lifecycle state.
- KMS-backed signer integrated into the inbox image (see [05](05-key-management.md)).
- Trust registry implementation backed by Postgres (replacing the file-backed reference).
- Admin CLI / minimal admin UI for: registering a team-AI, rotating a key, granting a pairing, revoking a sender.
- Audit log: every admin write produces an audit-log entry.

**Acceptance:**
- Two distinct team-AIs (call them `T1` and `T2`) can be registered, paired (`T1` → `T2` for scope `demo.*`), and exchange a live envelope. The audit log shows each admin action.

## Phase 3 — Production-grade nonce + rate limit (week 8)

**Goal:** Replace the in-process nonce registry and rate limiter with Redis-backed implementations that survive multi-replica deployment.

**Deliverables:**
- `RedisNonceRegistry` implementation passing the `NonceRegistryContract` test suite.
- `RedisRateLimiter` implementation passing the `RateLimiterContract` test suite.
- Inbox helm chart updated to deploy 3 replicas behind a service.
- Mesh integration test: 3-replica inbox handles 1000 envelopes/sec sustained for 60s with no envelope loss and no replay false-positives.

**Acceptance:**
- Layer 4 and the relevant Layer 5 tests from the [testing guide](../testing-guide-enterprise-ai-mesh.md) pass.

## Phase 4 — Receipt warehouse and discovery (week 9–10)

**Goal:** Make the mesh observable to operators, auditors, and the teams themselves.

**Deliverables:**
- Receipt warehouse: an executor wrapper that writes every receipt to the chosen object store, plus an indexed table in the chosen warehouse (see [04](04-data-schemas.md)).
- Receipt query API for retrieval by `envelope_id`, `sender`, `recipient`, time range.
- Discovery portal: each team-AI has a Backstage entity (or equivalent) showing pubkey, supported scopes, on-call rotation, example envelopes, current pairings.
- Receipts sink to SIEM as a secondary stream.

**Acceptance:**
- An operator can answer "show me every envelope T1 sent to T2 in the last 24 hours and the outcome of each" in under 30 seconds. A new team can find and request to pair with an existing team-AI through the portal.

## Phase 5 — First production pilot (week 11–14)

**Goal:** Two real product teams running the pilot defined in the [use case](../use-case-enterprise-ai-mesh.md).

**Deliverables:**
- Both pilot teams onboarded per [09 — Team onboarding](09-team-onboarding.md).
- Pairing established in log-only mode for the first 14 days.
- Dashboards live for both teams (see [07](07-observability.md)).
- Incident runbooks exercised in a tabletop.
- Pilot success criteria from the use case being measured: pairing-onboarding time, p95 latency, credential rotations, receipt completeness.

**Acceptance:**
- All pilot success criteria met. The third team can be added by editing the trust policy in under one hour, with no platform-team involvement.

## Phase 6 — Mesh hardening (week 15–18)

**Goal:** Move from "working pilot" to "ready for the tenth team."

**Deliverables:**
- Layer 6 (security/abuse) tests running nightly with alerting.
- `HumanReviewExecutor` reference implementation, with a queue + minimal review UI.
- `ChainExecutor` with a pluggable security wrapper (PII scrub + prompt-injection filter slot).
- Capacity headroom demonstrated: the platform handles 10× pilot peak with current infra.
- Quarterly mutation-testing job for crypto and processor.
- Disaster-recovery drill: lose the registry primary, fail over, verify mesh recovers.

**Acceptance:**
- Security team signs off. Capacity model is documented. DR drill completes within RTO/RPO targets in [10](10-runbooks-and-slos.md).

## Phase 7 — Self-service onboarding (week 19+)

**Goal:** Reduce platform-team load to "registry maintenance + escalations." Teams onboard themselves.

**Deliverables:**
- Self-service onboarding portal: a team can register a new team-AI, generate a KMS key, and stand up an inbox without filing a ticket.
- Pairing requests flow through the discovery portal: requester clicks "request pairing," recipient team approves in their dashboard.
- Default trust policy templates published; teams pick a template instead of authoring policy.
- Quarterly review cadence: every team-AI's pairings, scopes, and rate limits reviewed for staleness.

**Acceptance:**
- A new team-AI is live and exchanging envelopes within one business day with zero platform-team intervention.

---

## Out of scope (explicitly)

These are valid concerns but not blocking for v1:

- A custom transport beyond HTTP. The reference HTTP transport is sufficient.
- Cross-environment envelopes (prod sender to staging recipient or vice versa). Treat each environment as its own mesh.
- Federation across multiple enterprises. EPP supports it, but the registry is single-tenant in v1.
- A general-purpose policy DSL. Trust policies are simple structured records; no DSL until a real need appears.
- A "marketplace" of pre-built executors. Teams build their own; the platform ships the four reference executors.

## Dependencies between phases

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 5 ──► Phase 6 ──► Phase 7
                                          │           ▲
                                          ▼           │
                                       Phase 4 ───────┘
```

Phase 4 (receipt warehouse + discovery) blocks Phase 5 because the pilot needs auditability and the second team needs discoverability.
