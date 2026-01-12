# EPP Announcement Drafts

Ready-to-post announcements for External Prompt Protocol.

---

## X/Twitter

```
External Prompt Protocol - an open standard for cryptographically verified prompt delivery to user-owned AI systems.

Instead of every company running their own AI, your AI runs for you. Third parties deliver signed prompts with explicit consent.

Ed25519 signatures. Model-agnostic. MIT licensed.

github.com/elliptic1/external-prompt-protocol
```

---

## Hacker News (Show HN)

**Title:** Show HN: External Prompt Protocol - Signed prompt delivery for user-owned AI

**Body:**

EPP is an open protocol for external entities to deliver authorized prompts to your personal AI. Think of it as the authorization layer for the "everyone runs their own AI" future.

- Ed25519 signatures, not trusted by transport
- Explicit consent via trust registry
- Per-sender policies (scopes, rate limits)
- Model and transport agnostic

Use cases: app stores delivering rejection notices, retailers sending product manuals, services triggering pre-approved tasks.

Reference implementation in Python with CLI, FastAPI server, and docs. MIT licensed.

---

## Reddit (r/LocalLLaMA)

**Title:** External Prompt Protocol - Open standard for external prompt delivery to your local AI

**Body:**

Built a protocol for the scenario where you run your own AI and want external services to deliver prompts to it securely.

The idea: instead of every company running chatbots, they send signed prompts to YOUR AI. You control who's trusted, what scopes they can use, and rate limits.

- Ed25519 cryptographic signatures
- Replay protection (nonce + expiration)
- Trust registry with per-sender policies
- Works with any model (local or API)

Python reference implementation with CLI and FastAPI server. Docs include formal spec and threat model.

MIT licensed: https://github.com/elliptic1/external-prompt-protocol

---

## LinkedIn

External Prompt Protocol (EPP) - a new open standard for the AI landscape.

Today, every organization operates its own AI system. EPP reverses this: users run their own AI, and trusted third parties deliver signed prompts to it.

Key features:
- Cryptographic authentication (Ed25519)
- Explicit consent with per-sender policies
- Model and transport agnostic
- Replay protection built-in

Use cases range from app stores delivering rejection notices to retailers sending product documentation to a customer's personal AI.

The protocol is intentionally minimal to encourage adoption. Reference implementation in Python, MIT licensed.

https://github.com/elliptic1/external-prompt-protocol
