# 05 — Key Management

The trust model collapses if private keys leak. This doc specifies how keys are created, stored, used, rotated, and revoked.

## Identity model — pick Option B

[`02 — Service architecture`](02-service-architecture.md) referenced this choice; this doc commits to it.

**Option B: Key chained to existing org identity.**

- Every team-AI has an Ed25519 keypair generated in and held by the org KMS.
- The pubkey is *certified* by the org's existing identity issuer (internal CA, SPIFFE issuer, or OIDC issuer signing a JWT that vouches for the pubkey).
- Envelopes carry just the raw pubkey; receivers verify the signature directly.
- Receivers fetch the certificate out-of-band (from the identity registry), cache it, and use it to gate trust-registry insertion.

Option A (pure key-based, no chain to org identity) is allowed only for the **dev** environment to keep the loop fast.

## Key generation

Keys are generated **inside KMS** and never leave. The signing library uses a `Signer` interface:

```python
class Signer(Protocol):
    def public_key_hex(self) -> str: ...
    def sign(self, message: bytes) -> bytes: ...
```

Two implementations:

- `LocalKeypairSigner` — for tests and dev only. Keys live in process memory.
- `KmsSigner` — wraps the org KMS. Calls `KMS.Sign(key_arn, sha512(message))` since Ed25519 in most KMS APIs is "Ed25519ph" (pre-hashed). Verify the canonical encoding step still produces a verifiable signature when round-tripped through the chosen KMS — some providers require specific encoding wrappers. Test with the contract suite.

The reference `epp/crypto/keys.py` ships `LocalKeypairSigner`. Add `KmsSigner` as a separate module that depends on the chosen KMS SDK.

## Key storage requirements

| Property | Requirement |
|---|---|
| Generation location | Inside KMS HSM. No raw private key ever exposed to userland. |
| Algorithm | Ed25519 only. Reject any other algorithm at registration time. |
| Per-key access | Only the team-AI's own service identity may invoke `Sign` on its own key. Enforce via KMS key policy + IAM. |
| Audit | Every `Sign` call logged in KMS audit trail. |
| Backup | KMS provider's standard backup. Do not export key material for backup. If KMS loses the key, the team-AI must rotate to a new key. |
| Cross-region | Keys may be replicated within KMS provider's region group only if envelope traffic crosses regions. Default: single region. |

## Onboarding a new team-AI key

1. Operator runs `eppctl-admin team-ai register` (or uses the admin UI).
2. The admin command calls KMS to `CreateKey` with `KeyUsage=SIGN_VERIFY`, `KeySpec=ED25519`, alias `epp/{team_ai_id}`.
3. The admin command sets the key policy to allow `Sign` only from the service identity that will run that team-AI's inbox.
4. The admin command calls the identity registry: `POST /registry/v1/team-ais` with the new `kms_key_arn`.
5. The registry asynchronously calls KMS `GetPublicKey`, decodes the SPKI, extracts the 32-byte raw Ed25519 pubkey, hex-encodes lowercase, stores in `team_ai_pubkeys` with `role='active'`, and updates `team_ais.state` to `'active'`.
6. The registry generates and stores a certificate vouching for `(team_ai_id, pubkey)` signed by the org identity issuer. This certificate is returned to inboxes that look up the team-AI.

## Signing an envelope (inside an inbox)

```
1. Build envelope (everything except `signature`).
2. Compute canonical encoding via create_canonical_payload(envelope).
3. SHA-512 the canonical bytes (KMS Ed25519ph requirement).
4. KMS.Sign(key_arn, digest) → signature bytes.
5. Base64-encode signature, attach to envelope.
6. POST envelope to recipient inbox.
```

The signing path is in the hot loop. KMS adds latency (typically 10–50 ms per sign call) and cost. Two mitigations:

- **Batch envelopes** through a per-inbox signer queue if rate exceeds 100/s. Most senders won't hit this.
- **Cache the KMS client** with persistent connection. Don't open a new connection per sign.

Do **not** cache or pre-compute signatures. Each envelope's signature is over its full canonical bytes including unique nonce and timestamp; pre-computation is impossible.

## Verifying an envelope (inside an inbox)

Verification is local — no KMS call needed. The pubkey is fetched once per cache window from the identity registry, then verification is pure CPU.

```
1. Look up sender pubkey from local trust-registry cache.
2. If not in cache, fetch from identity registry.
3. Verify the certificate that vouches for the sender pubkey (chain to org identity issuer).
4. Recompute canonical encoding from envelope minus signature.
5. SHA-512 → digest.
6. ed25519_verify(pubkey, digest, signature). Constant-time.
```

Verification cost: ~50 µs per envelope on a modern core.

## Rotation

Rotation is the routine path. Schedule: annual minimum, more often for high-classification team-AIs.

**Rotation flow:**

1. Operator (or scheduled job) calls `POST /registry/v1/team-ais/{id}/rotate` with `new_kms_key_arn` (a new KMS key created the same way as initial onboarding) and `overlap_seconds` (default 86400 = 24 hours).
2. The registry adds the new pubkey to `team_ai_pubkeys` with `role='rotating'` and computes `deactivates_at = now + overlap_seconds` for the *old* key.
3. The team-AI's inbox is reconfigured (via GitOps or env var) to use the new `kms_key_arn` for signing. From this point, new envelopes are signed with the new key.
4. Other inboxes pulling from the registry see *both* keys in `active_pubkeys` and accept signatures from either.
5. After `overlap_seconds`, the old `team_ai_pubkeys` row is deleted; cache TTLs cause it to drop out of all trust registries within ≤ 5 minutes.
6. Operator decommissions the old KMS key (`ScheduleKeyDeletion` with 7-day window).

**Rotation never breaks in-flight traffic.** That is the property the overlap window guarantees.

## Revocation

Revocation is the emergency path. Triggered when a key is suspected compromised, a team-AI is decommissioned, or compliance demands removal.

**Revocation flow:**

1. Operator calls `POST /registry/v1/team-ais/{id}/revoke` with reason and ticket.
2. The registry sets `team_ais.state = 'revoked'` and removes all rows from `team_ai_pubkeys` for that team-AI.
3. The registry pushes an immediate cache-bust event to all inboxes via the cache-bust pub/sub channel (see below).
4. Inboxes evict the cached entry and refuse new envelopes with the revoked pubkey within ≤ 60 seconds.
5. The KMS key is disabled (not deleted — preserves audit trail).

**SLO:** Revocation must propagate to all inboxes within 60 seconds. Measure this in CI by simulating revocation and timing inbox refusal.

**In-flight envelopes:** Envelopes that have already passed pipeline step 5 (sender known) at the moment of revocation will complete. This is acceptable — the alternative is a transactional cross-inbox lock that is not worth its cost.

## Cache-bust mechanism

Inboxes cache the identity registry data for 5 minutes by default. The cache is refreshed on:

- TTL expiry (lazy).
- Pub/sub message on `epp.registry.invalidate.{team_ai_id}` (eager, used for revocations).
- Failed signature verification with a cache-aged pubkey (defensive — refresh and retry once).

The pub/sub channel is best-effort. The TTL is the safety net.

## Key compromise response

If a team-AI's private key is suspected compromised:

1. **Within 5 minutes:** Operator revokes the team-AI per the revocation flow above.
2. **Within 1 hour:** Audit-log query: every envelope signed by the compromised key in the last 30 days is enumerated. Receipts of those envelopes are reviewed for anomalies.
3. **Within 24 hours:** Provision a new KMS key, register a new pubkey for the team-AI under a *new* `team_ai_id` (do not reuse the compromised ID — it's tainted in the audit history).
4. **Within 1 week:** Re-establish all pairings against the new team-AI ID. Each recipient team confirms the new identity.

A compromised key is never re-trusted.

## Operator key management

Operators authenticate to platform APIs via the org SSO + OIDC. Operator credentials are not envelope keys.

For high-impact actions (revoke, register, rotate), require step-up auth (MFA challenge within the last 5 minutes). Enforce in the admin API.

## What this doc does NOT cover

- The specific KMS provider's SDK. Implement against whichever KMS the platform decision selected in [01](01-build-plan.md).
- Customer-facing key management. Customers (principals) do not have keys in this model; they're identified through the org's existing identity system and carried via `delegation` (see [00](00-glossary.md)).
- Hardware tokens for operators. That's an org SSO concern, not an EPP concern.
