# 10 — Runbooks and SLOs

Operational doc. What the platform commits to, and what platform on-call does when something breaks.

## Service-level commitments

Two audiences see SLOs: product teams (consumers of the mesh) and platform engineers (producers).

### Platform SLOs (what the platform commits to)

| SLO | Target (rolling 30d) | What it measures |
|---|---|---|
| Mesh control-plane availability | 99.95% | Identity registry + receipt warehouse API + discovery portal |
| Inbox image availability | 99.95% | Pulls succeed; image is signed; readiness probe passes within 30s of startup |
| Pipeline correctness | 100% | Verification pipeline does not return false-positives for `bad_signature`, `replay`, or `untrusted_sender` (no flaky pipeline behavior) |
| Inbox p95 latency (excluding executor) | < 50ms | `epp_envelope_duration_ms - epp_executor_duration_ms` |
| Receipt write success rate | 99.99% | `epp_receipt_warehouse_writes_total{outcome="success"} / total` |
| Revocation propagation | < 60s p95 | Synthetic probe |
| Key rotation overlap | exact window honored | No false signature failures during configured overlap |

### Per-team SLOs (what each product team commits to its callers)

The platform does **not** commit these. Each team declares its own in the discovery portal:

- Inbox availability (suggested floor: 99.5%).
- Executor p95 latency for each scope.
- Executor success rate (excluding upstream-caused errors).
- Hours of operation if not 24×7.

The platform does measure them and surface them on each team-AI's portal page. Senders see the actual numbers next to the team's commitment.

## Error budget policy

| Audience | Budget | Consequence of burning >50% in 30d |
|---|---|---|
| Platform team | 0.05% (= ~21 min/month) for control-plane SLO | Feature freeze on platform until budget recovers; root-cause review |
| Per-team | as declared by team | Surfaced on portal; no platform enforcement |

## Disaster recovery objectives

| Loss event | RTO | RPO |
|---|---|---|
| Single inbox pod | seconds | 0 |
| All inbox pods for one team-AI | < 5 min | 0 |
| Identity registry primary DB | < 15 min | < 1 min |
| Redis nonce cluster | < 30 min | up to envelope max-age window |
| Receipt warehouse blob store | < 1 hour | 0 (replicated) |
| Receipt warehouse index DB | < 2 hours | < 5 min (replayable from blob) |
| Whole region | < 4 hours | < 5 min |
| KMS region | KMS provider's RTO | provider's RPO |

DR drill cadence: quarterly. Run two drills per year against staging, one tabletop, one full-region failover simulation.

---

## Runbooks

Each runbook follows the same shape: **trigger → diagnose → remediate → postmortem trigger**.

### RB-01: Receipt write failure rate alert

**Trigger:** `epp_receipt_warehouse_writes_total{outcome="failure"} / total > 0.001` over 5 min.

**Why this pages:** Receipts are the audit trail. Loss is unrecoverable.

**Diagnose:**
1. Check receipt-warehouse-api dashboard. Is the API up?
2. Check object store status (S3/GCS) in cloud provider's console.
3. Check the receipt-sink worker logs for write errors.
4. Check object store IAM — has anyone changed the bucket policy?

**Remediate:**
1. If object store is the problem: the receipt-sink has a persistent buffer (default 1 GB). It will retry. If buffer is filling (`epp_audit_log_buffer_size` rising), scale up sink workers and engage cloud provider support.
2. If API is the problem: scale up replicas, restart unhealthy pods.
3. If IAM is the problem: revert the change. Audit who changed it (admin audit log).

**Postmortem:** Always. Receipt loss is sev-1 even if recovered.

---

### RB-02: Mesh success rate drop

**Trigger:** Mesh-wide success rate (excluding executor failures) < 99% over 5 min.

**Diagnose:**
1. Open Dashboard A. Which recipients are failing? Which step is failing?
2. If concentrated in one recipient: it's a per-team issue. Page that team's on-call. Stop here.
3. If distributed across recipients but concentrated in one pipeline step:
   - Step 5 (`untrusted_sender`) spike → identity registry may be stale, cache may be cold. Check registry availability.
   - Step 6 (`bad_signature`) spike → canonical encoding regression in a recent inbox release; potential mass key drift.
   - Step 7 (`replay`) spike → a sender is double-sending. Identify and notify their on-call.
   - Step 9 (`rate_limited`) spike → traffic surge or limits set wrong.
4. If it's distributed and not concentrated: infra problem. Check Redis cluster health, registry DB health.

**Remediate:**
- Per-team: hand off, this isn't a platform fix.
- Step 6 mass failure: roll back the inbox image to the last-known-good version. **Do not patch forward.**
- Step 5/7/9: address per cause above.

**Postmortem:** If sustained > 15 min, yes.

---

### RB-03: Suspected key compromise

**Trigger:** Security team reports compromise, OR `bad_signature` from a single sender exceeds 50% of their traffic for 5 min, OR an unusual signing pattern is flagged.

**Diagnose:**
1. Confirm the team-AI ID and the suspected compromise vector.
2. Pull the audit log: every Sign call from that key in the last 30 days.
3. Pull receipts: every envelope that key has signed.
4. Identify what scopes the key was authorized for and which executors handled its envelopes.

**Remediate (within 5 min of confirmation):**
1. `eppctl-admin team-ai revoke <id> --reason "key compromise" --ticket <SIRT-ticket>`.
2. Post an incident in the security incident channel.
3. Notify on-call for every team that has this team-AI as a trusted sender. Their inboxes will start refusing within 60s; they should know.
4. Disable the KMS key (do not delete; preserves audit).

**Remediate (within 24 hours):**
1. Provision a new KMS key.
2. Register a *new* team-AI ID (do not reuse the compromised ID — it is tainted).
3. Coordinate re-pairing with each affected recipient team. Each one explicitly accepts the new identity.
4. Audit each handled envelope from the compromised period for downstream impact.

**Postmortem:** Always. Required by security policy.

---

### RB-04: Identity registry primary DB failure

**Trigger:** Registry API 5xx rate > 1% over 2 min, OR DB primary alert from cloud provider.

**Diagnose:**
1. Check cloud provider DB console. Is the primary down?
2. Check standby lag.
3. Check inbox cache hit rate — if it's high, customer impact is muted while we recover.

**Remediate:**
1. Trigger DB failover to standby. If automatic failover hasn't happened, do it manually.
2. Inbox readers are read-replicas-aware; they continue serving once standby is promoted.
3. Operator writes (registration, rotation, revocation) are blocked during failover. Hold off on admin actions until primary is back or standby is promoted to primary.
4. Verify revocation propagation still works on synthetic probe before declaring all-clear.

**Postmortem:** If primary DB failure was unplanned, yes.

---

### RB-05: Redis nonce cluster degradation

**Trigger:** Redis nonce cluster CPU > 80% sustained, OR pipeline step 7 latency p95 > 100ms.

**Diagnose:**
1. Check Redis cluster dashboard: per-node CPU, memory, command rate.
2. Check key cardinality vs capacity model in [04](04-data-schemas.md).
3. Check for hot keys (one sender disproportionately active).

**Remediate:**
- If hot key: investigate the offending sender; possibly rate-limit them more aggressively.
- If general saturation: scale the Redis cluster (add nodes, resharding handled by cluster mode).
- If memory full and TTLs aren't purging fast enough: lower the inbox `max_envelope_age_s` (less time-window for replays = smaller working set).

**Postmortem:** If sustained > 30 min, yes.

---

### RB-06: KMS Sign quota approaching

**Trigger:** Per-team-AI KMS Sign rate > 80% of quota for 10 min.

**Diagnose:**
1. Identify the team-AI burning quota.
2. Talk to that team — is this expected traffic? If yes, request KMS quota increase (cloud provider ticket).
3. If no, the team has a runaway loop. Page their on-call.

**Remediate:**
- If legitimate: file the quota request, acknowledge alert.
- If runaway: team's responsibility to stop their sender; platform may help by enforcing inbox-side rate limits on the offending sender's recipients.

**Postmortem:** Only if customer-visible impact occurred.

---

### RB-07: Pairing approval flow broken

**Trigger:** Discovery portal pairing-request approvals failing.

**Diagnose:**
1. Check the portal logs. Is the GitOps PR creation failing?
2. Check the gitops-repo's webhook config. Is the portal authenticated?
3. Check trust-registry sync (ArgoCD application health).

**Remediate:**
- Restore the portal-to-gitops integration.
- For urgent pairings, use the admin CLI `eppctl-admin trust add` as a manual fallback. Backfill the gitops-repo file after.

**Postmortem:** Only if urgent pairing was blocked.

---

### RB-08: Operator step-up MFA loop

**Trigger:** Operator can't complete an admin action; MFA challenge looping.

**Diagnose:**
1. Check OIDC issuer health (org SSO).
2. Check that the operator's session is fresh (< 5 min since MFA).

**Remediate:**
- If SSO is degraded: notify SSO team, document.
- For genuinely urgent operator action during SSO outage: invoke break-glass procedure (see RB-09).

---

### RB-09: Break-glass procedure

**Trigger:** Genuine emergency where normal admin path is unavailable AND action cannot wait.

**Pre-conditions:**
- At least two platform engineers present.
- Incident declared in the security incident channel.
- One engineer initiates; the other witnesses.

**Procedure:**
1. Both engineers authenticate via the break-glass path (typically: hardware token + offline verification code).
2. Action is taken via direct admin CLI.
3. Action is recorded in the audit log with `actor_email = "break-glass:<both-emails>"`.
4. Within 1 hour, an incident report is filed describing what was done and why normal path was unavailable.

**This is for revocations and emergency rotations only.** Never for routine work.

---

## Capacity reviews

Cadence: monthly until phase 7, quarterly thereafter.

Each review covers:

- Current envelope rate per recipient.
- Projected rate based on team-AI growth.
- Redis nonce keyspace utilization vs cap.
- Receipt warehouse write rate vs storage growth budget.
- KMS Sign quota utilization per team-AI.
- Inbox pod utilization (CPU, memory) vs HPA limits.

Output: a doc identifying any service that will hit a wall in < 90 days at current growth, and a plan to raise the wall.

## On-call rotations

| Rotation | Hours | Coverage |
|---|---|---|
| Platform on-call (primary) | 24×7 | All platform sev-1 alerts |
| Platform on-call (secondary) | 24×7 | Backup; called if primary unreachable in 15 min |
| Security on-call | 24×7 (org-wide) | Anything in the security alert set |
| Per-team on-call | declared by each team | Their inbox + executor |

Handoffs: weekly, with a written checklist.

## Postmortem policy

- Every sev-1 (page) gets a postmortem within 5 business days.
- Postmortems are blameless and shared with the platform engineering org.
- Action items go to the platform team's backlog with owners and due dates.
- Recurring root causes (same root cause in 2+ postmortems within 6 months) trigger a deeper review.
