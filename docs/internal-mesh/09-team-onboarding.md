# 09 — Team Onboarding Runbook

What a product team does to bring their team-AI onto the mesh. Written for the team — they should be able to follow this without platform-team handholding once the mesh is operational.

## Who this is for

You're a product team that:

- Owns one or more AI agents (let's call yours `your-team-ai`).
- Wants your team-AI to receive prompts from other teams' AIs, send prompts to other teams' AIs, or both.
- Is not building the mesh itself — that's the platform team. You're a tenant.

## What you'll get

- A registered identity for your team-AI (a pubkey known across the mesh).
- An EPP inbox running in your namespace.
- The ability to receive signed envelopes from any team that pairs with you.
- The ability to send signed envelopes to any team-AI that has accepted you as a sender.
- Receipts for everything, queryable in the receipt warehouse.

## What you commit to

- Owning your inbox deployment (it lives in your namespace).
- Owning your executor (the platform doesn't decide what your AI does with prompts).
- Reviewing pairing requests promptly (other teams will request to talk to you; you decide).
- Keeping your trust policy current (remove stale senders quarterly).
- Being on call for your team-AI's availability.

---

## Step 1 — Decide what your team-AI does

Before any technical work, write down:

1. **Identifier:** kebab-case, globally unique, e.g. `concierge-orlando`. Convention: `<function>-<region>` or `<function>-<product-line>`.
2. **What scopes does your team-AI offer?** A scope is a verb-flavored string for the kinds of requests you accept. Examples: `concierge.lookup`, `concierge.handoff`, `dining.rsvp`, `loyalty.redeem`. Pick 1–5 scopes for v1; you can add more later.
3. **Data classification:** `public`, `internal`, `confidential`, or `restricted`. If your team-AI ever touches guest PII, you're at least `confidential`. If it touches payment or health data, `restricted` (and check with security first — payment scopes are gated).
4. **On-call rotation:** PagerDuty (or equivalent) reference for your team's on-call.
5. **Owner email:** the team's tech manager.

This is the data you'll register in step 3.

## Step 2 — Pick your executor

The executor is what your inbox does with a verified envelope. Four reference executors ship with the platform; pick one.

| Executor | When to pick it |
|---|---|
| `LoggerExecutor` | Required for the first 14 days of any pairing. Records, doesn't act. |
| `QueueExecutor` | You already have an async work queue (SQS, Pub/Sub, Kafka). Inbox pushes to it; your worker pool processes. Most decoupled. |
| `DirectModelExecutor` | Synchronous call to your LLM. Lowest latency. Use for read-only scopes. |
| `HumanReviewExecutor` | Required for any scope with side effects (bookings, refunds, guest messaging) until your team explicitly graduates a scope to autonomous. |

You can wrap any of these with `ChainExecutor` to add a PII scrub or prompt-injection filter. The platform ships a reference `ChainExecutor` with a default filter chain — use it.

If none of the reference executors fit, write your own against the `Executor` interface. Your executor must:

- Accept a verified `Envelope`.
- Return an `ExecutorResult` with `outcome` and optional `result_ref`.
- Complete within your declared deadline (default 30s; declare your own in inbox config).
- Not log raw prompts or PII at INFO (see [07](07-observability.md)).

## Step 3 — Register your team-AI

The platform team's admin runs this on your behalf in v1. After phase 7, you'll do it via the self-service portal.

```
eppctl-admin team-ai register \
  --id your-team-ai \
  --team your-team-name \
  --owner your-tech-manager@... \
  --on-call pagerduty:your-team-oncall \
  --scopes "your.scope.one,your.scope.two" \
  --classification internal \
  --kms-key-arn <provided-by-platform-team>
```

The platform team:
1. Creates a KMS key in your service identity's allowed scope.
2. Calls the registry to register your team-AI.
3. Returns the `kms_key_arn` for your inbox config.

After ~30 seconds, your team-AI is `state: active` in the registry and your pubkey is published.

## Step 4 — Deploy your inbox

In your team's GitOps repo, add:

```yaml
# teams/your-team/inbox/values.yaml
teamAi:
  id: your-team-ai
  team: your-team-name
  kmsKeyArn: <from step 3>
executor:
  kind: logger          # start with logger, switch later
  config: {}
trustPolicy:
  defaultAction: deny
  bootstrapFromGitOps: true
  gitopsPath: teams/your-team/trust-policies/your-team-ai.yaml
```

And the trust policy file (start empty):

```yaml
# teams/your-team/trust-policies/your-team-ai.yaml
apiVersion: epp.internal/v1
kind: TrustPolicy
metadata:
  teamAiId: your-team-ai
spec:
  defaultAction: deny
  senders: []      # populated as pairings get approved
```

Open a PR. CODEOWNERS is your team. Merge. ArgoCD applies. Within 5 minutes your inbox is up at `https://your-team-ai.inbox.internal`.

Verify:
```
curl https://your-team-ai.inbox.internal/epp/v1/healthz
curl https://your-team-ai.inbox.internal/epp/v1/info
```

## Step 5 — List your team-AI in the discovery portal

The portal entity is auto-generated from registry data, but you should fill in:

- A 1-paragraph description of what your team-AI is for.
- 2–3 example envelopes per scope, showing the prompt and context shape you expect.
- Your SLO commitments (e.g. "p95 < 2s, 99.5% success rate, business hours only").

This is what other teams will read when deciding to request a pairing. Treat it like API documentation.

## Step 6 — Receiving pairings

Another team requests to send envelopes to you via the discovery portal. You see a notification. To approve:

1. Read the requester's justification.
2. Look at their team-AI's portal page — what is it? what's its track record (success rate, classification)?
3. Decide on the scopes you'll grant. Subset of what they requested is fine.
4. Decide on the rate limit. Default: `burst=10, sustained=2/sec`. Raise after watching real traffic.
5. Click **Approve in log-only mode**. The portal opens a PR against your trust-policy file.
6. Merge the PR (requires another team-member's approval).
7. Wait 14 days. Watch their envelopes flow in via your dashboard. If anything looks wrong, investigate before promoting.
8. After 14 days, click **Promote to live**. Another PR, another merge.

This is intentionally slower than a "click yes" flow. Trust is the product; rushing trust defeats the protocol.

## Step 7 — Sending envelopes

To send to another team-AI, they must accept you as a sender (their step 6).

Once accepted, your code uses the EPP client SDK (Python reference; equivalent in your language):

```python
from epp.client import EppClient
from epp.crypto.kms_signer import KmsSigner

client = EppClient(
    sender_team_ai_id="your-team-ai",
    signer=KmsSigner(kms_key_arn=os.environ["EPP_KMS_KEY_ARN"]),
    registry_url="https://registry.internal",
)

receipt = await client.send(
    recipient_team_ai_id="dining-orlando",
    scope="dining.rsvp",
    prompt="Is there a 7pm table for 4 at any of the steakhouses near the guest's current location?",
    context={"guest_id_token": guest_token, "current_location": {"lat": ..., "lon": ...}},
    delegation={"on_behalf_of": guest_pubkey_hash, "authorization": guest_token},
)
```

The SDK handles: pubkey lookup, KMS signing, HTTP POST, retries with idempotency, receipt parsing.

## Step 8 — Watching your traffic

Three places to look:

- **Your dashboard** (Dashboard B in [07](07-observability.md)) — real-time throughput, latency, errors.
- **Receipt warehouse** — `GET /receipts/v1/?recipient=your_pubkey` for received, `?sender=your_pubkey` for sent.
- **Discovery portal** — `status.envelopes_24h`, `status.p95_latency_ms` are computed and shown.

Set up alerts that page your on-call on:
- Your inbox p95 latency above your declared SLO.
- Your executor failure rate above 1%.
- Any sender's `bad_signature` rate spiking against your inbox.

## Step 9 — Quarterly hygiene

Once per quarter, your team should:

1. Review your trust policy. Remove senders you haven't seen in 90 days. Tighten rate limits where actuals are 10× below the configured cap.
2. Review your scopes. If a scope has no envelopes for a quarter, retire it.
3. Review your receipts. Look for patterns: same sender always failing, same scope always slow, same conversation_id always errored.
4. Confirm on-call rotation is current.

## Common questions

**Can I rate-limit by source application within a sender team-AI?**
Not at the protocol level. Your executor can inspect the envelope's `payload.context` for an app identifier and apply its own throttling. EPP's rate limiter is per `(sender, scope)`.

**Can I require a stronger authorization than just "trusted sender"?**
Yes — your executor can inspect `delegation.authorization` and reject envelopes whose principal lacks specific permissions. EPP guarantees the envelope is from a trusted sender; what the sender is authorized to ask for *on the principal's behalf* is your executor's call.

**What if I want to send to a team that hasn't onboarded?**
You can't. They must onboard their team-AI first. Use the portal to express interest; the platform team can nudge.

**How do I rotate my key?**
Operator action via `eppctl-admin team-ai rotate`. Your inbox config (the `kmsKeyArn`) updates. Old signatures remain valid during the overlap window. See [05](05-key-management.md).

**My executor crashes on certain envelopes. What happens to the senders?**
They get an `executor_failure` receipt. If your executor is broken, you're broken — fix it. The mesh delivered the envelope correctly; what your executor did is on you.

**Can I see the full payloads I received?**
Only what your executor stored. The mesh does not store payloads — only receipt metadata. If you want auditable payload retention, store it yourself and reference via `executor_result_ref`.

**Can I block a specific sender mid-flight?**
Yes — `DELETE /admin/v1/policy/senders/{pubkey}` on your own inbox. Takes effect within ~60s.
