# 02 — Service Architecture

The platform is a small set of services with sharp responsibilities. This doc names every service, what it owns, what it depends on, and what crosses its boundary.

## The component map

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                              Discovery Portal (R)                              │
│            entity catalog: team-AIs, scopes, on-call, examples                 │
└────────────────────────────────────────┬───────────────────────────────────────┘
                                         │ reads
┌────────────────────────────────────────▼───────────────────────────────────────┐
│                            Identity Registry (W)                               │
│            team-AI metadata, active pubkeys, lifecycle state                   │
└──────────┬───────────────────────────────────────────────┬─────────────────────┘
           │ pulled by                                     │ pushed to
           │                                               │
           │                                       ┌───────▼────────┐
           │                                       │  Audit Log (W) │
           │                                       │  every admin   │
           │                                       │  write         │
           │                                       └────────────────┘
           ▼
┌──────────────────────────┐  ┌──────────────────────────┐  ┌──────────────────┐
│   Team A Inbox Pod (W)   │  │   Team B Inbox Pod (W)   │  │ ... per team-AI  │
│  - 10-step pipeline      │  │  - 10-step pipeline      │  │                  │
│  - trust registry cache  │  │  - trust registry cache  │  │                  │
│  - executor (team-owned) │  │  - executor (team-owned) │  │                  │
└────────┬──────────────┬──┘  └────────┬──────────────┬──┘  └──────────────────┘
         │              │              │              │
         │              │              │              │
         ▼              ▼              ▼              ▼
┌────────────────┐ ┌─────────────────────────┐ ┌────────────────────────────────┐
│ Nonce Registry │ │  Rate Limiter (Redis)   │ │     KMS Signer (managed)       │
│ (Redis, TTL)   │ │  token bucket per       │ │   per-team-AI Ed25519 key      │
│ replay defense │ │  (sender, recipient,    │ │   sign-only operation          │
│                │ │   scope)                │ │                                │
└────────────────┘ └─────────────────────────┘ └────────────────────────────────┘

         │                                     │
         └─────────────┬───────────────────────┘
                       │
                       ▼
        ┌────────────────────────────┐
        │  Receipt Warehouse (W)     │
        │  - blob store (cold)       │
        │  - indexed table (hot)     │
        │  - SIEM stream             │
        │  - query API               │
        └────────────────────────────┘

(W) = writes, (R) = reads
```

## Services owned by the platform team

### Identity Registry

**Responsibility:** Single source of truth for "what team-AIs exist, who owns each, what their current pubkey(s) are, and what state they're in (active / suspended / revoked / retired)."

**Owns:**
- The mapping `team_ai_id → {team, owner, pubkeys[], scopes_offered[], state, created_at, ...}`.
- Lifecycle transitions (register, rotate, revoke, retire).
- The audit log of every change.

**Depends on:** Postgres, the chosen service-identity / OIDC issuer (for operator auth), KMS (for issuing certificates that vouch for team-AI pubkeys, see [05](05-key-management.md)).

**Does not own:** Per-recipient trust policies (that's the trust registry, which lives in each inbox).

**Failure mode:** If the identity registry is down, inboxes serve from cache. Cache TTL is 5 minutes. After cache expiry, inboxes fail-closed on unknown senders.

### Audit Log

**Responsibility:** Append-only record of every operator action against the identity registry, every admin API call, every trust-policy change, every key rotation, every revocation.

**Owns:** A tamper-evident log (typically Postgres write + secondary write to immutable object store).

**Depends on:** Postgres + object store.

**Does not own:** Envelope receipts. Those live in the receipt warehouse. The audit log is for *control-plane* actions; the receipt warehouse is for *data-plane* events.

### Receipt Warehouse

**Responsibility:** Store every receipt produced by every inbox. Make them queryable by operators, security, and the teams themselves.

**Owns:**
- Receipt blobs in object storage (long retention, signed).
- Receipt index in a query store (hot tier, e.g. last 30 days).
- Query API.
- Streaming output to SIEM.

**Depends on:** Object store, query database (BigQuery / Snowflake / Postgres), SIEM ingestion.

**Does not own:** The decision to write a receipt — that's the inbox executor's responsibility. The warehouse is a sink.

### Discovery Portal

**Responsibility:** Make the mesh navigable. Every team-AI has an entity. Operators and other teams can find one, see its scopes and on-call, request to pair.

**Owns:** The catalog UI and the entity-definition format. Pairing-request workflow.

**Depends on:** Identity registry (for entity data), trust registries (for current pairings, read-only), receipt warehouse (for usage stats).

**Does not own:** Authoritative state. Everything in the portal is derived from the identity registry, trust registries, and receipt warehouse.

### Reference Inbox (the deployable)

**Responsibility:** The container that each product team runs to receive envelopes for their team-AI. The platform team builds and signs the image; product teams configure and run it.

**Owns the implementation of:** the 10-step pipeline, trust-registry cache, nonce-registry client, rate-limiter client, executor plug interface, observability emission, healthchecks.

**Does not own:** The executor. Product teams write or configure the executor.

## Components owned by the product team

### Team-AI Inbox Deployment

A product team's deployment of the reference inbox image into their own namespace. Configuration includes:

- Their team-AI ID (mapped to KMS key).
- Their trust registry contents (managed via admin API or GitOps).
- Their executor choice and configuration.
- Their resource sizing (replicas, CPU/memory).

### Executor

The component that decides what happens to a verified envelope. Owned by the product team. May be:

- The platform-shipped `LoggerExecutor` (during pilot).
- The platform-shipped `QueueExecutor` (push to team's existing async work queue).
- The platform-shipped `HumanReviewExecutor` (queue + review UI).
- A custom executor the team writes against the `Executor` interface.
- A `ChainExecutor` wrapping any of the above with security/PII filters.

## Cross-cutting concerns (provided by infrastructure)

These are not services in the EPP sense — they're substrates the platform builds on.

| Substrate | Provided by | Used by |
|---|---|---|
| Service identity / OIDC issuer | Existing org infra | Operator auth, team-AI cert chain (Option B) |
| KMS | Existing org infra | All team-AI signing keys |
| Postgres / managed SQL | Existing org infra | Identity registry, trust registry, audit log, receipt index |
| Redis | Existing org infra | Nonce registry, rate limiter |
| Object storage (S3/GCS) | Existing org infra | Receipt blobs, audit log secondary |
| Service mesh / mTLS | Existing org infra | Inbox-to-inbox transport (defense in depth) |
| Container platform (k8s) | Existing org infra | Inbox deployments |
| Observability stack | Existing org infra | Metrics, traces, logs from inboxes and platform services |
| SIEM | Existing org infra | Receipt stream, audit log stream |

## Boundaries that must not be crossed

These are invariants the architecture depends on. Violating any one of them breaks the trust model.

1. **Private keys never leave KMS.** Inbox processes call KMS to sign; they never hold the private key in process memory.
2. **Identity registry is the only writer of pubkey state.** Trust registries read from it; they never directly accept "this is my new pubkey" from a sender.
3. **Trust registries are per-recipient.** There is no global "who can talk to whom" table. Each recipient owns its own policy.
4. **The receipt warehouse is append-only.** No edits, no deletes. Retention is managed by lifecycle policy, not by writes.
5. **The inbox does not modify envelopes.** It verifies, executes, and produces receipts. Anything that would mutate an envelope's signed bytes is forbidden.
6. **The discovery portal is derived state.** It never holds authoritative data; if it disagrees with the identity registry, the registry wins.

## Service ownership matrix

| Service | Build | Operate | On-call |
|---|---|---|---|
| Identity Registry | Platform team | Platform team | Platform team |
| Audit Log | Platform team | Platform team | Platform team |
| Receipt Warehouse | Platform team | Platform team | Platform team |
| Discovery Portal | Platform team | Platform team | Platform team |
| Reference Inbox image | Platform team | — | — |
| Team-AI Inbox deployment | Product team (uses image) | Product team | Product team |
| Executor | Product team | Product team | Product team |
| Nonce Registry (Redis) | Platform team (provisions) | Platform team | Platform team |
| Rate Limiter (Redis) | Platform team (provisions) | Platform team | Platform team |
| KMS keys | Platform team (provisions) | Platform team | Platform team (key issuance), Product team (usage) |
