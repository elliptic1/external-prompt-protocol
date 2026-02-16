# AI-to-AI Services - Example Implementation

This is a **reference implementation** showing how to build paid consultation services on top of EPP. It is **not** part of the core EPP protocol.

## Use Case

A person wants legal advice but:
- Doesn't want to leave the house
- Doesn't want to talk to a human
- Just wants to talk to their own AI

Their AI pays a fee to use the lawyer's AI. The two AIs communicate. The lawyer doesn't do extra work. The person only talks to their own AI.

## Components

- `services.py` — Models and helpers for AI-to-AI services
- `test_services.py` — Tests (46 passing)

## Key Models

### Client-Facing
- `ServiceListing` — What a professional AI offers (pricing, tiers, jurisdiction)
- `ServiceRequest` — Query from client AI with payment proof
- `ServiceResponse` — Response with advice, confidence, citations
- `ConsultationSession` — Multi-turn session for per-session billing

### Provider-Side (Lawyer ↔ Lawyer's AI)
- `CaseRecord` — Case tracking with facts, guidance, AI questions
- `CaseMemory` — Memory store indexed by client
- `ProviderSession` — Conversation between provider and their AI

## Running

```bash
cd examples
PYTHONPATH=..:. python3 lawyer_consultation.py
PYTHONPATH=..:. python3 provider_workflow.py
```

## Tests

```bash
cd examples/services
PYTHONPATH=../..:. python3 -m pytest test_services.py -v
```

## This is NOT Part of EPP Core

EPP core provides:
- Cryptographic envelopes and signatures
- Trust registry
- Transport (HTTP, Solana)
- Replay protection

This services layer shows one way to build on top of that foundation.
