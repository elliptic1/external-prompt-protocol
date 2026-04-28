# Use Case: Enterprise AI Mesh for a Large Experiences Company

**Audience:** Internal developer platform leaders, AI/ML platform owners, enterprise architects
**Status:** Use case narrative — not a product commitment
**Last updated:** 2026-04-27

---

## The company shape

Imagine a large, decades-old company whose business is delivering face-to-face experiences to tens of millions of customers a year — properties that span hospitality, ticketed venues, retail, food service, transportation, live entertainment, and licensed media. Behind every customer-facing surface is a long tail of internal product and engineering teams:

- A team that owns the booking flow.
- A team that owns the in-venue mobile app.
- A team that owns the loyalty program.
- A team that owns merchandise.
- A team that owns wayfinding and accessibility.
- A team that owns workforce scheduling.
- A team that owns the call center.
- A team that owns the website.
- ...and dozens more, each with their own roadmap, their own director, their own service partners (cloud platform, identity, data platform, security), and their own backlog.

Each team is small — a handful of engineers, a tech manager, a product manager. Each team is, independently, building **something with AI**: a concierge, a planner, a recommender, a copilot, a triage agent, a knowledge bot. Each one is impressive in isolation. Each one was built without coordinating with the others, because that is how the org works. The silos are real, durable, and will not be reorged away.

## The problem

The customer experience is *one continuous trip* — they book, they arrive, they eat, they shop, they leave a review, they call support. But each team's AI only knows about its own slice. When a guest's flight is delayed and the hospitality AI knows the new arrival time, the dining-reservations AI does not. When the merchandise AI sees a guest browsing a specific franchise, the in-venue concierge AI cannot use that signal. When the call-center AI resolves an issue, the loyalty AI never finds out.

The natural instinct is "let's give every AI access to every other team's APIs." This fails for predictable reasons:

1. **Authorization sprawl.** Every team would have to issue and rotate credentials for every other team. Onboarding a new AI means N new integration tickets.
2. **No shared trust language.** Team A's "service account" means something different than Team B's. Audit and revocation are inconsistent.
3. **Schema lock-in.** REST/GraphQL contracts force the requester to know the responder's data shape. Two AIs that *speak natural language internally* end up wrapping LLM output into rigid JSON just to cross a team boundary.
4. **No record of intent.** When AI-1 asks AI-2 for something and AI-2 acts, there is no signed, tamper-evident record of *who asked, what they asked for, and on whose behalf* — which is exactly what compliance, security, and incident response need six months later when something goes sideways.
5. **MCP doesn't solve this.** MCP is a great tool-calling protocol *within* one agent's process boundary. It is not a cross-org trust fabric. It assumes the caller and the tool are in a single trust domain. That assumption breaks the moment Team A's AI wants to talk to Team B's AI.

## The proposal: an internal AI mesh built on EPP

Stand up the External Prompt Protocol as the **inter-team AI message bus** for the company. Each team continues to own and operate its own AI exactly as they do today. What changes is *how* those AIs reach each other.

### How it looks in practice

Every team's AI gets two things:

1. **An Ed25519 keypair** registered in a central internal registry (think: an internal extension of the company's existing service identity system). The public key is the team-AI's identity. The private key never leaves their service.
2. **An EPP inbox** — a small FastAPI process the team runs alongside their AI, with a trust policy that says "I will accept signed envelopes from these other team-AIs, at this rate, with these payload constraints, and route them to my AI as a prompt."

When the in-venue concierge AI wants to ask the dining AI "is there a 7pm table for 4 at any of the steakhouses near our guest's current location?", it does not call a REST endpoint. It signs an envelope with its team's key, posts it to the dining AI's inbox, and the dining AI's executor delivers the natural-language prompt into its own model. The reply comes back as a signed envelope on the concierge's inbox.

### Why each property of EPP matters here

| EPP property | Why it matters in this org |
|---|---|
| **Ed25519 signed envelopes** | The receiving team can prove *which* team's AI made the request. No shared secrets, no rotation hell. |
| **Per-sender trust policies** | The dining AI's team decides which other team-AIs may talk to it, at what rate, and with what payload size — without filing a security ticket per integration. |
| **Nonce + replay protection** | Built-in. Replays of an old prompt cannot trigger a duplicate booking, refund, or page. |
| **Pluggable executors** | The dining AI team picks how envelopes land — directly into their LLM, into a queue for human review, into a logger-only dry run during pilot. They do not have to rewrite their AI to participate. |
| **Receipts** | Every cross-team interaction produces a signed receipt. That receipt is the audit trail compliance has been asking for since the first AI shipped. |
| **Natural-language payloads** | Two AIs can negotiate intent in language, not in pre-agreed JSON. Schema drift across teams stops being a coordination tax. |
| **Open spec, MIT** | No vendor lock-in. The platform team owns the registry and the libraries; product teams own their inboxes. |

### What the platform team provides

To make this real internally, a small central platform team would own:

- **Identity registry.** A service that issues team-AI keypairs, ties them to existing org identity (team, cost center, on-call rotation, data classification), and publishes the public-key directory.
- **Reference inbox.** A hardened, opinionated EPP inbox container that any team can deploy with one config file. Comes with logging, metrics, and tracing wired into the company's existing observability stack.
- **Trust policy templates.** Pre-baked policies for common patterns: "accept from any AI in my division," "accept only from listed senders," "log-only mode for new senders for the first 30 days."
- **Receipt warehouse.** A central, append-only store of envelope receipts, queryable by security, compliance, and the teams themselves. This is the "what did the AIs say to each other" system of record.
- **Discovery.** A lightweight catalog where teams publish "my AI accepts envelopes about X, here is my public key, here is an example envelope." Think internal `npm search` for team-AIs.

### What the platform team explicitly does NOT do

- Does not run anyone's AI.
- Does not see envelope payloads in cleartext (only metadata + receipts).
- Does not own the trust decisions. Each team owns its own inbox policy.

That separation is what makes the model org-compatible. Platform owns the rails; teams own the cars.

## A concrete first pairing

A use case is not real until two specific teams want it. The smallest credible pilot:

> **Pilot:** The in-venue concierge AI (Team A) and the dining-reservations AI (Team B) exchange envelopes for one venue, for one quarter, in log-only mode for the first two weeks, then live for the rest.

Success criteria:

- Team B onboards Team A as a trusted sender in under one day, with no security tickets opened.
- 100% of cross-team requests have a signed receipt retrievable by either team.
- Mean cross-team request latency p95 under 500ms.
- Zero credential rotations required during the pilot.
- At end of quarter, a third team can be added by Team B in under one hour by editing their trust policy.

If those numbers land, the pattern generalizes. The third team is the proof; the tenth team is the platform.

## Why this is interesting strategically

- **It does not require any team to give up their AI.** Every team keeps their roadmap, their model choices, their UX. The mesh is additive.
- **It does not require a reorg.** It works *with* the silos, not against them. Trust is expressed in policy, not org structure.
- **It produces an audit trail by default.** The receipts are not a feature anyone has to remember to turn on.
- **It is open-source and externally inspectable.** EPP is MIT-licensed and the spec is public. The company is not betting on a closed vendor protocol that could disappear or get repriced.
- **It composes with everything else.** EPP envelopes can carry MCP tool-call references, can be relayed through HTTP or queues, and can sit in front of any model from any vendor. It is a *transport for intent*, not a replacement for any existing AI tooling.

## What it would take to validate this internally

1. **Two willing teams.** Identify two team-AIs whose customers would benefit from cross-team context *today*. Concierge ↔ dining is one candidate; loyalty ↔ merchandise is another.
2. **A platform sponsor.** A director-level owner in the developer platform / AI platform org who can stand up the registry and reference inbox.
3. **A 90-day pilot with explicit success criteria** (the ones above, or something close to them).
4. **A security review of the pilot envelope, not of the whole concept.** The pilot is small and reversible. Scope the review accordingly.

After 90 days, the question is not "should we build this?" — it is "which ten teams join next?"

---

## Technical architecture deep dive

This section is the part you will hand to the platform architect. It maps every EPP responsibility to a discrete component, so you can walk into a meeting with your internal AI cloud platform team and say "this piece needs a key vault, this piece needs a queue, this piece needs an OIDC integration" without hand-waving.

### The envelope, in one diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Envelope (signed JSON, ~1–4 KB typical)                                     │
├──────────────────────────────────────────────────────────────────────────────┤
│  version           "1"                                                       │
│  envelope_id       UUIDv4              ← idempotency key                     │
│  sender            ed25519 pubkey hex  ← team-AI identity                    │
│  recipient         ed25519 pubkey hex  ← target team-AI identity             │
│  timestamp         ISO-8601 UTC        ← signed                              │
│  expires_at        ISO-8601 UTC        ← signed; receiver enforces           │
│  nonce             base64 random       ← replay defense                      │
│  scope             string              ← policy match key (e.g. "dining.rsvp")│
│  conversation_id   UUID (optional)     ← threading across envelopes          │
│  payload                                                                     │
│    ├── prompt        natural language                                        │
│    ├── context       structured dict (guest_id, venue_id, locale, ...)       │
│    ├── metadata      free-form                                               │
│    └── payload_type  schema hint (e.g. "table-availability-request")         │
│  signature         ed25519 over canonical-encoded fields above               │
└──────────────────────────────────────────────────────────────────────────────┘
```

Three properties matter for your platform mapping:

1. **The signature covers a canonical, deterministic encoding** of the fields. Any middlebox that mutates the envelope breaks verification — which is the point. This means you cannot put a "rewriting" API gateway in the middle. Pass-through L7 only.
2. **`envelope_id` is the natural idempotency key.** Any retry layer (queue, mesh sidecar, client SDK) should retry on `envelope_id`, and the receiver dedupes via the nonce registry. Same envelope sent twice = one execution, two receipts pointing at the same result.
3. **`scope` is the policy axis.** It is a free-form string the sender chooses (`"dining.rsvp"`, `"loyalty.lookup"`, `"merch.recommendation"`). Trust policies are keyed on `(sender_pubkey, scope)`. This is your knob for "Team A may ask Team B about dining but not about payments."

### The 10-step verification pipeline (what an inbox actually does)

Every envelope that lands on a team's inbox flows through this pipeline before the team's AI ever sees it. Each step is a place where your platform can inject a hook, a metric, or a trace span.

| # | Step | What it checks | Failure mode |
|---|------|---------------|--------------|
| 1 | **Parse** | Valid JSON, valid envelope schema (Pydantic) | `400 invalid_envelope` |
| 2 | **Recipient match** | `envelope.recipient == this_inbox_pubkey` | `403 wrong_recipient` |
| 3 | **Timestamp window** | `now - clock_skew < timestamp < now + clock_skew` | `400 stale_or_future` |
| 4 | **Expiry** | `now < expires_at` | `400 expired` |
| 5 | **Sender known** | Sender pubkey is in trust registry | `403 untrusted_sender` |
| 6 | **Signature verify** | Ed25519 verify over canonical encoding | `401 bad_signature` |
| 7 | **Nonce check** | Nonce not seen before for this sender | `409 replay` |
| 8 | **Scope policy** | `(sender, scope)` is allowed by policy | `403 scope_denied` |
| 9 | **Rate limit** | Token bucket has capacity for this sender | `429 rate_limited` |
| 10 | **Execute** | Hand payload to executor | depends on executor |

Steps 1–9 are pure CPU + small state lookups. Step 10 is where the team's AI work happens. The pipeline is synchronous in the reference impl but the executor at step 10 can be async (queue-backed) without changing the protocol.

### Component-by-component mapping to a typical internal cloud platform

This is the table to bring to your platform architect. Left column is the EPP responsibility; middle is what it needs from infrastructure; right is the typical internal-platform service that satisfies it.

| EPP responsibility | What it needs | Typical internal platform mapping |
|---|---|---|
| **Identity registry** (team-AI keypairs + metadata) | Long-lived service identity bound to org metadata (team, cost center, on-call, data classification). Public key directory. Revocation. | Existing service-identity / SPIFFE-style system + a thin EPP-specific projection that adds the public key field. Reuse, do not rebuild. |
| **Private key custody** | Each team's private key must never leave a controlled boundary. Sign operations only. | Cloud KMS (AWS KMS, GCP KMS, HashiCorp Vault, internal HSM). EPP signing becomes a `Sign(envelope_hash)` call. The signing library needs an `Ed25519Signer` interface — already present at `epp/crypto/keys.py` — pluggable to KMS. |
| **Inbox runtime** | HTTP server, stateless, horizontally scalable, low-latency | Your standard internal container platform (Kubernetes namespace per team, or shared serverless). Reference impl is FastAPI + uvicorn, OCI-packageable. p50 envelope verify is sub-millisecond CPU; the bottleneck is always step 10. |
| **Trust registry** (per-sender, per-scope policy) | Read-mostly config store, fast lookups, audited writes | Whatever your platform uses for service config: Consul, etcd, a config service, or a dedicated Postgres table behind an internal admin UI. Source of truth in git, hydrated to a fast cache. |
| **Nonce registry** (replay defense) | Set membership, TTL = max envelope lifetime (typically 5–15 min), per-sender keyspace | Redis with TTL on keys is the obvious fit. One key per `(sender, nonce)`, expires when the envelope's `expires_at` passes. Memory bound: `senders × peak_envelope_rate × max_lifetime`. For 100 senders × 100 env/sec × 600s, that's ~6M keys — trivial for Redis. |
| **Rate limiter** | Token bucket per `(sender, recipient, scope)`, distributed if inbox is multi-replica | Redis token bucket (Lua script for atomicity) or your platform's existing rate-limiter (Envoy/Istio, an internal service). Reference impl is in-process; production needs distributed state. |
| **Receipt warehouse** | Append-only, queryable by sender, recipient, envelope_id, time range. Long retention (compliance). Signed. | Object storage (S3/GCS) for the receipt blobs + an indexed table (BigQuery / Snowflake / Postgres) for query. Receipts are small (~500 bytes JSON). One year of 100 envelopes/sec = ~1.6 TB raw, ~300 GB compressed. |
| **Discovery / catalog** | "Which team-AI accepts which scopes? Where do I send envelopes?" | Internal dev portal (Backstage, an internal equivalent). One Backstage entity per team-AI, with public key, supported scopes, example envelopes, on-call rotation. |
| **Transport** | HTTP POST `/epp/v1/submit` between inboxes | Your existing east-west service mesh. EPP-over-mTLS gives you defense-in-depth (envelope signature is the inner layer; mesh mTLS is the outer). Mesh authz can be permissive — EPP signature is the authoritative check. |
| **Observability** | Metrics, traces, logs per envelope step | Standard OpenTelemetry. Each pipeline step emits a span. Add a `epp.envelope_id` and `epp.scope` baggage tag so you can trace cross-team conversations end-to-end. |
| **Audit** | "Who said what to whom, when, with what outcome" | Receipt warehouse is the source of truth. Pipe receipts to your SIEM as a secondary stream for security. |
| **Key rotation** | Sender pubkey changes; trust registry must accept old + new for a window | Standard KMS rotation primitives. Trust registry stores a list of accepted pubkeys per team-AI, not a single value. Old pubkey stays valid for the rotation window, then is removed. |
| **Revocation** | A compromised team-AI's pubkey must stop being honored everywhere fast | Trust registry hot-path is cache-backed. Revocation is "remove from registry + bust caches." Receivers fail-closed on cache miss + lookup failure. SLA on revocation propagation: target < 60s. |

### Where the team-AI plugs in: the executor interface

This is the thing every team owns and every team gets to choose. The executor is a single Python interface:

```python
class Executor:
    async def execute(self, envelope: Envelope) -> ExecutorResult: ...
```

Common executor patterns the platform should ship as reference implementations:

- **`DirectModelExecutor`** — Hand `payload.prompt + payload.context` to the team's existing LLM client (OpenAI, Anthropic, internal model gateway). Synchronous. Lowest latency.
- **`QueueExecutor`** — Push envelope onto the team's existing async work queue (SQS, Pub/Sub, Kafka). Receipt returns "accepted, work_id=…". Team's existing worker pool processes it. Highest decoupling.
- **`HumanReviewExecutor`** — Push to a review queue with a UI; nothing reaches the model until a human approves. Right default for high-stakes scopes (refunds, bookings > $X, anything touching guest PII).
- **`LoggerExecutor`** — Log only, no execution. The right setting for the first 2 weeks of any new sender relationship. Receipts say "logged." Use this to validate volume and content before flipping to live.
- **`ChainExecutor`** — Wrap another executor with pre/post hooks (PII scrub, prompt-injection filter, output policy check). This is where your security team's existing prompt-firewall plugs in.

### Identity model: how a team-AI proves who it is

The platform decision that has the longest blast radius is the identity model. Two viable shapes, pick one and commit:

**Option A — Pure key-based (simplest):**
- Each team-AI has one Ed25519 keypair.
- The pubkey *is* the identity.
- Registry maps `pubkey → {team, scopes_offered, on_call, ...}`.
- Pro: minimal moving parts, works offline, signatures verifiable forever.
- Con: rotation requires registry update + trust-registry update everywhere.

**Option B — Key-chained to existing org identity (recommended):**
- Each team-AI's Ed25519 pubkey is *certified* by your existing org identity system (an internal CA, SPIFFE issuer, or OIDC issuer issuing a JWT that vouches for the pubkey).
- The envelope still carries just the pubkey; the receiver verifies the signature directly. The certificate is fetched out-of-band from the registry on first contact, cached.
- Pro: revocation is a single CA operation. Onboarding inherits org identity provisioning. SOC2 / SOX auditors recognize the pattern.
- Con: more infrastructure. The CA is now a dependency of the trust fabric.

For an enterprise of this size, Option B is almost certainly correct. EPP itself does not care which one you pick — the protocol is the same — but the platform team owns this choice on day one and changing it later is painful.

### Delegation: when team A's AI acts on behalf of a guest

The protocol already has a `Delegation` model (`on_behalf_of` is a pubkey, `authorization` is optional evidence). The pattern in this org:

- The guest never has a keypair. They have an account in the existing identity system.
- When a team-AI acts on a specific guest's behalf, the envelope carries `delegation.on_behalf_of = <guest_identity_token_hash>` and `delegation.authorization = <signed token from your identity system>`.
- The receiving team-AI's executor checks the authorization token against the existing identity system before acting.
- Receipts capture the delegation, so audit can answer "did Team A really have authority to ask about guest X?"

This is the path that makes EPP usable for guest-context-bearing requests without inventing a parallel identity world.

### Failure modes and what to monitor

The platform team's dashboard should have, at minimum:

- **Envelope verification failure rate by step** (steps 1–9 above) — sudden spikes in step 6 (bad signature) usually mean a sender deployed with the wrong key. Spikes in step 7 (replay) mean someone's retry logic is broken. Spikes in step 8 (scope denied) mean a team is calling outside their negotiated agreement.
- **p50 / p95 / p99 end-to-end envelope latency**, broken down by sender → recipient pair.
- **Trust registry cache hit rate** — drops here mean revocation propagation is working, but if it stays low you have a config-store problem.
- **Receipt write success rate** — receipts must not be lost. This is your audit trail. Page on this.
- **Per-sender rate-limit rejection rate** — a sender consistently hitting limits is either misbehaving or the limit is wrong; both need a human.

### Capacity planning sketch

Numbers to give your platform team a starting point. Assumes the protocol becomes the default for cross-team AI calls.

- **Envelope size:** 1–4 KB typical, 64 KB max with payload.
- **Verify CPU:** ~100 µs per envelope (Ed25519 verify + JSON parse + lookups). One modern core handles ~10k env/sec sustained.
- **Inbox memory:** ~50 MB baseline + nonce registry working set (Redis, not in-process).
- **Network:** negligible — east-west traffic, small payloads.
- **Storage:** receipts are the only thing that grows. Plan for `envelopes/sec × 500 bytes × retention_seconds`. One year, 100 env/sec, hot tier 30 days, cold tier rest.

For 100 team-AIs averaging 10 env/sec each (= 1000 env/sec aggregate cross-team), the entire mesh fits on a handful of inbox replicas per team, one Redis cluster, one config store, and a standard data-warehouse table. None of these are exotic. All of them already exist on a typical internal platform.

### The minimum viable platform

If you have to ship this on a 90-day timeline, the irreducible core:

1. **Identity registry** — even just a Postgres table behind an admin API.
2. **KMS-backed signer** — one integration with your existing KMS.
3. **Reference inbox container** — already exists in this repo; package it as your standard internal image.
4. **Trust registry with file or DB backend** — already exists in this repo; wire it to your config service.
5. **Nonce registry on Redis** — swap the in-memory implementation.
6. **Receipt sink** — a single executor wrapper that writes every receipt to your warehouse.
7. **One dashboard** — verification failures, latency, receipt write rate.

That is the v1. Discovery, human-review executor, prompt-firewall chain, fancy delegation flows — all v2.

---

## Appendix: what this is not

- **Not a customer-facing product.** Customers do not see envelopes. They see better answers from the AIs they already use.
- **Not a replacement for the existing service mesh.** Team services keep talking to team services over the existing mesh. EPP is a *new* lane specifically for AI-to-AI prompt traffic.
- **Not a model.** EPP does not provide an AI. It provides the trust fabric between AIs the company already has.
- **Not coupled to any one cloud or vendor.** The reference implementation is Python, runs anywhere, and the protocol is transport-agnostic.
