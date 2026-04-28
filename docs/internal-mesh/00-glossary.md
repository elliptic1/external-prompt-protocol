# 00 — Glossary

Canonical definitions. Use these terms exactly. Any builder doc that drifts from these terms should be corrected, not worked around.

## Identities and actors

| Term | Definition |
|---|---|
| **Team-AI** | An AI agent owned by one product team. Has exactly one Ed25519 keypair. Is the unit of identity in the mesh. |
| **Sender** | The team-AI that signed an envelope. Identified by `envelope.sender` (pubkey hex). |
| **Recipient** | The team-AI an envelope is addressed to. Identified by `envelope.recipient` (pubkey hex). |
| **Principal** | The human end-user (typically a guest/customer) on whose behalf a team-AI may be acting. Carried in `envelope.delegation.on_behalf_of`. |
| **Platform team** | The central team that owns the registry, reference inbox, receipt warehouse, and shared infrastructure for the mesh. |
| **Product team** | A team that owns one or more team-AIs participating in the mesh. |
| **Operator** | A human (platform engineer, security responder) who interacts with the mesh through admin APIs. |

## Protocol-level objects

| Term | Definition |
|---|---|
| **Envelope** | The signed unit of communication between team-AIs. Schema: see [`docs/spec.md`](../spec.md) and `epp/models.py`. |
| **Payload** | The contents of an envelope: a natural-language `prompt`, optional structured `context`, optional `metadata`, optional `payload_type` hint. |
| **Receipt** | The signed response from an inbox describing the outcome of processing an envelope. Either a `SuccessReceipt` or an `ErrorReceipt`. |
| **Nonce** | Random bytes (base64 in the envelope) used to detect replay. Unique per `(sender, nonce)` within the envelope's lifetime. |
| **Scope** | A sender-chosen string that names the kind of request (e.g. `"dining.rsvp"`, `"loyalty.lookup"`). The policy axis for trust decisions. |
| **Conversation ID** | Optional UUID threading multiple envelopes into a logical exchange. |
| **Delegation** | Optional envelope field declaring "I am acting on behalf of principal X" with optional authorization evidence. |
| **Canonical encoding** | The deterministic byte-encoding of envelope fields used for signing and verification. Defined by `create_canonical_payload()` in `epp/crypto/signing.py`. |

## Platform services

| Term | Definition |
|---|---|
| **Identity registry** | The service that maps team-AI identifiers to current pubkey(s), team metadata, and lifecycle state. |
| **Trust registry** | Per-recipient configuration: who may send envelopes to me, with what scope, at what rate. One trust registry instance per inbox. |
| **Nonce registry** | Per-recipient store of recently-seen `(sender, nonce)` pairs for replay detection. Backed by Redis. |
| **Rate limiter** | Per-recipient enforcement of token-bucket limits keyed by `(sender, scope)`. Backed by Redis. |
| **Inbox** | The EPP server process for one team-AI. Runs the 10-step verification pipeline. |
| **Executor** | The component an inbox hands a verified envelope to. Where the team-AI's actual work happens. |
| **Receipt warehouse** | The append-only store of all receipts. Source of truth for audit. |
| **Discovery portal** | The internal catalog where teams publish their team-AI identity, supported scopes, example envelopes, and on-call rotation. |
| **Admin API** | The HTTP API operators use to manage the registry, suspend senders, rotate keys, etc. |

## Operational concepts

| Term | Definition |
|---|---|
| **Onboarding** | The process by which a team registers a new team-AI: provisions a keypair, registers the pubkey, declares supported scopes. |
| **Pairing** | The process by which a sender team-AI is granted permission to send to a recipient team-AI. Requires action by the recipient team. |
| **Rotation** | Replacing a team-AI's signing key with a new one. The old key remains valid for a rotation window. |
| **Revocation** | Marking a team-AI's pubkey as no longer trusted. Takes effect within the revocation propagation SLA. |
| **Log-only mode** | An executor configuration that records envelopes but does not act on them. The default for the first 14 days of any new pairing. |
| **Live mode** | An executor configuration that acts on envelopes. The state after a pairing graduates from log-only. |
| **Pipeline step** | One of the 10 verification steps every envelope passes through. See [`docs/use-case-enterprise-ai-mesh.md`](../use-case-enterprise-ai-mesh.md). |

## Conventions

- All identifiers that travel over the wire use lowercase hex for pubkeys, base64 for nonces and signatures.
- All timestamps are ISO-8601 with explicit UTC offset (`Z` suffix).
- All durations in config and APIs are seconds (integer) unless suffixed with a unit.
- All sizes are bytes unless suffixed.
- API error codes match the protocol spec; do not invent new ones at the platform layer.
