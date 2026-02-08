# EPP v1.1 Implementation Plan

Based on feature requests from Moltbook agent community (2026-02-08).

## Overview

EPP v1.0 established the foundation. v1.1 adds features agents are actually asking for:
- Integrity verification (content hashing)
- Granular capabilities (beyond scope)
- Provenance chains (multi-party attestation)
- Payment integration (x402 pattern)

All changes are **backward compatible** — new fields are optional.

---

## Phase 1: Quick Wins (1-2 days)

### 1.1 Content Hashing (`integrity`)

**Problem:** No way to verify payload hasn't been modified in transit or storage.

**Solution:** Add optional `integrity` field with content hash.

```json
{
  "integrity": {
    "alg": "sha256",
    "hash": "a1b2c3d4e5f6..."
  }
}
```

**Spec changes:**
- Add `integrity` to envelope structure (optional)
- Hash computed over `payload_json` (same format as signing)
- Supported algorithms: `sha256`, `sha384`, `sha512`
- Verification: compute hash, compare to declared

**Implementation:**
- `epp/crypto/integrity.py` — hash functions
- Update `sign_envelope()` to optionally include integrity
- Update `verify_envelope()` to check integrity if present
- CLI: `eppctl envelope create --hash`

**Files to change:**
- `docs/spec.md` — add field definition
- `epp/envelope.py` — add field, validation
- `epp/crypto/integrity.py` — new file
- `cli/envelope.py` — add --hash flag
- `tests/test_integrity.py` — new tests

---

### 1.2 Capability Declarations (`capabilities`)

**Problem:** `scope` is too coarse. Agents want to know exactly what a sender needs.

**Solution:** Add optional `capabilities` field with granular permission requests.

```json
{
  "capabilities": {
    "filesystem": {
      "read": ["~/.config/myapp/*"],
      "write": []
    },
    "network": {
      "domains": ["api.example.com", "*.trusted.org"],
      "protocols": ["https"]
    },
    "actions": ["send_notification", "query_calendar"],
    "data_access": ["contacts:read", "calendar:read"]
  }
}
```

**Spec changes:**
- Add `capabilities` to envelope structure (optional)
- Capabilities are **advisory** — recipient decides whether to honor
- Trust registry can require/restrict capabilities per sender
- Standard capability categories: `filesystem`, `network`, `actions`, `data_access`

**Implementation:**
- `epp/capabilities.py` — capability schema, validation
- Update trust registry to support capability policies
- CLI: `eppctl trust add --require-capabilities`

**Files to change:**
- `docs/spec.md` — add capabilities section
- `epp/envelope.py` — add field
- `epp/capabilities.py` — new file
- `epp/trust.py` — capability policy support
- `tests/test_capabilities.py` — new tests

---

## Phase 2: Provenance & Attestation (3-5 days)

### 2.1 Provenance Chain (`provenance`)

**Problem:** `delegation` only handles one level. Agents want full chain: author → auditor → voucher.

**Solution:** Add optional `provenance` array with role-based attestations.

```json
{
  "provenance": [
    {
      "role": "author",
      "identity": "<pubkey-hex>",
      "timestamp": "2026-02-08T00:00:00Z",
      "signature": "<base64-sig>",
      "statement": "I authored this content"
    },
    {
      "role": "auditor",
      "identity": "<pubkey-hex>",
      "timestamp": "2026-02-08T01:00:00Z",
      "signature": "<base64-sig>",
      "statement": "I reviewed and found no issues"
    },
    {
      "role": "voucher",
      "identity": "<pubkey-hex>",
      "timestamp": "2026-02-08T02:00:00Z",
      "signature": "<base64-sig>",
      "statement": "I vouch for this skill"
    }
  ]
}
```

**Spec changes:**
- Add `provenance` array to envelope (optional)
- Each entry is independently signed
- Signature covers: `role||identity||timestamp||statement||parent_hash`
- `parent_hash` = hash of previous provenance entry (chain integrity)
- Standard roles: `author`, `auditor`, `reviewer`, `voucher`, `forwarder`

**Implementation:**
- `epp/provenance.py` — provenance chain handling
- Functions: `add_attestation()`, `verify_chain()`, `get_chain_depth()`
- Trust registry can require minimum chain depth or specific roles
- CLI: `eppctl provenance add --role auditor --key mykey.priv`

**Files to change:**
- `docs/spec.md` — add provenance section
- `epp/provenance.py` — new file
- `epp/envelope.py` — add field
- `epp/trust.py` — provenance requirements
- `cli/provenance.py` — new CLI commands
- `tests/test_provenance.py` — new tests

---

### 2.2 Multi-Party Attestation (`attestations`)

**Problem:** Single signature isn't enough for high-trust scenarios.

**Solution:** Add optional `attestations` for multi-sig style verification.

```json
{
  "attestations": {
    "threshold": 2,
    "required_roles": ["auditor"],
    "entries": [
      {
        "identity": "<pubkey-hex>",
        "role": "auditor",
        "timestamp": "2026-02-08T01:00:00Z",
        "signature": "<base64-sig>"
      },
      {
        "identity": "<pubkey-hex>",
        "role": "auditor", 
        "timestamp": "2026-02-08T01:30:00Z",
        "signature": "<base64-sig>"
      }
    ]
  }
}
```

**Spec changes:**
- `threshold`: minimum attestations required
- `required_roles`: roles that must be represented
- Each attestation signs: `envelope_id||timestamp||role`
- Trust registry can set minimum thresholds per scope

**Implementation:**
- `epp/attestations.py` — multi-party verification
- Functions: `add_attestation()`, `verify_threshold()`, `meets_requirements()`
- CLI: `eppctl attest --envelope <file> --key mykey.priv --role auditor`

---

## Phase 3: Payment Integration (3-5 days)

### 3.1 Payment Instructions (`payment`)

**Problem:** No standard way to request payment for prompt processing.

**Solution:** Add optional `payment` field following x402 pattern.

```json
{
  "payment": {
    "required": true,
    "amount": "0.01",
    "currency": "USDC",
    "recipient": "0x1234...abcd",
    "chain": "base",
    "memo": "API call: weather-query",
    "expires_at": "2026-02-08T00:15:00Z"
  }
}
```

**For responses with proof of payment:**

```json
{
  "payment_proof": {
    "tx_hash": "0xabcd...",
    "chain": "base",
    "amount": "0.01",
    "currency": "USDC",
    "payer": "0x5678...efgh",
    "block": 12345678
  }
}
```

**Spec changes:**
- `payment` on request envelopes (optional)
- `payment_proof` on response envelopes (optional)
- Supported chains: ethereum, base, solana, etc.
- Currencies: USDC, ETH, SOL, etc.
- Integration point — EPP doesn't process payments, just carries instructions

**Implementation:**
- `epp/payment.py` — payment schema, validation
- Inbox can return HTTP 402 with payment instructions
- CLI: `eppctl envelope create --payment-required --amount 0.01 --currency USDC`

---

### 3.2 Stake Reference (`stake`)

**Problem:** Agents want reputation staking for high-trust attestations.

**Solution:** Add optional `stake` field referencing on-chain stakes.

```json
{
  "stake": {
    "contract": "0xabcd...1234",
    "chain": "base",
    "amount": "100",
    "currency": "USDC",
    "staker": "<pubkey-hex>",
    "stake_id": "12345",
    "slash_conditions": "malicious_content"
  }
}
```

**Spec changes:**
- Stakes are referenced, not verified by EPP
- Slash conditions are advisory
- Verification requires on-chain lookup (out of scope for EPP core)

---

## Phase 4: Identity Extensions (2-3 days)

### 4.1 Chain Identity (`chain_identity`)

**Problem:** Ed25519 keys don't link to on-chain reputation.

**Solution:** Add optional `chain_identity` for linking to ERC-8004 or similar.

```json
{
  "chain_identity": {
    "standard": "ERC-8004",
    "chain": "base",
    "contract": "0x1234...abcd",
    "token_id": "42",
    "verification_method": "owner_of"
  }
}
```

**Spec changes:**
- Optional link to on-chain identity
- Verification: check that Ed25519 pubkey controls the token
- Standards: ERC-8004, ENS, Lens, etc.

---

### 4.2 Key Revocation (`revocation`)

**Problem:** No mechanism to revoke compromised keys.

**Solution:** Support revocation registry checks.

```json
{
  "revocation_check": {
    "registry": "https://revoke.epp.dev/v1/check",
    "required": true
  }
}
```

**Trust registry addition:**
```json
{
  "revocation": {
    "check_url": "https://revoke.epp.dev/v1/check",
    "on_failure": "reject"
  }
}
```

---

## Implementation Order

| Phase | Feature | Effort | Impact | Priority |
|-------|---------|--------|--------|----------|
| 1.1 | Content hashing | 1 day | High | P0 |
| 1.2 | Capabilities | 2 days | High | P0 |
| 2.1 | Provenance chains | 3 days | High | P1 |
| 2.2 | Multi-attestation | 2 days | Medium | P1 |
| 3.1 | Payment instructions | 2 days | High | P1 |
| 3.2 | Stake reference | 1 day | Medium | P2 |
| 4.1 | Chain identity | 2 days | Medium | P2 |
| 4.2 | Key revocation | 2 days | Medium | P2 |

**Total: ~15 days of work**

---

## Migration

All new fields are **optional**. Existing v1.0 envelopes remain valid.

Version stays at "1" — these are additive changes. Bump to "1.1" in docs only for clarity.

---

## Moltbook Announcement

Once Phase 1 is shipped, post update on Moltbook:

> **EPP v1.1: Content hashing + capability declarations**
> 
> Based on your feedback, we shipped:
> - `integrity` field for payload hashing
> - `capabilities` for granular permission requests
> 
> Coming soon: provenance chains, multi-attestation, x402 payments.
> 
> https://github.com/elliptic1/external-prompt-protocol

---

*Plan created 2026-02-08 based on Moltbook community feedback*
