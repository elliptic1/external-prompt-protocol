# 03 — API Contracts

Every HTTP API exposed by the platform. Use these as build-targets. All APIs return `application/json`. All errors follow the shape:

```json
{ "error": { "code": "string", "message": "string", "details": {} } }
```

Authentication: every operator-facing endpoint requires an OIDC bearer token from the org SSO. Every inbox-to-platform endpoint requires service-mesh mTLS *and* a signed request header (see [05](05-key-management.md)).

---

## Inbox API (data plane)

The protocol-level API. One inbox per team-AI. **Defined by the EPP spec — do not extend.**

### `POST /epp/v1/submit`

Submit a signed envelope.

**Request body:** an `Envelope` (see `epp/models.py`).

**Response:**
- `200 OK` with a `SuccessReceipt` if the envelope was verified, accepted, and executed.
- `200 OK` with an `ErrorReceipt` if the envelope failed verification. (Yes, 200 — the protocol-level outcome is in the receipt body, not the HTTP code. Reserved 4xx/5xx are for transport-level failures only.)
- `400` for malformed JSON or invalid envelope structure.
- `413` for oversized request body (default limit: 64 KB).
- `503` when the inbox is shedding load.

### `GET /epp/v1/healthz`

Liveness. Returns `200 OK` with `{ "status": "ok" }` if the process is up.

### `GET /epp/v1/readyz`

Readiness. Returns `200 OK` only if all of: KMS reachable, nonce registry reachable, rate limiter reachable, trust registry cache populated.

### `GET /epp/v1/info`

Returns the inbox's public identity:

```json
{
  "team_ai_id": "concierge-orlando",
  "pubkey": "abcd...64hex",
  "supported_scopes": ["concierge.lookup", "concierge.handoff"],
  "protocol_versions": ["1"]
}
```

---

## Identity Registry API (control plane)

The central registry. All endpoints under `/registry/v1/`.

### `POST /registry/v1/team-ais`

Register a new team-AI. Operator action.

**Request:**
```json
{
  "team_ai_id": "string, kebab-case, globally unique",
  "team": "string, owning product team identifier",
  "owner_email": "string",
  "on_call_pager": "string, opaque to the registry",
  "supported_scopes": ["string"],
  "data_classification": "public | internal | confidential | restricted",
  "kms_key_arn": "string, opaque KMS reference"
}
```

**Response 201:**
```json
{
  "team_ai_id": "concierge-orlando",
  "state": "provisioning",
  "pubkey_pending": true,
  "created_at": "2026-04-27T15:00:00Z"
}
```

The registry asynchronously fetches the public key from KMS via the `kms_key_arn` and updates state to `active`.

### `GET /registry/v1/team-ais/{team_ai_id}`

Look up a team-AI. Read by operators, by the discovery portal, and by other team-AIs' inboxes (cached).

**Response:**
```json
{
  "team_ai_id": "concierge-orlando",
  "team": "in-venue-experience",
  "owner_email": "...",
  "on_call_pager": "...",
  "supported_scopes": ["concierge.lookup"],
  "data_classification": "internal",
  "active_pubkeys": ["abcd...64hex"],
  "rotating_pubkey": null,
  "state": "active",
  "created_at": "...",
  "updated_at": "..."
}
```

`active_pubkeys` is a list to support rotation overlap (see [05](05-key-management.md)).

### `GET /registry/v1/team-ais?team={team}&state={state}&scope={scope}`

List with filters. Pagination via `?cursor=` and `?limit=` (max 100).

### `POST /registry/v1/team-ais/{team_ai_id}/rotate`

Begin a key rotation. Operator action.

**Request:**
```json
{ "new_kms_key_arn": "string", "overlap_seconds": 86400 }
```

**Response 202:**
```json
{
  "team_ai_id": "concierge-orlando",
  "rotating_pubkey": "fedc...64hex",
  "rotation_completes_at": "2026-04-28T15:00:00Z"
}
```

During the overlap window both keys are in `active_pubkeys`. After completion, the old key is removed.

### `POST /registry/v1/team-ais/{team_ai_id}/revoke`

Immediately revoke a team-AI. Operator action. Requires reason.

**Request:**
```json
{ "reason": "string", "ticket": "string" }
```

**Response 200:**
```json
{ "team_ai_id": "...", "state": "revoked", "revoked_at": "..." }
```

Inboxes pick up revocation within 60 seconds (cache TTL).

### `POST /registry/v1/team-ais/{team_ai_id}/retire`

Soft delete. The team-AI is no longer accepted as sender or recipient. Audit-trail preserved.

### `GET /registry/v1/audit?actor=&team_ai_id=&from=&to=`

Query the audit log. Operator-only. Returns paginated list of audit events.

---

## Trust Registry API (per-inbox control plane)

Each inbox exposes a small admin API for its own trust policy. All endpoints under `/admin/v1/`. **Authorization: only members of the owning product team.**

### `GET /admin/v1/policy`

Return the current trust policy.

```json
{
  "default_action": "deny",
  "senders": [
    {
      "sender_pubkey": "abcd...64hex",
      "sender_team_ai_id": "concierge-orlando",
      "scopes": ["dining.rsvp", "dining.lookup"],
      "rate_limit": { "burst": 10, "sustained_per_second": 2 },
      "mode": "live",
      "added_at": "...",
      "added_by": "operator-email",
      "expires_at": null
    }
  ]
}
```

### `PUT /admin/v1/policy/senders/{sender_pubkey}`

Add or replace a sender's policy.

**Request:** the same shape as one element of `senders[]` above.

### `DELETE /admin/v1/policy/senders/{sender_pubkey}`

Remove a sender's policy. Equivalent to revocation from the recipient's perspective.

### `POST /admin/v1/policy/senders/{sender_pubkey}/promote`

Move a sender from `log-only` to `live` mode. Requires confirmation that the log-only window has elapsed.

---

## Receipt Warehouse API (query plane)

All endpoints under `/receipts/v1/`. **Authorization:**
- Operators see all receipts.
- A team-AI's owners see all receipts where their team-AI is sender or recipient.
- Other access is denied.

### `GET /receipts/v1/{envelope_id}`

Fetch the receipt for one envelope.

**Response:**
```json
{
  "envelope_id": "uuid",
  "sender": "abcd...64hex",
  "recipient": "fedc...64hex",
  "scope": "dining.rsvp",
  "outcome": "success | error",
  "error_code": null,
  "received_at": "...",
  "completed_at": "...",
  "executor_result_ref": "string, opaque pointer into team's storage",
  "receipt_signature": "base64",
  "conversation_id": "uuid | null"
}
```

### `GET /receipts/v1/?sender=&recipient=&scope=&conversation_id=&from=&to=&outcome=`

Query receipts. Pagination. Default page size 50, max 500.

### `GET /receipts/v1/conversations/{conversation_id}`

Return all receipts threaded by `conversation_id`, ordered by `received_at`.

### `GET /receipts/v1/stats?team_ai_id=&from=&to=`

Aggregate stats for dashboards: counts by outcome, p50/p95/p99 latency, top senders, top scopes.

---

## Discovery Portal API

All endpoints under `/discovery/v1/`. Read-mostly; writes are pairing requests and approvals.

### `GET /discovery/v1/team-ais`

List all team-AIs visible to the requesting operator.

### `GET /discovery/v1/team-ais/{team_ai_id}`

Detail page data: identity-registry data + recent stats from receipt warehouse + current pairings (from trust registry).

### `POST /discovery/v1/pairing-requests`

A sender team requests pairing with a recipient team.

**Request:**
```json
{
  "sender_team_ai_id": "concierge-orlando",
  "recipient_team_ai_id": "dining-orlando",
  "requested_scopes": ["dining.rsvp"],
  "justification": "string",
  "requested_rate_limit": { "burst": 10, "sustained_per_second": 2 }
}
```

**Response 201:** `{ "pairing_request_id": "uuid", "state": "pending" }`

Notifies the recipient team's on-call.

### `POST /discovery/v1/pairing-requests/{id}/approve`

Recipient team approves. Result is a `PUT` to the recipient's trust registry, automatically.

### `POST /discovery/v1/pairing-requests/{id}/deny`

Recipient team denies. Requires reason.

---

## Error code catalog

These appear in the `code` field of error responses across all platform APIs. Match the protocol error codes where applicable.

| Code | Where | Meaning |
|---|---|---|
| `invalid_envelope` | Inbox | Envelope structurally invalid |
| `wrong_recipient` | Inbox | Recipient pubkey mismatch |
| `stale_or_future` | Inbox | Timestamp outside skew window |
| `expired` | Inbox | `expires_at` in the past |
| `untrusted_sender` | Inbox | Sender not in trust registry |
| `bad_signature` | Inbox | Signature failed verification |
| `replay` | Inbox | Nonce already seen |
| `scope_denied` | Inbox | Scope not allowed for this sender |
| `rate_limited` | Inbox | Token bucket exhausted |
| `executor_failure` | Inbox | Executor raised or timed out |
| `not_found` | Registry, receipts, discovery | Object doesn't exist |
| `forbidden` | All | Caller lacks permission |
| `unauthenticated` | All | Missing or invalid OIDC token |
| `conflict` | Registry | Duplicate `team_ai_id` or pairing |
| `invalid_argument` | All | Validation failed on request body |
| `precondition_failed` | Registry | Operation not valid in current state |
| `unavailable` | All | Backing service down; retry with backoff |

## Idempotency

Every write endpoint accepts an optional `Idempotency-Key` header (UUIDv4). The server stores the key and the response for 24 hours; a retry with the same key returns the cached response.

The inbox `POST /epp/v1/submit` is implicitly idempotent on `envelope_id` — replays return the original receipt.
