External Prompt Protocol (EPP)

External Prompt Protocol (EPP) is an open, model-agnostic protocol that allows third parties to deliver authorized, cryptographically verifiable prompts and context into a user-owned AI system.

EPP is designed for a future where individuals run and trust their own personal AI models, while selectively granting external entities permission to supply prompts, context, or task requests—without surrendering control to centralized platforms.


---

Why EPP Exists

Today, every organization is expected to operate its own AI system:

Retailers run chatbots

App stores issue rejection messages

Manufacturers publish PDFs and support portals

Governments build bespoke AI workflows


These systems are often expensive, fragmented, low quality, and opaque.

EPP reverses this model.

Instead of every organization operating an AI, each user operates their own AI, and trusted third parties deliver structured context directly into it.

Examples:

An app store delivers a signed rejection notice directly to your coding AI.

A retailer delivers product manuals to your personal AI after purchase.

A service provider submits configuration or compliance prompts you’ve pre-approved.

An automated agent triggers a task on your AI with explicit user consent.


EPP provides the authorization, authentication, and delivery layer for these interactions.


---

What EPP Is (and Is Not)

EPP is:

A protocol for external prompt delivery

Cryptographically authenticated (signed messages)

Explicitly consent-based

Model-agnostic

Transport-agnostic (HTTP recommended, not required)

Compatible with local models, cloud APIs, and agent frameworks


EPP is not:

A chatbot

A model hosting platform

A wallet or payment network (though compatible with them)

A replacement for tool-execution protocols (e.g., MCP)


EPP focuses narrowly on who is allowed to send prompts and context into a model, and under what rules.


---

Core Concepts

User-Owned AI

The user controls:

Which models they run

Where they run them

Which entities are trusted to deliver prompts

How those prompts are handled


Trusted Senders

External entities (companies, agents, services, people) are identified by public keys.

A sender can only interact with a user’s AI if:

Their public key is explicitly trusted

Their message is correctly signed

The request complies with the user’s policy


Prompt Envelopes

All requests are sent as signed envelopes containing:

Metadata (sender, time, scope)

Payload (prompt + optional context)

Cryptographic signature


The envelope is verified before any model interaction occurs.

Inbox Model

Users run an EPP Inbox service that:

1. Receives envelopes

2. Verifies signatures

3. Applies policy (scope, rate limits, size, routing)

4. Forwards accepted prompts to the configured model or executor

5. Returns a receipt



---

High-Level Flow

1. User runs an EPP-compatible Inbox

2. User explicitly trusts a sender’s public key

3. Sender creates and signs an EPP envelope

4. Sender delivers the envelope to the Inbox

5. Inbox verifies, applies policy, and executes or queues the prompt

6. Inbox returns an acceptance or rejection receipt



No shared accounts.
No implicit trust.
No silent execution.


---

Relationship to Other Protocols

EPP is complementary to existing AI infrastructure:

Model Context Protocol (MCP)
MCP defines how models and tools expose context.
EPP defines who is allowed to inject context.

LLM APIs (OpenAI, Anthropic, local models)
EPP does not replace model APIs.
It sits in front of them as an authorization layer.

Agent frameworks
EPP provides a secure external trigger mechanism for agents.



---

Security Model (Summary)

Asymmetric cryptography (Ed25519 recommended)

All envelopes are signed, not trusted by transport

Replay protection via nonce + expiration

Explicit sender trust registry

Policy enforcement before execution

No requirement to expose Inbox publicly


See docs/threat-model.md for details.


---

Reference Implementation

This repository includes:

A formal protocol specification

A Python reference Inbox (FastAPI)

A CLI tool (eppctl) for key management and message sending

Pluggable executors (file queue, command execution, no-op)

Tests and CI


The reference implementation is not required to use EPP.
Any language, runtime, or model may implement the protocol.


---

Status

Current version: EPP v1 (draft)

Stability: Experimental

License: MIT


The protocol is intentionally minimal in v1 to encourage adoption and experimentation.


---

Non-Goals (v1)

Payments / gas fees

Blockchain or ledger dependencies

End-to-end anonymity

Tool execution graphs

Model-specific features


These may be explored in future extensions.


---

Getting Started

See:

docs/spec.md — Protocol specification

docs/threat-model.md — Security considerations

README-quickstart.md — Reference implementation usage (if included)



---

Philosophy

EPP is built on a simple premise:

> Your AI should work for you—not for every company you interact with.



External Prompt Protocol exists to make that premise technically and cryptographically enforceable.


---

If you want, next we can:

write the EPP Abstract in RFC style

define EPP Envelope v1 formally

write a Quickstart that hackers can run in 5 minutes

or draft a “Comparison to MCP / OAuth / Webhooks” section