# 06 — Security Threat Model

STRIDE-style enumeration of threats specific to an internal AI mesh built on EPP, and the controls that mitigate each. Use this with [`docs/threat-model.md`](../threat-model.md) which covers the protocol-level threats in more depth.

## Trust boundaries

```
┌──── Operator (human) ────────────────────────────────────────────────┐
│  authenticated via org SSO + MFA                                     │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ OIDC bearer token
                                ▼
┌──── Platform Services (Identity Registry, Audit, Receipts) ──────────┐
│  authoritative state, behind mTLS + OIDC                             │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ pubkey lookups, certs
                                ▼
┌──── Inbox Process (per team-AI) ─────────────────────────────────────┐
│  runs verification pipeline; holds no private keys                   │
└──────┬───────────────────┬────────────────┬──────────────────────────┘
       │ Sign() calls      │ envelope I/O   │ executor invocation
       ▼                   ▼                ▼
┌─────────────┐   ┌───────────────────┐   ┌────────────────────────────┐
│   KMS       │   │  Other Inboxes    │   │  Team-owned executor       │
│   (HSM)     │   │  (mTLS mesh)      │   │  (LLM, queue, human review)│
└─────────────┘   └───────────────────┘   └────────────────────────────┘
```

The boundaries that matter most: **operator → platform**, **platform → inbox**, **inbox → KMS**, **inbox → inbox**, **inbox → executor**.

## STRIDE per asset

### Asset: a team-AI's private signing key

| Threat | Vector | Control |
|---|---|---|
| **Spoofing** | Attacker generates own keypair and tries to register it as the team-AI's | Registration requires operator OIDC token; KMS key creation is restricted to platform team service identity; certificate chain to org identity issuer prevents pubkey impersonation |
| **Tampering** | Attacker modifies the key in storage | Key never leaves KMS HSM; tamper-evident KMS audit log |
| **Repudiation** | Team claims "we didn't sign that envelope" | KMS Sign call audit log + receipt warehouse; both are append-only |
| **Information Disclosure** | Key material leaks | KMS HSM enforces non-exportability; `Sign` is the only allowed operation |
| **Denial of Service** | Attacker exhausts KMS Sign quota | Per-team-AI KMS rate limit; inbox-side queue when rate exceeds threshold; alert on quota approach |
| **Elevation of Privilege** | Attacker gains rights to use the key | KMS key policy restricts `Sign` to one specific service identity; SSO MFA for any policy change |

### Asset: a team-AI's pubkey registration

| Threat | Vector | Control |
|---|---|---|
| **Spoofing** | Attacker writes to identity registry directly to add a pubkey | Registry writes require OIDC token + step-up MFA; database-level RBAC blocks direct writes outside the registry service; audit log + alert on direct DB writes |
| **Tampering** | Attacker modifies an existing team-AI's pubkey | Registry pubkeys are append-only; updates are new rows with role transitions, not in-place edits; immutable audit log |
| **Repudiation** | Operator claims they didn't add the pubkey | Operator OIDC token JTI captured in audit log; non-repudiable |
| **Information Disclosure** | Pubkeys leak | Pubkeys are not secret; leak is not a threat |
| **Denial of Service** | Registry overload | Read-heavy workload cached at inboxes; registry rate-limits writes; reads behind CDN-style cache |
| **Elevation of Privilege** | A team registers a team-AI claiming it belongs to another team | `team` field on `team_ais` is set from operator's OIDC org membership claim, not request body |

### Asset: an inbox's trust registry

| Threat | Vector | Control |
|---|---|---|
| **Spoofing** | Attacker pretends to be the recipient team and adds themselves as a trusted sender | Trust registry admin API requires the operator to be in the recipient team's authorization group (from OIDC group claim); no other auth path |
| **Tampering** | Attacker modifies trust policy to allow themselves | Same as Spoofing; plus full audit log on every change; plus `default_action='deny'` so missing entries fail closed |
| **Repudiation** | Team claims a policy entry was not authorized | Audit log captures actor, time, request body |
| **Information Disclosure** | Trust policy leaks revealing org structure | Trust policies are visible only to the recipient team and platform operators; the discovery portal shows pairings publicly but only after the recipient team explicitly opts each pairing into the public listing |
| **Denial of Service** | Attacker fills trust policy with junk entries to slow lookups | Per-recipient policy size cap (default: 10,000 sender entries); admin API rate-limited |
| **Elevation of Privilege** | Sender escalates from log-only to live | The `promote` admin endpoint requires recipient-team operator + reason + the log-only window must have elapsed |

### Asset: an envelope in flight

| Threat | Vector | Control |
|---|---|---|
| **Spoofing** | Attacker forges an envelope claiming to be from a trusted sender | Ed25519 signature; canonical encoding; pubkey resolved from registry, not from envelope itself |
| **Tampering** | Attacker modifies envelope in transit | Signature covers all signed fields; mTLS between inboxes adds wire-level integrity |
| **Repudiation** | Sender denies sending the envelope | Receipt warehouse stores the envelope signature, sender pubkey, and a vouching certificate chain |
| **Information Disclosure** | Eavesdropper reads envelope payload | Service-mesh mTLS encrypts wire traffic; payloads not stored by platform (only metadata in receipts) |
| **Denial of Service** | Flood inbox with envelopes | Per-sender rate limiter (token bucket); per-inbox global rate limit; load shedding at inbox HTTP layer with `503` |
| **Elevation of Privilege** | Sender uses scope they're not authorized for | Pipeline step 8 (scope policy) denies; receipt records the denial |

### Asset: replay protection

| Threat | Vector | Control |
|---|---|---|
| **Replay** | Attacker captures legitimate envelope and resends it | Pipeline step 7 (nonce check) — `(sender, nonce)` recorded with TTL = envelope max lifetime |
| **Cross-recipient replay** | Attacker submits B's envelope to C | Pipeline step 2 (recipient match) blocks; signature also covers `recipient` field |
| **Late replay** | Attacker waits past nonce TTL and replays | Pipeline step 4 (expiry) blocks; envelope `expires_at` is signed |
| **Nonce-DB exhaustion** | Attacker floods with unique envelopes to exhaust Redis | Per-sender rate limiter throttles before nonce write; Redis cluster sized for projected load (see [04](04-data-schemas.md)) |

### Asset: receipts and audit log

| Threat | Vector | Control |
|---|---|---|
| **Tampering** | Attacker edits a receipt to hide an action | Receipts written to immutable object storage (S3 object-lock or equivalent); index table is append-only; periodic integrity check compares blob signatures to index |
| **Repudiation** | Team disputes a receipt | Receipt is signed by the recipient inbox; envelope it references is signed by the sender; chain provides non-repudiation |
| **Information Disclosure** | Receipts leak revealing cross-team activity patterns | Receipt query API enforces team-membership authorization; aggregate stats are visible more broadly than individual receipts |
| **Denial of Service** | Audit log overwhelmed | Async write path with persistent buffer; alert on buffer growth |

### Asset: the executor (team-owned, but the platform's reputation is tied to it)

| Threat | Vector | Control |
|---|---|---|
| **Prompt injection** | Sender's `prompt` field contains adversarial content designed to subvert the recipient's LLM | `ChainExecutor` security wrapper with prompt-injection filter; high-stakes scopes route through `HumanReviewExecutor`; prompt-injection catch rate measured in Layer 6 tests |
| **PII leakage from executor logs** | Team's executor logs full prompts at INFO | Reference executors strip prompts at INFO; logging guidance in [07](07-observability.md); CI test for receiving teams |
| **Executor takes destructive action without authority** | A scope grants more capability than the requesting envelope deserves | Recipient team's responsibility; platform recommends `HumanReviewExecutor` for any scope with side effects until autonomous-mode policy is approved |

## Org-specific concerns for a large entertainment company

A few threats are amplified by the org context — guests, brand exposure, regulated data.

| Concern | Mitigation |
|---|---|
| **Guest PII in payloads** | The `delegation.on_behalf_of` field carries a token reference, not the guest's identity in cleartext. Executors that need full guest data fetch it from the existing customer system using the delegation token. Receipts never store the dereferenced PII. |
| **PCI / payment scopes** | Forbidden in v1. Scopes touching payment must wait until a separate certified PCI track. Enforce in the registry: `scopes_offered` with prefix `payment.*` is rejected unless team-AI has a `pci_certified` flag set by security. |
| **Brand voice** | Each receiving team owns guest-facing wording. The mesh transports prompts; it does not generate brand copy. |
| **Legal hold** | Receipt retention complies with org legal hold policy; legal-hold flag on a team-AI extends retention indefinitely until cleared. |
| **Cross-region data residency** | If guests in a regulated region (e.g. EU) interact with a team-AI, that team-AI's inbox and KMS key live in that region. Cross-region envelopes are blocked at policy level, not transport. |

## Threats deliberately accepted

Documented so they're not surprises later:

- **A compromised executor on the recipient side can take an envelope's prompt and act on it as it wishes.** EPP's job ends at delivery; what the recipient AI does is the recipient team's responsibility. Mitigation is at the executor layer (human review, PII scrub), not at the protocol layer.
- **A malicious recipient can lie in receipts.** Receipts say "I did X" — there's no third-party verification that X actually happened. The signature proves the recipient took responsibility, not that the action was correct. This is the same trust model as a signed delivery confirmation.
- **Side-channel timing across teams.** Two team-AIs colluding could use envelope-timing to exfiltrate information. This is a research-grade concern, not addressed in v1.
- **Compromise of KMS itself.** If KMS is compromised, the entire org's security model fails, not just EPP. Out of scope.

## Required security reviews

Before each phase ships:

| Phase | Review |
|---|---|
| 1 | Crypto code review (focus: canonical encoding, signature verification, key isolation) |
| 2 | Identity & access review (focus: registry RBAC, KMS key policies, audit log integrity) |
| 3 | Distributed-state review (focus: nonce registry race conditions, rate limiter atomicity) |
| 4 | Data classification & retention review (focus: receipt warehouse access, PII handling) |
| 5 | Pilot threat model walkthrough with the two pilot teams |
| 6 | Penetration test against the full mesh |
| 7 | Self-service safety review (focus: what an unauthenticated insider could do) |

## Mapping to controls catalogs

For audit narrative, EPP's controls map to common frameworks as follows. Use this when your security team asks "where do you cover NIST control X?"

| Control | Frameworks | Where in EPP |
|---|---|---|
| Identification & authentication | NIST AC-2, ISO A.9 | Identity registry + Ed25519 + cert chain |
| Cryptographic key management | NIST SC-12, SC-13, FIPS 140 | KMS HSM, [05](05-key-management.md) |
| Audit logging | NIST AU-2, AU-9, ISO A.12.4 | Audit log + receipt warehouse + immutable storage |
| Access enforcement | NIST AC-3 | Trust registry, scope policies |
| Replay protection | NIST SC-23 | Nonce registry, expiry, recipient match |
| Non-repudiation | NIST AU-10 | Signed envelopes + signed receipts |
| Boundary protection | NIST SC-7 | Inbox per team-AI, mTLS mesh |
