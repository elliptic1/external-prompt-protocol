# 07 — Observability

What every component emits, how it's named, and what dashboards and alerts are built on top.

## Three pillars, one trace context

The platform emits **metrics**, **traces**, and **logs**. All three carry the same correlation IDs:

| ID | Where it originates | Travels in |
|---|---|---|
| `request_id` | Inbox HTTP layer | HTTP header `X-Request-Id`, every log line, every metric label that supports it, every span |
| `trace_id` | OpenTelemetry SDK | W3C `traceparent` header, propagated through executor calls and follow-up envelopes |
| `envelope_id` | Sender, in the envelope | Span attribute, log field, metric label |
| `conversation_id` | Sender, optional | Span attribute, log field |

Trace propagation across team-AI boundaries: when team A's executor sends a follow-up envelope to team B, the SDK sets the `traceparent` HTTP header on the submit call. B's inbox creates a child span. The full A → B → C chain is one trace in your tracing backend.

## Metrics

All metrics use OpenTelemetry naming conventions. Prefix: `epp_`.

### Inbox-side metrics

| Metric | Type | Labels | Purpose |
|---|---|---|---|
| `epp_envelopes_received_total` | counter | `recipient_team_ai`, `sender_team_ai`, `scope` | Total submitted envelopes |
| `epp_envelopes_pipeline_failures_total` | counter | `recipient_team_ai`, `sender_team_ai`, `scope`, `step`, `error_code` | Failures per pipeline step |
| `epp_envelopes_executed_total` | counter | `recipient_team_ai`, `sender_team_ai`, `scope`, `executor_kind`, `outcome` | Executor outcomes |
| `epp_envelope_duration_ms` | histogram | `recipient_team_ai`, `scope`, `outcome` | End-to-end inbox latency |
| `epp_pipeline_step_duration_ms` | histogram | `recipient_team_ai`, `step` | Per-step latency |
| `epp_executor_duration_ms` | histogram | `recipient_team_ai`, `executor_kind`, `outcome` | Executor wallclock |
| `epp_signature_verify_duration_us` | histogram | (none) | Crypto step microbench |
| `epp_kms_sign_duration_ms` | histogram | `team_ai_id`, `outcome` | KMS sign latency on sender side |
| `epp_kms_sign_failures_total` | counter | `team_ai_id`, `kms_error` | KMS sign errors |
| `epp_trust_registry_cache_hits_total` | counter | `recipient_team_ai` | Cache effectiveness |
| `epp_trust_registry_cache_misses_total` | counter | `recipient_team_ai` | |
| `epp_trust_registry_lookup_duration_ms` | histogram | `outcome` | Registry roundtrip on cache miss |
| `epp_nonce_registry_duration_ms` | histogram | `outcome` | Redis nonce check latency |
| `epp_rate_limiter_duration_ms` | histogram | `outcome` | Redis token bucket latency |
| `epp_rate_limit_rejections_total` | counter | `recipient_team_ai`, `sender_team_ai`, `scope` | 429s, by sender |
| `epp_inbox_load_shed_total` | counter | `recipient_team_ai` | 503s when overloaded |
| `epp_receipt_write_failures_total` | counter | `recipient_team_ai` | Critical — page on this |

### Platform-side metrics

| Metric | Type | Labels | Purpose |
|---|---|---|---|
| `epp_registry_requests_total` | counter | `endpoint`, `outcome` | Identity registry traffic |
| `epp_registry_request_duration_ms` | histogram | `endpoint`, `outcome` | |
| `epp_registry_active_team_ais` | gauge | `state` | Total team-AIs by lifecycle state |
| `epp_audit_log_writes_total` | counter | `action` | Audit log volume |
| `epp_audit_log_buffer_size` | gauge | (none) | If non-zero, async writes are backing up |
| `epp_receipt_warehouse_writes_total` | counter | `outcome` | Receipt sink throughput |
| `epp_receipt_warehouse_index_lag_seconds` | gauge | (none) | Time from blob write to query-table availability |
| `epp_revocation_propagation_seconds` | histogram | (none) | Time from revocation API call to all-inboxes-evicted (synthetic test) |

### Histogram buckets (recommended)

```
duration_ms:    [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000]
duration_us:    [10, 25, 50, 100, 250, 500, 1000, 2500]
```

## Traces

Every envelope produces one root span at the inbox plus child spans for each pipeline step and the executor.

**Span names:**

```
epp.inbox.submit                         (root, attributes from envelope)
├── epp.pipeline.parse
├── epp.pipeline.recipient_match
├── epp.pipeline.timestamp_window
├── epp.pipeline.expiry
├── epp.pipeline.sender_known
│   └── epp.registry.lookup              (only on cache miss)
├── epp.pipeline.signature_verify
├── epp.pipeline.nonce_check
│   └── epp.redis.nonce_setnx
├── epp.pipeline.scope_policy
├── epp.pipeline.rate_limit
│   └── epp.redis.rate_bucket
└── epp.executor.<kind>
    └── (team-defined sub-spans)
```

**Span attributes (set on root):**
- `epp.envelope_id`
- `epp.sender_pubkey` (full hex)
- `epp.sender_team_ai_id`
- `epp.recipient_pubkey`
- `epp.recipient_team_ai_id`
- `epp.scope`
- `epp.conversation_id` (if present)
- `epp.protocol_version`

**Sender-side trace:**

```
epp.sender.send                          (started by sender SDK)
├── epp.kms.sign
└── epp.transport.http_post
    └── (becomes the receiver's epp.inbox.submit span as child)
```

Sampling: 100% of error-outcome traces, 1% of success-outcome traces in production. Sender SDK is responsible for sampling decision; receiver inherits.

## Logs

Structured JSON logs only. No printf-style logs.

**Required fields on every log line from inbox or platform service:**

```json
{
  "timestamp": "ISO-8601",
  "level": "DEBUG | INFO | WARN | ERROR | FATAL",
  "service": "epp-inbox | epp-registry | epp-receipts | ...",
  "service_version": "git sha or semver",
  "team_ai_id": "string or null",
  "request_id": "string",
  "trace_id": "string or null",
  "envelope_id": "string or null",
  "msg": "human-readable",
  "...": "additional structured fields"
}
```

**Log levels:**

| Level | Use |
|---|---|
| DEBUG | Disabled in prod. Step-by-step pipeline trace. |
| INFO | One line per envelope on success: `envelope_processed`. One line per admin write. Pubkey rotations. Cache invalidations. |
| WARN | Pipeline failures (each with `error_code`). Trust-registry cache misses that failed. KMS retries. |
| ERROR | Receipt write failures. Registry write failures. Unhandled executor exceptions. |
| FATAL | Process is exiting (e.g. KMS unreachable on startup). |

**Forbidden in logs at any level:**

- The full `payload.prompt` text. Log a hash if needed for correlation.
- `payload.context` contents. Log only the keys, not the values.
- Full envelope JSON. Log the `envelope_id` instead.
- KMS key material (which never reaches userland anyway, but enforce).
- Operator session tokens.

The reference inbox enforces these via a logging filter; product teams must apply the same filter to their executors.

## Dashboards

Build these in your observability stack (Grafana, Datadog, etc.). Each dashboard is keyed to one audience.

### Dashboard A — Mesh-wide health (platform team)

- Envelope throughput (rate over time, stacked by `recipient_team_ai`)
- Mesh-wide success rate (last 5m, last 1h, last 24h)
- p50/p95/p99 envelope duration (mesh-wide and top-10 recipients)
- Pipeline step failure rate, broken down by step
- Receipt write success rate (alert on dip)
- Trust-registry cache hit rate
- Registry API latency
- Active team-AIs by state

### Dashboard B — Per-team health (one per team-AI)

- Envelopes received (rate, by sender)
- Envelopes sent (rate, by recipient)
- Success vs error breakdown
- Top scopes by volume
- Latency p50/p95/p99 (received side)
- Rate-limit rejections (sender = me, hitting other inboxes' limits)
- Pairings: list of current senders + their mode (log-only / live)

### Dashboard C — Security (security team)

- `bad_signature` rate over time (any spike = investigation)
- `replay` rate over time
- `untrusted_sender` rate (high = misconfiguration; sustained = probing)
- `scope_denied` rate by sender (sender testing scopes is suspicious)
- Revocation propagation time (synthetic test result)
- Audit log write rate + buffer size
- Operator step-up MFA challenge rate

### Dashboard D — Capacity (platform team)

- Inbox CPU / memory per pod, top 20 pods
- Redis nonce-registry memory used vs configured cap
- Redis rate-limiter ops/sec
- KMS Sign call rate per team-AI vs quota
- Receipt warehouse write lag
- Registry DB connection pool utilization

## Alerts

Pages = wakes someone up. Tickets = handled in business hours.

### Pages (sev 1)

| Alert | Threshold | Why |
|---|---|---|
| Receipt write failure rate > 0.1% over 5 min | rate | Audit trail breaking; legal/compliance risk |
| Mesh success rate < 99% over 5 min | rate | Customer-facing AIs degraded |
| KMS Sign failure rate > 1% over 5 min | rate | Senders cannot send |
| Identity registry 5xx rate > 1% over 5 min | rate | Mesh control plane failing |
| Revocation propagation > 120s | synthetic | Security control broken |
| Audit log buffer growing for > 5 min | gauge | Loss of evidence imminent |

### Tickets (sev 2)

| Alert | Threshold | Why |
|---|---|---|
| `bad_signature` rate spike > 10× baseline | rate | Misconfigured sender or attack |
| `replay` rate spike > 10× baseline | rate | Bad retry logic somewhere |
| Trust-registry cache hit rate < 95% | rate | Cache config or registry slow |
| p95 envelope duration > 500ms for any recipient | histogram | Recipient SLO breach |
| Rate-limit rejection sustained from one sender | rate | Sender misbehaving or limits wrong |
| Receipt warehouse index lag > 60s | gauge | Query freshness degraded |

### Watch (no page, no ticket — visible on dashboard only)

- New `team_ai_id` registered (informational)
- New pairing approved (informational)
- Key rotation begun / completed (informational)

## SLO definitions

These are platform commitments. See [10](10-runbooks-and-slos.md) for the runbook side. Targets:

| SLO | Target | Measurement |
|---|---|---|
| Mesh success rate (excluding `executor_failure`) | 99.9% over 30 days | `epp_envelopes_executed_total{outcome="success"} / total` minus executor failures |
| Inbox p95 latency (excluding executor time) | < 50 ms over 30 days | `epp_envelope_duration_ms - epp_executor_duration_ms` |
| Identity registry availability | 99.95% over 30 days | `epp_registry_requests_total{outcome="success"} / total` |
| Receipt write success rate | 99.99% over 30 days | `epp_receipt_warehouse_writes_total{outcome="success"} / total` |
| Revocation propagation | < 60s p95 | `epp_revocation_propagation_seconds` |

Executor latency is the team's SLO, not the platform's. Track it but do not page the platform team on it.

## What to keep out of telemetry

- Anything that would let an outside observer reconstruct an envelope payload from logs. Hash, don't log.
- Per-principal (per-guest) identifiers. Use `delegation.on_behalf_of` *hash* if traceability is needed for audit, but do not put guest IDs in metric labels (cardinality explosion + privacy risk).
- Free-form `metadata` field contents from envelopes. Log only keys.

## Cardinality budget

OpenTelemetry metrics with high-cardinality labels become expensive fast. Caps:

| Label | Cap | Mitigation if exceeded |
|---|---|---|
| `team_ai_id` | ~500 | If exceeded, mesh has more team-AIs than expected — split metrics by `team` |
| `scope` | ~200 per recipient | Recipients with > 200 scopes have a design problem |
| `error_code` | ~20 | Defined set, won't grow |

Do not label metrics with `envelope_id`, `request_id`, `trace_id`, or `conversation_id`. Those belong in traces and logs, not metrics.
