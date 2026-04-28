# 08 — Deployment

How the platform is laid out in Kubernetes, how environments are separated, and how changes are promoted.

## Environments

Three environments. Each is a fully independent mesh — no envelopes ever cross environments.

| Env | Purpose | Pubkeys | Registry | Receipt retention |
|---|---|---|---|---|
| `dev` | Engineer loops, local + shared dev cluster | LocalKeypairSigner allowed | In-memory or per-engineer Postgres | 7 days |
| `staging` | Pre-prod integration, mirrors prod topology | KMS (separate keys from prod) | Postgres (staging) | 30 days |
| `prod` | Live mesh | KMS (prod keys) | Postgres (prod) | 7 years for restricted, 2 years for internal |

A team-AI in `dev` cannot send to a team-AI in `staging`. The protocol does not enforce this; the deployment topology does (separate clusters, separate registries, no shared transport).

## Cluster layout

Recommended: one Kubernetes cluster per environment per region. Inboxes deployed into per-team namespaces. Platform services in a `epp-platform` namespace.

```
cluster: prod-us-east-1
├── namespace: epp-platform
│   ├── identity-registry      (3 replicas, behind service mesh)
│   ├── receipt-warehouse-api  (3 replicas)
│   ├── receipt-sink           (deployment + worker pool)
│   ├── discovery-portal       (2 replicas)
│   ├── audit-log-writer       (2 replicas)
│   └── synthetic-prober       (1 replica, runs SLO probes)
├── namespace: epp-shared
│   ├── redis-nonce-cluster    (StatefulSet, 6 nodes)
│   ├── redis-rate-cluster     (StatefulSet, 6 nodes)
│   └── postgres-registry      (managed external; reference only)
├── namespace: in-venue-experience
│   └── concierge-orlando-inbox  (Deployment, 3 replicas, owned by product team)
├── namespace: dining
│   └── dining-orlando-inbox     (Deployment, 3 replicas, owned by product team)
└── namespace: ...one per product team
```

Per-team namespaces are owned by the product team. Platform team owns `epp-platform` and `epp-shared`. Network policies restrict cross-namespace traffic to:

- Team namespace → `epp-shared` Redis (nonce, rate)
- Team namespace → `epp-platform` registry (pubkey lookups)
- Team namespace → other team namespaces (envelope POST)
- Team namespace → KMS (sign)
- Team namespace → team's own external services (executor backends)

## Helm chart structure

The platform team publishes one chart that any product team installs:

```
charts/epp-inbox/
├── Chart.yaml
├── values.yaml                # documented defaults
├── templates/
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── serviceaccount.yaml    # bound to team-AI's KMS key
│   ├── configmap.yaml         # trust policy bootstrap
│   ├── networkpolicy.yaml
│   ├── poddisruptionbudget.yaml
│   ├── horizontalpodautoscaler.yaml
│   ├── servicemonitor.yaml    # Prometheus
│   └── certificate.yaml       # cert-manager for ingress
└── README.md
```

**Required `values.yaml` overrides per inbox install:**

```yaml
teamAi:
  id: concierge-orlando
  team: in-venue-experience
  kmsKeyArn: arn:aws:kms:us-east-1:...:key/...
executor:
  kind: queue
  config:
    queueUrl: ...
trustPolicy:
  defaultAction: deny
  bootstrapFromGitOps: true
  gitopsPath: trust-policies/concierge-orlando.yaml
```

Defaults in chart `values.yaml` cover everything else (replicas: 3, HPA min/max, resource requests/limits, sidecar config).

## GitOps for trust policies

Trust policies are checked into a git repo, one file per team-AI. ArgoCD (or equivalent) reconciles them into the per-inbox trust registry.

```
gitops-repo/
├── platform/
│   ├── identity-registry/        # platform-managed configs
│   └── shared/
└── teams/
    ├── in-venue-experience/
    │   └── trust-policies/
    │       └── concierge-orlando.yaml
    └── dining/
        └── trust-policies/
            └── dining-orlando.yaml
```

A trust policy file:

```yaml
apiVersion: epp.internal/v1
kind: TrustPolicy
metadata:
  teamAiId: dining-orlando
spec:
  defaultAction: deny
  clockSkewSeconds: 60
  maxPayloadBytes: 65536
  senders:
    - senderTeamAiId: concierge-orlando
      senderPubkey: abcd...64hex   # validated against registry on apply
      scopes: [dining.rsvp, dining.lookup]
      rateLimit:
        burst: 10
        sustainedPerSecond: 2
      mode: live
      addedAt: 2026-04-27T10:00:00Z
      addedBy: tech-manager-email
      expiresAt: null
```

**Pull request flow:** A pairing approval in the discovery portal opens a PR against this file. CODEOWNERS for `teams/dining/` is the dining team's tech leads. They approve, ArgoCD applies, the change is live within ~60s.

## Service mesh / network policy

If the org runs Istio, Linkerd, or equivalent: deploy inbox pods with sidecar mTLS. Inbox-to-inbox traffic is wrapped in mTLS by the mesh; the EPP signature is the *inner*, authoritative trust check.

Authorization at the mesh layer should be **permissive** for envelope traffic. The mesh layer says "yes, this came from a known service identity in the cluster"; the inbox's pipeline says "yes, this came from a sender we trust at the protocol level." Two layers of defense.

Mesh authorization should be **strict** for traffic to platform services (registry, receipt warehouse): only `epp-inbox` service accounts allowed.

## Pod-level configuration

Each inbox pod runs:

```
inbox-container               (the EPP server, FastAPI/uvicorn)
├── Listens on :8080 for /epp/v1/submit
├── Calls Redis (nonce, rate) over service mesh
├── Calls KMS (sign) over AWS SDK / equivalent
├── Calls registry (pubkey lookup, cached)
└── Emits OpenTelemetry to mesh-provided collector

executor-container            (optional, depending on executor kind)
├── For QueueExecutor: nothing extra; inbox writes directly to queue
├── For DirectModelExecutor: in-process, no separate container
├── For HumanReviewExecutor: a separate web UI service in same pod
└── For custom: team's choice

otel-collector-sidecar        (or DaemonSet on the node)
```

Resource defaults for the inbox container at v1 sizing:

```yaml
resources:
  requests:
    cpu: 200m
    memory: 256Mi
  limits:
    cpu: 1000m
    memory: 512Mi
```

HPA: scale on `epp_envelopes_received_total` rate. Target: 200 envelopes/sec/pod. Min replicas 3, max 50.

## Promotion flow (dev → staging → prod)

Code changes:

```
PR → tests → merge to main → image build →
  auto-deploy to dev →
  manual promote to staging (after smoke test) →
  manual promote to prod (after staging soak: 24h)
```

Trust policy changes:

```
PR against gitops-repo → CODEOWNERS approve → ArgoCD applies →
  audit-log-writer captures the change →
  inbox picks up via configmap reload (no restart needed)
```

Identity registry changes (registering a team-AI, rotating, revoking):

```
Operator action via admin CLI / UI → registry persists →
  audit log entry → cache-bust pubsub →
  inboxes refresh on next request
```

## Image management

| Image | Built by | Signed | Tag policy |
|---|---|---|---|
| `epp-inbox` | Platform team CI | cosign | semver + git sha |
| `epp-registry` | Platform team CI | cosign | semver + git sha |
| `epp-receipts-api` | Platform team CI | cosign | semver + git sha |
| `epp-receipt-sink` | Platform team CI | cosign | semver + git sha |
| `epp-discovery-portal` | Platform team CI | cosign | semver + git sha |

Admission policy: only cosign-signed images from the platform team's registry may run in `epp-platform`, `epp-shared`, or any namespace with the `epp-managed=true` label.

## Disaster recovery

| Loss event | RTO | RPO | Recovery |
|---|---|---|---|
| Single inbox pod crash | seconds | none | Pod restart, k8s handles |
| All inbox pods for one team-AI | < 5 min | none | New pods come up, pull config from gitops |
| Identity registry primary | < 15 min | < 1 min | Fail over to standby; inboxes serve from cache during gap |
| Redis nonce cluster | < 30 min | up to TTL window | Fail over; brief replay-protection gap covered by signature + expiry |
| Receipt warehouse blob store | n/a | none | Replicated; if primary loss, redirect writes to secondary |
| Whole cluster | < 4 hours | < 5 min | Multi-cluster failover; identity registry replicated cross-region |
| KMS (region) | KMS provider's RTO | none | KMS provider's responsibility; senders fail until KMS recovers |

DR drill quarterly. See [10](10-runbooks-and-slos.md).

## Local development

A `docker-compose.yml` in the repo brings up: 2 inbox containers (with LocalKeypairSigner), 1 Postgres, 1 Redis, 1 mock receipt sink. Engineers can:

```
docker-compose up
eppctl key generate --out alice.key
eppctl key generate --out bob.key
eppctl trust add --recipient bob --sender alice --scope demo.* --rate 10
eppctl envelope send --from alice --to bob --scope demo.echo --prompt "hello"
```

This loop should take under 30 seconds end-to-end. If it doesn't, the dev experience needs work before more teams are onboarded.

## What this doc does NOT cover

- Specific cluster sizing for prod beyond v1. That comes from capacity modeling once real envelope traffic is observed in pilot.
- Multi-cluster federation for cross-region. Defer to phase 7+.
- Cost optimization. Cover after the mesh is providing demonstrated value.
