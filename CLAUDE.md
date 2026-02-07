# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

External Prompt Protocol (EPP) is a cryptographically verified, consent-based protocol for delivering external prompts to user-owned AI systems. It uses Ed25519 signatures, per-sender trust policies, and a pluggable executor architecture. Python 3.9+, MIT licensed.

## Commands

```bash
# Install from source with dev dependencies
pip install -e ".[dev]"

# Run all tests with coverage
pytest tests/ -v --cov=epp

# Run a single test file
pytest tests/unit/test_crypto.py -v

# Run a single test by name
pytest tests/unit/test_crypto.py::test_sign_and_verify -v

# Lint
ruff check epp/ cli/ tests/

# Format (check only)
black --check epp/ cli/ tests/

# Format (apply)
black epp/ cli/ tests/

# Type check
mypy epp/ cli/

# Build package
python -m build
```

## Architecture

The protocol processes envelopes through a 10-step verification pipeline:

```
Sender → sign_envelope() → Envelope → HTTP POST /epp/v1/submit → InboxServer
                                                                      │
                                                              InboxProcessor
                                                                      │
                                              ┌───────────────────────┼───────────────────────┐
                                              ▼                       ▼                       ▼
                                        Parse/Validate         Crypto Verify           Policy Check
                                        (models.py)            (crypto/)               (policy/)
                                                                                          │
                                                                                    ┌─────┼─────┐
                                                                                    ▼     ▼     ▼
                                                                                Trust  Rate  Nonce
                                                                              Registry Limit Registry
                                                                                          │
                                                                                          ▼
                                                                                    Executor
                                                                              (FileQueue/Logger/
                                                                               Command/NoOp/Custom)
```

**Key modules:**
- `epp/crypto/` - Ed25519 key management (`keys.py`) and envelope signing/verification (`signing.py`)
- `epp/models.py` - Pydantic models: `Envelope`, `Payload`, `Receipt`, error codes
- `epp/inbox/` - FastAPI server (`server.py`) and the 10-step processing pipeline (`processor.py`)
- `epp/policy/` - `TrustRegistry` (per-sender policies + JSON persistence), `RateLimiter` (token bucket), `NonceRegistry` (replay prevention)
- `epp/executors/` - Abstract `Executor` base class with `FileQueueExecutor`, `LoggerExecutor`, `CommandExecutor`, `NoOpExecutor`
- `epp/transport/` - Abstract `Transport` base class with HTTP and Solana implementations
- `cli/main.py` - Click CLI (`eppctl`) for key generation, trust management, envelope operations

**Entry points** (defined in pyproject.toml):
- `eppctl` → `cli.main:cli`
- `epp-inbox` → `epp.inbox.server:main`

## Code Style

- **Line length:** 100 (both black and ruff)
- **Target:** Python 3.9
- **Type checking:** mypy with `disallow_untyped_defs = true`
- **Async tests:** pytest-asyncio with `asyncio_mode = "auto"`

## Canonical Signing Format

Envelope signatures use a deterministic canonical format (newline-separated fields in fixed order). This is critical -- any change to field ordering or serialization in `create_canonical_payload()` in `epp/crypto/signing.py` will break all existing signatures.

## Protocol Spec

The formal specification lives in `docs/spec.md`. Changes to protocol behavior should stay consistent with this spec, or the spec should be updated alongside code changes.
