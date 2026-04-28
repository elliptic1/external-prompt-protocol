# Testing Guide: EPP-Based Enterprise AI Mesh

**Audience:** Platform engineers and team-AI engineers building or integrating with an internal EPP mesh
**Companion to:** `use-case-enterprise-ai-mesh.md`
**Last updated:** 2026-04-27

---

## Why this app is unusual to test

Most internal services have one trust domain, one schema, one team. An EPP-based AI mesh has **three** independently moving parts, each owned by different people:

1. **The protocol layer** — envelope shape, signatures, canonical encoding. Owned by the platform team. Breakage here is silent and catastrophic (envelopes still look valid; signatures just don't match).
2. **The trust layer** — who is allowed to talk to whom, at what rate, under what scope. Owned by each receiving team. Breakage here is operational (legitimate traffic blocked, or worse, illegitimate traffic let through).
3. **The execution layer** — what the receiving AI actually does with a delivered prompt. Owned by each receiving team. Non-deterministic by nature (LLMs).

A good test suite separates these three concerns so a failure points at exactly one of them. A bad test suite mixes "did the signature verify" with "did the LLM produce a sensible answer," and then no one can debug a red build.

This guide is opinionated. It tells you what to test, in what layer, with what tools, and — equally important — **what not to test**.

---

## The seven test layers

Build them in this order. Each layer assumes the lower ones pass.

### Layer 1 — Crypto property tests

**Owned by:** Platform team
**Speed:** Sub-second per test, run on every commit

The signing/verification code is the foundation. If it has a bug, the entire mesh is compromised. Test it with **property-based testing**, not just example tests. Use `hypothesis`.

Properties to assert:

- Round-trip: for any well-formed envelope, `verify(sign(env)) == True`.
- Tamper detection: mutating any signed field invalidates the signature. Iterate over every field.
- Wrong-key detection: signature signed by key A does not verify under key B.
- Canonical encoding stability: the canonical encoding of a given envelope is byte-identical across runs, across Python versions, across dict insertion orders. **This is the test that catches the most dangerous class of bug** — a refactor that "looks fine" but silently changes byte ordering and breaks every existing signature in the mesh.
- Signature determinism: signing the same envelope twice produces the same signature (Ed25519 is deterministic).

```python
# tests/unit/test_crypto_properties.py
from hypothesis import given, strategies as st

@given(envelope_strategy())
def test_signature_round_trip(env):
    signed = sign_envelope(keypair, env)
    assert verify_envelope_signature(signed) is True

@given(envelope_strategy(), st.sampled_from(SIGNED_FIELDS))
def test_field_tampering_invalidates(env, field):
    signed = sign_envelope(keypair, env)
    mutated = mutate_field(signed, field)
    assert verify_envelope_signature(mutated) is False
```

**Critical regression test:** check in a fixture file `tests/fixtures/golden_signed_envelopes.json` containing 20+ envelopes signed with known keys. The test reloads them and verifies they still verify. This catches canonical-encoding drift across versions. **Never regenerate this fixture casually** — if it fails, you have probably broken backward compatibility with every signature ever produced.

### Layer 2 — Pipeline unit tests

**Owned by:** Platform team
**Speed:** Sub-second per test, run on every commit

Test the 10-step verification pipeline step by step, in isolation, with mocked dependencies. One test per failure mode per step.

The matrix you need to cover:

| Step | Happy path test | At least these failure tests |
|---|---|---|
| Parse | valid envelope parses | invalid JSON, missing field, wrong type, oversized payload |
| Recipient match | matches | mismatched recipient |
| Timestamp window | within skew | too old, too future, malformed timestamp, missing timezone |
| Expiry | not expired | expired by 1s, expired by 1d, expires before timestamp |
| Sender known | trusted | unknown sender, recently revoked sender |
| Signature verify | valid sig | bad sig, sig from wrong key, sig over wrong canonical form |
| Nonce check | first use | replay of same nonce, replay across senders (must be allowed) |
| Scope policy | scope allowed | scope denied, scope not in policy at all, scope with wildcards |
| Rate limit | under limit | at limit, over limit, burst then steady |
| Execute | executor succeeds | executor raises, executor times out, executor returns invalid result |

These tests should not touch Redis, KMS, or the network. Use the in-memory implementations of `NonceRegistry`, `TrustRegistry`, `RateLimiter` that ship in this repo.

**Anti-pattern:** writing one giant `test_full_pipeline_happy_path` that exercises all 10 steps. When it fails, you don't know which step broke. Decompose.

### Layer 3 — Adapter contract tests

**Owned by:** Platform team
**Speed:** Seconds per test, requires real backing services (use testcontainers)

Each pluggable backend (KMS signer, Redis nonce registry, Postgres trust registry, queue executor) gets a **contract test suite** that the abstract interface declares, and every implementation must pass.

The pattern:

```python
# tests/contracts/nonce_registry_contract.py
class NonceRegistryContract:
    """Every NonceRegistry implementation must pass these tests."""

    def make_registry(self) -> NonceRegistry: ...

    def test_first_use_accepted(self): ...
    def test_replay_rejected(self): ...
    def test_same_nonce_different_sender_accepted(self): ...
    def test_expired_nonce_can_be_reused(self): ...
    def test_concurrent_first_use_only_one_wins(self): ...

# tests/unit/test_in_memory_nonce_registry.py
class TestInMemoryNonceRegistry(NonceRegistryContract):
    def make_registry(self): return InMemoryNonceRegistry()

# tests/integration/test_redis_nonce_registry.py
class TestRedisNonceRegistry(NonceRegistryContract):
    def make_registry(self):
        return RedisNonceRegistry(redis_url=testcontainer_redis())
```

This is the single highest-leverage pattern in the suite. It guarantees that swapping an in-memory backend for Redis, or swapping a file-backed trust registry for Postgres, **does not change protocol behavior**. Without contract tests, every backend swap is a silent risk.

Targets that need a contract suite:

- `Signer` (in-memory keypair, KMS)
- `NonceRegistry` (in-memory, Redis)
- `TrustRegistry` (in-memory, file, DB)
- `RateLimiter` (in-memory, Redis)
- `Executor` (Logger, NoOp, Queue, DirectModel)
- `Transport` (HTTP, queue-backed, in-process)

### Layer 4 — Integration tests (single inbox)

**Owned by:** Platform team
**Speed:** Seconds per test, run on every PR

Stand up one real inbox process with real backing services (Redis, Postgres, mock KMS) using testcontainers or docker-compose. Hit it with HTTP. Verify receipts are returned and persisted.

What to test here that lower layers cannot:

- **HTTP layer concerns:** content-type negotiation, response codes match the protocol spec, malformed JSON returns 400 not 500, oversized requests rejected at the body-size limit.
- **Persistence:** after restart, the trust registry is intact, nonces older than the expiry window are gone (TTL works), receipts are durably written.
- **Concurrency:** N parallel clients sending unique envelopes all succeed; N parallel clients sending the *same* envelope all see exactly one execution and N receipts pointing at it.
- **Observability:** every step emits the expected metric/span; failure cases emit the failure metric.

Use `pytest-asyncio` and `httpx.AsyncClient`. Do NOT use the FastAPI `TestClient` for these — it bypasses real HTTP semantics.

### Layer 5 — Mesh integration tests (multi-inbox)

**Owned by:** Platform team
**Speed:** Tens of seconds per test, run on PRs that touch protocol or registry

This is the layer most teams skip and then regret. Stand up **two or three** inboxes, each with their own keypair, in their own processes (or as pods in a kind cluster, or via docker-compose). Have them talk to each other.

Scenarios to cover:

- **A → B happy path.** A signs, B verifies, B's executor runs, A receives receipt.
- **A → B → C chained.** B's executor sends a follow-up envelope to C as part of handling A's request. Verify the conversation_id threading works and all three receipts are linked.
- **A → B with B's pubkey rotated mid-flight.** A is sending steady traffic. B rotates its pubkey. Verify A picks up the new pubkey from the registry within the propagation SLA and traffic recovers without manual intervention.
- **A → B with A revoked mid-flight.** B's trust registry removes A. Verify in-flight envelopes already past step 5 still complete; new envelopes from A get `403 untrusted_sender` within the SLA.
- **A → B with clock skew.** A's clock is 30s ahead of B's. Verify envelopes within tolerance succeed; envelopes outside tolerance fail with the right error code.
- **A → B with B down.** A retries. When B comes back, verify exactly-once semantics — the retried envelope is not re-executed if B already processed it before crashing.
- **A → B under sustained load.** Run 1000 envelopes/sec for 60s. Verify p99 latency stays under SLO and no envelopes are silently dropped.

These tests catch the bugs that no amount of unit testing will find: registry propagation race conditions, retry storms, partial-failure semantics.

### Layer 6 — Security and abuse tests

**Owned by:** Platform team + security team
**Speed:** Variable; run nightly and before any protocol change

This layer asks "what does an attacker see?" Frame each test as a specific attacker capability.

Mandatory tests:

- **Replay attack.** Capture a legitimate envelope; resend it 1s later, 1m later, 1h later. The first replay must be rejected; the late replay must be rejected with the right error (expired, not nonce-replay).
- **Cross-recipient replay.** Take an envelope addressed to B and submit it to C. Must be rejected by C even though signature is valid — `recipient` field must be checked.
- **Field-tampering attack.** Modify the prompt, the scope, the timestamp, the conversation_id. Each must fail signature verification.
- **Pubkey-substitution attack.** Sender claims to be A (pubkey of A in the envelope) but signs with key A'. Must fail.
- **Trust-registry-bypass attack.** Direct DB write to add a sender. Verify the audit log captures it and an alert fires.
- **Scope-escalation attack.** Sender holds permission for `dining.rsvp`; sends envelope with scope `dining.cancel`. Must be denied at step 8.
- **Rate-limit-bypass attack.** Burst from one sender; verify token-bucket holds. Burst from many fake senders sharing the same source IP; verify per-sender limits hold even when source-IP limits do not exist (they shouldn't — sender pubkey is the unit, not IP).
- **Payload-injection attack.** Payloads designed to break the receiving LLM (prompt injection) — these are not protocol failures, but the test suite should *measure* what fraction of known injection patterns the `ChainExecutor` security wrapper catches before delivery to the model. Track this number over time.
- **Timing attack on signature verify.** Constant-time verify (which Ed25519 is). Test with a timing measurement that two failures take the same time regardless of where the bytes diverge.
- **Resource-exhaustion attack.** Submit envelope with maximum-allowed payload at maximum-allowed rate from maximum-allowed senders. Inbox must stay responsive and fail fast on the (N+1)th sender.

Wire these into your CI as a separate job that runs nightly, not on every PR — they are slower and a failure means "stop everything," not "block this PR."

### Layer 7 — Executor / model tests

**Owned by:** Each team
**Speed:** Variable; the team chooses

This is the layer the *receiving* team owns. The platform team should provide **harnesses**, not write the tests.

The platform team ships:

- A **golden envelope generator** — given a scope and a payload schema, produce N signed envelopes a team can replay against their own inbox in CI.
- A **conversation recorder** — run a team's inbox in a test fixture and capture envelope-in / receipt-out pairs. Use these as regression tests for the team's executor.
- An **LLM evaluation harness** — score the team's executor outputs on a per-scope rubric. This is the only place LLM non-determinism enters the test suite. Use a separate, slower CI job; do not block PRs on it; track the score over time.

What teams should test about their own executor:

- Given a well-formed envelope for a supported scope, the executor returns a structurally valid result.
- Given an envelope for an *unsupported* scope, the executor declines cleanly (does not pass the prompt to the model, returns a `scope_not_supported` result).
- Given a malformed `payload.context` (missing required field, wrong type), the executor declines cleanly.
- The executor's latency p95 is under whatever the team has committed to.
- The executor does not log secrets, PII, or full prompts at INFO level.
- For high-stakes scopes (anything with side effects: bookings, refunds, messages to guests), the executor goes through the human-review path until explicitly switched to autonomous.

What teams should *not* try to test:

- The protocol itself. That's layer 1–6.
- Whether the LLM is "right." It isn't, reliably. Score it, don't assert on it.

---

## The pyramid, sized for this app

```
                        ┌─────────────────────┐
                        │  Layer 7: Executor  │   tens of tests, slow,
                        │   / model eval      │   non-blocking, per team
                        ├─────────────────────┤
                       │ Layer 6: Security/    │  ~50 tests, nightly
                       │ abuse                 │
                      ├──────────────────────── ┤
                      │ Layer 5: Multi-inbox   │  ~20 scenarios, on PR
                      │ mesh integration       │  if protocol changes
                     ├───────────────────────────┤
                     │ Layer 4: Single-inbox    │  ~50 tests, every PR
                     │ integration              │
                    ├─────────────────────────────┤
                    │ Layer 3: Adapter contract  │  ~30 tests × N backends
                    │ tests                      │  every PR
                   ├───────────────────────────────┤
                   │ Layer 2: Pipeline unit       │  ~100 tests
                   │ tests                        │  every commit
                  ├─────────────────────────────────┤
                  │ Layer 1: Crypto property tests │  ~20 properties
                  │                                │  every commit
                  └─────────────────────────────────┘
```

The shape is wider in the middle than a classic pyramid. That is deliberate — for a protocol-shaped app, the contract tests and pipeline tests are where bugs hide.

---

## Test data: the three fixture sets you need

1. **Static golden envelopes** (`tests/fixtures/golden_signed_envelopes.json`). Hand-curated, signed with checked-in test keys, version-controlled. Used by layer 1 to detect canonical-encoding drift. **Never auto-regenerated.**

2. **Generated envelopes** (`tests/factories/`). Programmatic envelope builders using `hypothesis` strategies and factory_boy. Used by layers 1–4. Regenerated every test run.

3. **Recorded real traffic** (`tests/fixtures/recorded/`). Anonymized envelope/receipt pairs captured from staging. Used by layer 5 and layer 7 as realistic load. Refreshed quarterly. **Must pass through a PII scrubber before being committed.**

---

## CI pipeline shape

A four-tier pipeline matches the test layer split:

| Tier | Triggers | Layers | Wall time budget | Blocking? |
|---|---|---|---|---|
| **Fast** | every commit, every PR | 1, 2 | < 60s | yes |
| **Standard** | every PR | 3, 4 | < 5 min | yes |
| **Mesh** | PRs touching `epp/`, `cli/`, or `docs/spec.md` | 5 | < 15 min | yes for those PRs |
| **Nightly** | scheduled + manual | 6, 7 | < 60 min | no, but pages on regression |

The Fast tier is the developer feedback loop. The Standard tier is the PR gate. The Mesh tier is the protocol-change gate. The Nightly tier is the security and quality watch.

---

## Coverage targets

Coverage is a weak proxy, but worth tracking:

- **`epp/crypto/`** — 100%. Non-negotiable. Anything less means a code path that handles signed bytes is untested.
- **`epp/inbox/processor.py`** — 100% branch coverage on the 10-step pipeline.
- **`epp/policy/`** — 95%+, with explicit tests for every error path.
- **`epp/models.py`** — 90%+, with property tests covering field validators.
- **`epp/executors/`** — 80%+ for built-in executors; team executors set their own bar.
- **`epp/transport/`** — 85%+, with both happy-path and connection-failure paths.

Fail the CI on coverage *regression*, not on absolute number. A PR that drops `epp/crypto/` from 100% to 99% blocks; a new module landing at 80% does not.

---

## What to deliberately NOT test

- **The LLM's wording.** Score it, don't assert on exact strings.
- **Wall-clock timing in unit tests.** Inject a clock; never `time.sleep`.
- **Network behavior in unit tests.** Use the in-memory executor and transport.
- **Backwards-compatibility with envelopes from "future" protocol versions.** Reject them at the parse step; that's the test.
- **Behavior of the underlying KMS / Redis / Postgres.** Those are AWS's / Redis Labs' / your DBA's tests. Test only your *integration* with them, via the contract suite.
- **Configuration files in production format.** Test the config loader; don't ship a copy of prod config to the test suite.

---

## Tooling stack

The opinionated default for this project:

| Concern | Tool |
|---|---|
| Test runner | `pytest` |
| Async tests | `pytest-asyncio` (already configured: `asyncio_mode = "auto"`) |
| Property testing | `hypothesis` |
| HTTP client for integration | `httpx.AsyncClient` against a real uvicorn process — not `TestClient` |
| Service containers | `testcontainers-python` (Redis, Postgres) |
| Mesh tests | docker-compose for local; `kind` cluster for CI |
| Coverage | `pytest-cov` with branch coverage |
| Mutation testing (quarterly) | `mutmut` against `epp/crypto/` and `epp/inbox/processor.py` |
| Load/perf | `locust` driving real inboxes; capture p50/p95/p99 |
| Static analysis | `mypy --strict` on `epp/` (already configured), `ruff` |
| Security linting | `bandit`, `pip-audit` |
| Secret scanning | `gitleaks` in CI |

Mutation testing is the quietly-most-valuable item in this list for the crypto and pipeline layers. If `mutmut` can mutate a line and your tests still pass, you have a coverage gap that line-coverage will not show you. Run it quarterly; treat survivors as bugs.

---

## A 30-day testing roadmap

If you're starting from the existing test suite and want to get to "production-ready for an enterprise mesh," here's the order:

**Week 1 — Foundation**
- Add `hypothesis` property tests for crypto round-trip and tamper detection (layer 1).
- Check in golden signed envelopes fixture.
- Add mutation testing job for `epp/crypto/`.

**Week 2 — Pipeline coverage**
- Add explicit failure-mode tests for each of the 10 pipeline steps (layer 2).
- Get `epp/inbox/processor.py` to 100% branch coverage.

**Week 3 — Contract tests**
- Define the `NonceRegistryContract`, `TrustRegistryContract`, `RateLimiterContract`, `ExecutorContract`, `TransportContract` test classes (layer 3).
- Run each existing implementation against them. Fix anything that doesn't pass.

**Week 4 — Mesh and security**
- Stand up a docker-compose two-inbox harness (layer 5).
- Implement the seven mesh scenarios listed above.
- Wire the layer 6 security tests into a nightly CI job.
- Document the layer 7 harness for receiving teams.

After day 30 you have a suite that catches protocol drift, validates every backend swap, exercises real cross-team semantics, and tells you when an attacker pattern stops being caught. That's the bar.
