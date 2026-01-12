<p align="center">
  <img src="https://img.shields.io/badge/EPP-External_Prompt_Protocol-6366f1?style=for-the-badge&labelColor=1e1b4b" alt="EPP">
</p>

<h3 align="center">Cryptographically signed prompt delivery for user-owned AI</h3>

<p align="center">
  <em>Your AI works for you — not for every company you interact with.</em>
</p>

<p align="center">
  <a href="https://github.com/elliptic1/external-prompt-protocol/actions"><img src="https://github.com/elliptic1/external-prompt-protocol/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.9+-3776ab.svg" alt="Python 3.9+"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT"></a>
  <a href="https://github.com/elliptic1/external-prompt-protocol/stargazers"><img src="https://img.shields.io/github/stars/elliptic1/external-prompt-protocol?style=social" alt="GitHub Stars"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="#why-epp">Why EPP</a> •
  <a href="#features">Features</a> •
  <a href="#use-cases">Use Cases</a> •
  <a href="docs/spec.md">Specification</a> •
  <a href="#contributing">Contributing</a>
</p>

---

## The Problem

Today, every company runs its own AI chatbot. You interact with dozens of fragmented, low-quality bots that don't know you or your preferences.

**EPP flips this model.**

Instead of talking to *their* AI, they send signed messages to *your* AI. You control who's trusted, what they can send, and how your AI handles it.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   TODAY                              WITH EPP                               │
│   ─────                              ────────                               │
│                                                                             │
│   You ←→ Store's AI                  Store ──signed prompt──→ YOUR AI       │
│   You ←→ Bank's AI                   Bank  ──signed prompt──→ YOUR AI       │
│   You ←→ Airline's AI                Airline ─signed prompt─→ YOUR AI       │
│                                                                             │
│   (Fragmented, no context)           (Unified, you're in control)           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Install

```bash
pip install external-prompt-protocol
```

### Create and Sign an Envelope

```python
from epp.crypto.keys import KeyPair
from epp.crypto.signing import sign_envelope, generate_nonce
from datetime import datetime, timedelta
from uuid import uuid4

# Generate keys
sender = KeyPair.generate()
recipient = KeyPair.generate()

# Sign an envelope
signature = sign_envelope(
    sender,
    version="1",
    envelope_id=str(uuid4()),
    sender=sender.public_key_hex(),
    recipient=recipient.public_key_hex(),
    timestamp=datetime.utcnow().isoformat() + "Z",
    expires_at=(datetime.utcnow() + timedelta(minutes=15)).isoformat() + "Z",
    nonce=generate_nonce(),
    scope="notifications",
    payload={"prompt": "Your order has shipped!", "context": {}, "metadata": {}}
)
```

### Run an Inbox Server

```bash
eppctl keys generate --output inbox
epp-inbox --config config.yaml
```

That's it. You're now receiving cryptographically verified prompts.

---

## Why EPP

| | Without EPP | With EPP |
|---|-------------|----------|
| **Control** | Companies control the AI | You control the AI |
| **Trust** | Implicit (you hope it's them) | Cryptographic (Ed25519 signatures) |
| **Context** | Starts fresh every time | Your AI knows your history |
| **Privacy** | Your data on their servers | Prompts delivered to your system |
| **Spam** | Whatever they want to send | Explicit trust + rate limits |

---

## Features

### Core Protocol

- **Ed25519 Signatures** — Every envelope is cryptographically signed
- **Replay Protection** — Nonce + expiration prevents replay attacks
- **Trust Registry** — Explicit per-sender trust with scope restrictions
- **Rate Limiting** — Per-sender hourly/daily limits
- **Model Agnostic** — Works with any LLM (local, cloud, agent frameworks)

### Transport Options

| Transport | Server Required | Best For |
|-----------|-----------------|----------|
| **HTTP** | Yes (FastAPI inbox) | Web services, always-on systems |
| **Solana** | No | Wearables, IoT, offline-first devices |

```bash
# HTTP transport (default)
pip install external-prompt-protocol

# With Solana blockchain transport
pip install external-prompt-protocol[solana]
```

### Reference Implementation

- `eppctl` — CLI for keys, trust management, and envelope creation
- `epp-inbox` — FastAPI server with pluggable executors
- **Executors** — File queue, command execution, logging, no-op

---

## Use Cases

### App Store Rejection Notice

```python
# App store signs and sends rejection directly to developer's AI
envelope = create_envelope(
    scope="app-review",
    prompt="Your app was rejected: Missing privacy policy in Settings.",
    context={"app_id": "com.example.myapp", "submission_id": "12345"}
)
```

Developer's AI receives it, analyzes the issue, and suggests fixes.

### Retail Product Support

```python
# After purchase, retailer sends product manual to your AI
envelope = create_envelope(
    scope="product-support",
    prompt="Here's the setup guide for your new espresso machine.",
    context={"product": "Breville BES870", "manual_url": "..."}
)
```

Your AI now knows how to help you troubleshoot it.

### Wearable Notifications

```python
# Coffee shop delivers prompt via Solana (no server needed)
from epp.transport.solana import SolanaTransport

transport = SolanaTransport(keypair_path="store-wallet.json")
await transport.send(envelope, customer_solana_address)

# Customer's smart glasses poll the chain, AI whispers:
# "The coffee shop has your usual ready, 20% off today"
```

---

## How It Works

```
┌──────────┐     ┌─────────────────────────────────────────────────────┐     ┌──────────┐
│          │     │                    EPP ENVELOPE                     │     │          │
│  SENDER  │────▶│  ┌─────────────────────────────────────────────┐   │────▶│  INBOX   │
│          │     │  │ sender: <public key>                        │   │     │          │
└──────────┘     │  │ recipient: <public key>                     │   │     └────┬─────┘
                 │  │ timestamp: 2025-01-12T09:00:00Z              │   │          │
   Signs with    │  │ expires_at: 2025-01-12T09:15:00Z             │   │     Verifies
   private key   │  │ nonce: <random>                              │   │     signature
                 │  │ scope: "notifications"                       │   │          │
                 │  │ payload: { prompt: "...", context: {...} }   │   │          ▼
                 │  │ signature: <Ed25519 signature>               │   │     ┌──────────┐
                 │  └─────────────────────────────────────────────┘   │     │ EXECUTOR │
                 └─────────────────────────────────────────────────────┘     │ (Model)  │
                                                                             └──────────┘
```

1. **Sender** creates an envelope with prompt + context
2. **Sender** signs with their Ed25519 private key
3. **Envelope** delivered via HTTP or blockchain
4. **Inbox** verifies signature against trust registry
5. **Inbox** applies policies (scope, size, rate limits)
6. **Executor** forwards to your AI model

---

## Documentation

| Document | Description |
|----------|-------------|
| [Protocol Specification](docs/spec.md) | Formal protocol definition |
| [Threat Model](docs/threat-model.md) | Security analysis and mitigations |
| [Quick Start Guide](docs/quickstart.md) | HTTP inbox setup tutorial |
| [Solana Transport](docs/solana-transport.md) | Blockchain transport for serverless delivery |

---

## Installation

### From PyPI

```bash
pip install external-prompt-protocol
```

### From Source

```bash
git clone https://github.com/elliptic1/external-prompt-protocol.git
cd external-prompt-protocol
pip install -e ".[dev]"
```

### Optional: Solana Transport

```bash
pip install external-prompt-protocol[solana]
```

---

## CLI Reference

```bash
# Key management
eppctl keys generate --output mykeys
eppctl keys show mykeys.pub

# Trust registry
eppctl trust add --public-key <KEY> --name "Acme Corp" --scopes "notifications,support"
eppctl trust list
eppctl trust remove <KEY>

# Envelope operations
eppctl envelope create --private-key sender.key --recipient <KEY> --scope notifications --prompt "Hello!"
eppctl envelope send envelope.json http://localhost:8000
eppctl envelope verify envelope.json
```

---

## Comparison with Other Protocols

| | EPP | MCP | Direct API |
|---|-----|-----|------------|
| **Purpose** | Who can send prompts | How tools expose context | Model inference |
| **Auth model** | Cryptographic signatures | Transport-level | API keys |
| **User control** | Full (trust registry) | Limited | None |
| **Replay protection** | Built-in (nonce) | None | None |
| **Works with** | Any model | Claude, others | Specific provider |

EPP is **complementary** to MCP — use both together.

---

## Project Status

| | Status |
|---|--------|
| Protocol Version | v1 (draft) |
| Stability | Experimental |
| License | MIT |

The protocol is intentionally minimal in v1 to encourage adoption. Future extensions may include payments, anonymity features, and more transport options.

---

## Contributing

Contributions are welcome! Here's how to help:

1. **Report bugs** — [Open an issue](https://github.com/elliptic1/external-prompt-protocol/issues)
2. **Suggest features** — Start a discussion
3. **Submit PRs** — Fork, branch, and submit

### Development Setup

```bash
git clone https://github.com/elliptic1/external-prompt-protocol.git
cd external-prompt-protocol
pip install -e ".[dev]"
pytest tests/ -v
```

### Code Style

```bash
black epp/ cli/ tests/
ruff check epp/ cli/ tests/
mypy epp/ cli/
```

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <strong>Your AI should work for you.</strong><br>
  EPP makes that cryptographically enforceable.
</p>

<p align="center">
  <a href="https://github.com/elliptic1/external-prompt-protocol">GitHub</a> •
  <a href="https://github.com/elliptic1/external-prompt-protocol/issues">Issues</a> •
  <a href="docs/spec.md">Specification</a>
</p>
