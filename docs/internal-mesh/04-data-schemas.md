# 04 — Data Schemas

Every persistent data shape in the platform. Postgres tables, Redis keyspace, queue topics, receipt JSON. All of it.

---

## Postgres — Identity Registry

### `team_ais`

```sql
CREATE TABLE team_ais (
    team_ai_id            TEXT PRIMARY KEY,                      -- kebab-case, globally unique
    team                  TEXT NOT NULL,                         -- owning product team
    owner_email           TEXT NOT NULL,
    on_call_pager         TEXT,
    supported_scopes      TEXT[] NOT NULL DEFAULT '{}',
    data_classification   TEXT NOT NULL CHECK (data_classification IN
                            ('public','internal','confidential','restricted')),
    kms_key_arn           TEXT NOT NULL,
    state                 TEXT NOT NULL CHECK (state IN
                            ('provisioning','active','rotating','suspended','revoked','retired')),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX team_ais_team_idx ON team_ais (team);
CREATE INDEX team_ais_state_idx ON team_ais (state);
CREATE INDEX team_ais_scopes_gin ON team_ais USING GIN (supported_scopes);
```

### `team_ai_pubkeys`

A team-AI may have one active pubkey, plus a second during rotation overlap.

```sql
CREATE TABLE team_ai_pubkeys (
    pubkey_hex      TEXT PRIMARY KEY,                            -- 64-char lowercase hex
    team_ai_id      TEXT NOT NULL REFERENCES team_ais(team_ai_id),
    role            TEXT NOT NULL CHECK (role IN ('active','rotating')),
    activated_at    TIMESTAMPTZ NOT NULL,
    deactivates_at  TIMESTAMPTZ,                                 -- non-null during rotation
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX team_ai_pubkeys_team_idx ON team_ai_pubkeys (team_ai_id);
```

### `audit_log`

```sql
CREATE TABLE audit_log (
    audit_id        BIGSERIAL PRIMARY KEY,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_email     TEXT NOT NULL,                               -- from OIDC token
    actor_token_jti TEXT NOT NULL,                               -- for non-repudiation
    action          TEXT NOT NULL,                               -- e.g. "team_ai.register"
    target_kind     TEXT NOT NULL,                               -- e.g. "team_ai"
    target_id       TEXT NOT NULL,
    request_body    JSONB NOT NULL,                              -- redacted of secrets
    response_status INT NOT NULL,
    request_id      TEXT NOT NULL,                               -- correlation
    ip_address      INET
);
CREATE INDEX audit_log_target_idx ON audit_log (target_kind, target_id, occurred_at DESC);
CREATE INDEX audit_log_actor_idx ON audit_log (actor_email, occurred_at DESC);
```

The audit log is also mirrored to immutable object storage on write (S3 with object-lock) for tamper-evidence.

---

## Postgres — Trust Registry (per-inbox)

Each inbox has its own logical schema. Multi-tenant on a shared cluster is fine; one schema per team-AI.

### `trust_policy_senders`

```sql
CREATE TABLE trust_policy_senders (
    sender_pubkey         TEXT PRIMARY KEY,                      -- 64-char lowercase hex
    sender_team_ai_id     TEXT NOT NULL,                         -- denormalized from registry
    scopes                TEXT[] NOT NULL,                       -- supported wildcard "dining.*"
    rate_burst            INT NOT NULL,                          -- token bucket capacity
    rate_sustained_per_s  REAL NOT NULL,                         -- refill rate
    mode                  TEXT NOT NULL CHECK (mode IN ('log-only','live','suspended')),
    added_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    added_by              TEXT NOT NULL,
    expires_at            TIMESTAMPTZ,                           -- optional auto-expiry
    notes                 TEXT
);
CREATE INDEX trust_policy_mode_idx ON trust_policy_senders (mode);
```

### `trust_policy_defaults`

One row per inbox.

```sql
CREATE TABLE trust_policy_defaults (
    singleton           BOOL PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    default_action      TEXT NOT NULL CHECK (default_action IN ('deny','log-only')),
    clock_skew_seconds  INT NOT NULL DEFAULT 60,
    max_payload_bytes   INT NOT NULL DEFAULT 65536,
    max_envelope_age_s  INT NOT NULL DEFAULT 600
);
```

`default_action = 'deny'` is required for production. `'log-only'` is for staging or initial onboarding only.

---

## Redis — Nonce Registry

One Redis cluster, shared across all inboxes. Keys are namespaced by recipient.

**Key shape:**
```
epp:nonce:{recipient_pubkey}:{sender_pubkey}:{nonce_b64}
```

**Value:** `1` (presence is the signal).

**TTL:** `envelope.expires_at - now`, capped at the inbox's `max_envelope_age_s`.

**Operations:**
- `SET key 1 NX EX <ttl>` — atomic "first use." Returns OK if new, nil if replay.
- That is the only op needed.

**Capacity model:**
```
keys_in_flight = Σ_recipients (peak_envelope_rate × max_envelope_age_s)
```
At 100 senders × 100 env/s × 600s per recipient × 50 recipients ≈ 300M keys. Each key is ~140 bytes including overhead. ≈ 42 GB. Use Redis Cluster with eviction disabled; let TTL handle expiry.

---

## Redis — Rate Limiter

Token bucket per `(recipient_pubkey, sender_pubkey, scope)`.

**Key shape:**
```
epp:rate:{recipient_pubkey}:{sender_pubkey}:{scope}
```

**Value:** Hash:
```
{ "tokens": float, "last_refill_unix_ms": int }
```

**Operation:** Lua script, atomic:

```lua
-- inputs: KEYS[1], ARGV[1]=now_ms, ARGV[2]=burst, ARGV[3]=refill_per_s, ARGV[4]=cost
local h = redis.call('HMGET', KEYS[1], 'tokens', 'last_refill_unix_ms')
local tokens = tonumber(h[1]) or tonumber(ARGV[2])
local last   = tonumber(h[2]) or tonumber(ARGV[1])
local elapsed_s = (tonumber(ARGV[1]) - last) / 1000.0
tokens = math.min(tonumber(ARGV[2]), tokens + elapsed_s * tonumber(ARGV[3]))
if tokens < tonumber(ARGV[4]) then
    return 0  -- rate limited
end
tokens = tokens - tonumber(ARGV[4])
redis.call('HMSET', KEYS[1], 'tokens', tokens, 'last_refill_unix_ms', ARGV[1])
redis.call('EXPIRE', KEYS[1], 86400)  -- idle keys age out
return 1
```

---

## Receipt Warehouse — JSON shape

Every receipt is stored as JSON in object storage *and* indexed in the warehouse. The JSON shape:

```json
{
  "receipt_version": "1",
  "receipt_id": "uuid",
  "envelope_id": "uuid",
  "sender": "abcd...64hex",
  "recipient": "fedc...64hex",
  "scope": "dining.rsvp",
  "conversation_id": "uuid | null",
  "received_at": "2026-04-27T15:00:00.123Z",
  "completed_at": "2026-04-27T15:00:00.456Z",
  "outcome": "success | error",
  "error_code": "string | null",
  "error_message": "string | null",
  "executor_kind": "logger | queue | direct-model | human-review | chain | custom",
  "executor_result_ref": "string, opaque pointer (e.g. s3://team-bucket/result/uuid)",
  "envelope_signature": "base64",
  "receipt_signature": "base64",
  "platform_metadata": {
    "inbox_pod": "string",
    "inbox_image_digest": "sha256:...",
    "trace_id": "string",
    "request_id": "string"
  }
}
```

**Object storage path:**
```
s3://receipts/{yyyy}/{mm}/{dd}/{recipient_pubkey[:8]}/{envelope_id}.json
```

Object lifecycle: hot tier (S3 standard) for 30 days, then transition to cold tier (Glacier or equivalent) until retention expires. Retention default: 7 years for receipts where `data_classification` was `confidential` or `restricted`; 2 years otherwise.

### `receipts` index table (in warehouse)

```sql
CREATE TABLE receipts (
    envelope_id          UUID PRIMARY KEY,
    sender_pubkey        TEXT NOT NULL,
    recipient_pubkey     TEXT NOT NULL,
    scope                TEXT NOT NULL,
    conversation_id      UUID,
    received_at          TIMESTAMPTZ NOT NULL,
    completed_at         TIMESTAMPTZ NOT NULL,
    duration_ms          INT GENERATED ALWAYS AS
                            (EXTRACT(EPOCH FROM (completed_at - received_at)) * 1000) STORED,
    outcome              TEXT NOT NULL,
    error_code           TEXT,
    executor_kind        TEXT NOT NULL,
    blob_uri             TEXT NOT NULL,                           -- pointer to object storage
    sender_team_ai_id    TEXT NOT NULL,                           -- denormalized for query
    recipient_team_ai_id TEXT NOT NULL                            -- denormalized for query
);
CREATE INDEX receipts_sender_time_idx ON receipts (sender_pubkey, received_at DESC);
CREATE INDEX receipts_recipient_time_idx ON receipts (recipient_pubkey, received_at DESC);
CREATE INDEX receipts_conversation_idx ON receipts (conversation_id) WHERE conversation_id IS NOT NULL;
CREATE INDEX receipts_scope_time_idx ON receipts (scope, received_at DESC);
PARTITION BY RANGE (received_at);  -- monthly partitions
```

---

## Queue topics (when inboxes use queue-backed executors)

The platform does not own these queues — each product team uses their own infra. But the **message shape** is standardized:

### Topic: `epp.envelope.{recipient_team_ai_id}`

Producer: the inbox after pipeline steps 1–9 succeed. Consumer: the team's executor worker pool.

**Message:**
```json
{
  "envelope": { /* full Envelope object */ },
  "trace_id": "string",
  "request_id": "string",
  "received_at": "ISO-8601",
  "deadline_at": "ISO-8601",
  "callback": {
    "kind": "http | queue",
    "uri": "string",
    "auth_ref": "string"
  }
}
```

### Topic: `epp.receipt.callback.{recipient_team_ai_id}`

Producer: the team's executor when work completes. Consumer: the inbox process, which finalizes the receipt.

**Message:**
```json
{
  "envelope_id": "uuid",
  "outcome": "success | error",
  "error_code": "string | null",
  "executor_result_ref": "string"
}
```

---

## Discovery Portal — entity definition

Each team-AI is one Backstage-style entity (or equivalent in another internal portal):

```yaml
apiVersion: epp.internal/v1alpha1
kind: TeamAI
metadata:
  name: concierge-orlando
  namespace: in-venue-experience
  annotations:
    epp.internal/pubkey: "abcd...64hex"
    epp.internal/registry-link: "https://registry.internal/team-ais/concierge-orlando"
spec:
  team: in-venue-experience
  owner: user:tech-manager-email
  on_call: pagerduty:in-venue-experience-oncall
  supported_scopes:
    - concierge.lookup
    - concierge.handoff
  data_classification: internal
  example_envelopes:
    - title: "Look up nearest available cast member"
      scope: concierge.lookup
      payload_example: |
        { "prompt": "Where is the nearest cast member trained for accessibility assistance?", ... }
  inbox:
    url: https://concierge-orlando.inbox.internal/epp/v1/submit
    healthcheck: https://concierge-orlando.inbox.internal/epp/v1/healthz
status:
  current_pairings: 7
  envelopes_24h: 12450
  p95_latency_ms: 180
  error_rate_24h: 0.003
```

`status.*` is computed by the portal from the receipt warehouse and is read-only.

---

## A note on PII

No envelope payload is stored anywhere by the platform. Receipts contain *metadata* about envelopes (who, when, scope, outcome) but not payload contents. If a team-AI needs to retain payload contents, it does so in its own storage and references them by `executor_result_ref`.

This separation is what makes the receipt warehouse safe to retain for years and to query broadly.
