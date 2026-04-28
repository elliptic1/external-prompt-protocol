# Internal AI Mesh — Build Documentation

This directory contains the complete documentation set required to build an EPP-based internal AI mesh inside a large enterprise. It is written to be **fed to an AI builder** — every doc is self-contained, terms are consistent, and decisions are explicit.

## Read in this order

| # | Doc | Purpose |
|---|-----|---------|
| — | [Use case](../use-case-enterprise-ai-mesh.md) | Why this exists. Read first. |
| — | [Testing guide](../testing-guide-enterprise-ai-mesh.md) | How to verify it works. Read second. |
| 00 | [Glossary](00-glossary.md) | Canonical terms. Reference throughout. |
| 01 | [Build plan](01-build-plan.md) | Phased roadmap with acceptance criteria per phase. |
| 02 | [Service architecture](02-service-architecture.md) | Decomposition into discrete services with responsibilities and ownership. |
| 03 | [API contracts](03-api-contracts.md) | HTTP APIs every platform service exposes. |
| 04 | [Data schemas](04-data-schemas.md) | Postgres tables, Redis keyspace, queue topics, receipt JSON shape. |
| 05 | [Key management](05-key-management.md) | KMS integration, signing, rotation, revocation. |
| 06 | [Security threat model](06-security-threat-model.md) | STRIDE-style enumeration with controls. |
| 07 | [Observability](07-observability.md) | Metrics, traces, logs, alerting. |
| 08 | [Deployment](08-deployment.md) | Kubernetes layout, environments, GitOps. |
| 09 | [Team onboarding runbook](09-team-onboarding.md) | What a receiving team does to join the mesh. |
| 10 | [Runbooks and SLOs](10-runbooks-and-slos.md) | Operational procedures and service-level commitments. |

## What's NOT in this doc set (and why)

- **The protocol spec itself.** That lives in [`docs/spec.md`](../spec.md) and is the single source of truth for envelope shape, signing, and verification semantics. These build docs assume it as a dependency, not a substitute.
- **Org-specific names.** No team names, no business unit names, no internal product names. Substitute when handing to your platform team.
- **Vendor lock-in.** Where a doc says "Redis" or "Postgres," any equivalent works. Where a doc says "your KMS," wire in your specific one.
- **LLM choices.** Each team's executor calls whatever model the team uses. The mesh does not care.

## Conventions used across all docs

- "**Team-AI**" means an AI agent owned by one product team.
- "**Inbox**" means the EPP server process that receives envelopes for a team-AI.
- "**Sender**" / "**recipient**" are envelope-level terms, identified by Ed25519 pubkey hex.
- "**Scope**" is the policy axis — a free-form string the sender chooses (e.g. `"dining.rsvp"`).
- "**Platform team**" owns the central services. "**Product team**" owns one or more team-AIs.
- API examples use `application/json` unless stated otherwise.
- All timestamps are ISO-8601 UTC.
- All pubkeys are 64-char lowercase hex.
- Code blocks marked `python` are reference snippets; the actual implementation language is at the platform team's discretion (the EPP reference is Python; receiving teams may use any language with an EPP client library).
