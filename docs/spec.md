# External Prompt Protocol (EPP) v1 Specification

## Status

**Version:** 1.0-draft
**Status:** Experimental
**Last Updated:** 2026-01-10

## Abstract

External Prompt Protocol (EPP) defines a cryptographically authenticated, consent-based system for delivering external prompts and context to user-owned AI systems. EPP enables third parties to submit prompts to a user's AI only with explicit authorization, using asymmetric cryptography for authentication and trust management.

## 1. Protocol Overview

### 1.1 Goals

- Enable cryptographically verified prompt delivery from trusted third parties
- Maintain user sovereignty over AI system interactions
- Provide model-agnostic, transport-agnostic message format
- Support fine-grained policy enforcement and consent management

### 1.2 Non-Goals (v1)

- Payment or gas fee mechanisms
- Blockchain or distributed ledger dependencies
- Anonymity guarantees
- Tool execution graph definitions
- Model-specific optimizations

## 2. Core Components

### 2.1 Entities

**User**: Controls an AI system and determines which external entities may deliver prompts.

**Sender**: External entity (person, service, agent, organization) that wishes to deliver prompts to a user's AI.

**Inbox**: User-controlled service that receives, verifies, and processes EPP envelopes.

**Executor**: Backend component that processes accepted prompts (may be model API, agent, file writer, etc.).

### 2.2 Trust Model

- Each sender is identified by a public key (Ed25519 recommended)
- Users maintain an explicit trust registry mapping sender identities to policies
- Only messages from trusted senders with valid signatures are processed
- Trust is not transitive or delegatable in v1

## 3. Message Format

### 3.1 EPP Envelope Structure

An EPP envelope is a JSON object containing:

```json
{
  "version": "1",
  "envelope_id": "<unique-identifier>",
  "sender": "<sender-public-key-hex>",
  "recipient": "<recipient-public-key-hex>",
  "timestamp": "<ISO-8601-UTC>",
  "expires_at": "<ISO-8601-UTC>",
  "nonce": "<base64-random-bytes>",
  "scope": "<scope-identifier>",
  "payload": {
    "prompt": "<text>",
    "context": {},
    "metadata": {},
    "payload_type": "<type-hint>"
  },
  "signature": "<base64-signature>",
  "conversation_id": "<uuid>",
  "in_reply_to": "<uuid>",
  "delegation": {
    "on_behalf_of": "<public-key-hex>",
    "authorization": "<optional-evidence>"
  }
}
```

### 3.2 Field Definitions

**version** (required, string): Protocol version. Must be "1" for this specification.

**envelope_id** (required, string): Globally unique identifier for this envelope. Format: UUID v4 recommended.

**sender** (required, string): Sender's public key in hexadecimal format.

**recipient** (required, string): Intended recipient's public key in hexadecimal format.

**timestamp** (required, string): Envelope creation time in ISO-8601 UTC format.

**expires_at** (required, string): Expiration time in ISO-8601 UTC format. Envelopes MUST be rejected after this time.

**nonce** (required, string): Cryptographically random bytes (minimum 16 bytes) encoded in base64. Used for replay protection.

**scope** (required, string): Scope identifier for policy matching (e.g., "support", "notifications", "code-review"). Alphanumeric and hyphens only.

**payload** (required, object): Contains the actual prompt and context.
  - **prompt** (required, string): The prompt text to be delivered.
  - **context** (optional, object): Structured context data (JSON).
  - **metadata** (optional, object): Additional metadata (JSON).
  - **payload_type** (optional, string): Type hint for payload schema (e.g., "order-request", "medical-record"). Alphanumeric and hyphens only.

**signature** (required, string): Cryptographic signature of the canonical envelope, base64-encoded.

**conversation_id** (optional, string): UUID linking envelopes in a multi-step exchange. All envelopes in the same conversation share this ID.

**in_reply_to** (optional, string): The `envelope_id` of the envelope being responded to. Used to chain request-response pairs within a conversation.

**delegation** (optional, object): Delegation info for acting on behalf of another entity.
  - **on_behalf_of** (required, string): Public key hex (64 characters) of the principal being represented.
  - **authorization** (optional, string): Evidence of delegation authority (e.g., signed token, reference ID).

### 3.3 Size Limits

Implementations SHOULD enforce reasonable size limits:
- Maximum envelope size: 10 MB (recommended default)
- Maximum prompt length: 1 MB (recommended default)
- Limits SHOULD be configurable per sender/scope

## 4. Cryptographic Operations

### 4.1 Key Generation

- Algorithm: Ed25519 (recommended)
- Alternative: ECDSA with P-256 or secp256k1 (permitted)
- Key format: Raw public keys encoded as hexadecimal

### 4.2 Canonical Signing Format

To create a signature:

1. Create a signing payload by serializing these 12 fields in order:
   ```
   version||envelope_id||sender||recipient||timestamp||expires_at||nonce||scope||conversation_id||in_reply_to||delegation_json||payload_json
   ```

2. Where:
   - `||` represents concatenation with a newline (`\n`) separator
   - Optional fields (`conversation_id`, `in_reply_to`, `delegation_json`) use an empty string when absent
   - `delegation_json` is compact sorted JSON of the delegation object when present, empty string when absent
   - `payload_json` is the compact JSON serialization of the payload object (no whitespace), always last

3. Compute signature:
   ```
   signature = sign(private_key, signing_payload)
   ```

4. Encode signature as base64

### 4.3 Signature Verification

To verify an envelope:

1. Extract all fields except `signature`
2. Reconstruct the canonical signing payload (as above)
3. Verify signature using sender's public key:
   ```
   verify(sender_public_key, signing_payload, signature)
   ```
4. Verification MUST fail if signature is invalid

## 5. Inbox Processing

### 5.1 Envelope Acceptance Flow

```
1. Receive envelope (HTTP POST, local file, message queue, etc.)
2. Parse and validate JSON structure
3. Check version compatibility
4. Verify recipient matches inbox public key
5. Check expiration (reject if expired)
6. Verify cryptographic signature
7. Check nonce for replay (reject if seen before)
8. Look up sender in trust registry (reject if unknown)
9. Apply policy for sender + scope
10. If accepted: store nonce, forward to executor, return receipt
11. If rejected: return error receipt
```

### 5.2 Validation Rules

An envelope MUST be rejected if:
- JSON structure is invalid
- Any required field is missing
- Version is not supported
- Recipient does not match inbox public key
- Current time > expires_at
- Signature verification fails
- Nonce has been seen before (replay)
- Sender is not in trust registry
- Policy denies the request (scope, rate limit, size, etc.)

### 5.3 Nonce Registry

Implementations MUST maintain a nonce registry to prevent replay attacks:
- Store nonces with their expiration times
- Reject envelopes with previously seen nonces
- Garbage collect expired nonces periodically

## 6. Trust Registry

### 6.1 Trust Entry Format

```json
{
  "public_key": "<hex-public-key>",
  "name": "<human-readable-name>",
  "added_at": "<ISO-8601-UTC>",
  "policy": {
    "allowed_scopes": ["scope1", "scope2", "*"],
    "max_envelope_size": 1048576,
    "rate_limit": {
      "max_per_hour": 100,
      "max_per_day": 1000
    }
  }
}
```

### 6.2 Policy Enforcement

Policies are evaluated per (sender, scope) tuple:
- **allowed_scopes**: List of permitted scope identifiers. "*" permits all scopes.
- **max_envelope_size**: Maximum allowed envelope size in bytes.
- **rate_limit**: Maximum number of accepted envelopes per time window.

## 7. Receipts

### 7.1 Success Receipt

```json
{
  "status": "accepted",
  "envelope_id": "<envelope-id>",
  "received_at": "<ISO-8601-UTC>",
  "receipt_id": "<unique-receipt-id>",
  "executor": "<executor-identifier>"
}
```

### 7.2 Error Receipt

```json
{
  "status": "rejected",
  "envelope_id": "<envelope-id>",
  "received_at": "<ISO-8601-UTC>",
  "error": {
    "code": "<error-code>",
    "message": "<human-readable-message>"
  }
}
```

### 7.3 Error Codes

- `INVALID_FORMAT`: JSON parsing or structure error
- `UNSUPPORTED_VERSION`: Protocol version not supported
- `WRONG_RECIPIENT`: Recipient does not match inbox
- `EXPIRED`: Envelope has expired
- `INVALID_SIGNATURE`: Signature verification failed
- `REPLAY_DETECTED`: Nonce has been seen before
- `UNTRUSTED_SENDER`: Sender not in trust registry
- `POLICY_DENIED`: Policy rejected the envelope
- `SIZE_EXCEEDED`: Envelope exceeds size limits
- `RATE_LIMITED`: Sender has exceeded rate limits

## 8. Transport

EPP is transport-agnostic. Recommended transport is HTTP(S).

### 8.1 HTTP Transport

**Endpoint:** User-defined (e.g., `https://user-inbox.example.com/epp/v1/submit`)

**Method:** POST

**Content-Type:** application/json

**Request Body:** EPP envelope JSON

**Response Codes:**
- 200 OK: Envelope accepted (includes success receipt)
- 400 Bad Request: Invalid envelope format
- 401 Unauthorized: Signature verification failed or untrusted sender
- 403 Forbidden: Policy denied
- 429 Too Many Requests: Rate limited
- 500 Internal Server Error: Inbox processing error

**Response Body:** Receipt JSON

### 8.2 Alternative Transports

EPP envelopes may be delivered via:
- Local files (watched directory)
- Message queues (RabbitMQ, Redis, etc.)
- Direct function calls (in-process)
- Email with S/MIME
- Any mechanism that can deliver the JSON envelope

## 9. Executors

Executors are pluggable backend processors for accepted prompts.

### 9.1 Executor Interface

```python
class Executor:
    def execute(self, envelope: Envelope) -> ExecutionResult:
        """Process an accepted envelope."""
        pass
```

### 9.2 Reference Executors

**NoOpExecutor**: Accepts and logs, no action.

**FileQueueExecutor**: Writes envelopes to a file queue for later processing.

**CommandExecutor**: Executes a shell command with prompt as input.

**ModelExecutor**: Forwards prompt to an LLM API.

**AgentExecutor**: Triggers an agent with the prompt.

## 10. Security Considerations

See `threat-model.md` for comprehensive security analysis.

Key points:
- Always verify signatures before any processing
- Enforce strict expiration times
- Implement robust replay protection
- Never trust envelopes from unknown senders
- Apply principle of least privilege in policies
- Log all accepted and rejected envelopes
- Consider rate limiting per sender
- Validate envelope sizes to prevent DoS

## 11. Extensibility

### 11.1 Custom Fields

Implementations MAY include additional fields in:
- `payload.metadata`
- `policy` objects
- Receipts

Custom fields SHOULD be prefixed with a namespace (e.g., `x-myorg-*`).

### 11.2 Future Versions

Breaking changes require a new version number. Implementations SHOULD reject envelopes with unsupported versions.

## 12. References

- Ed25519: RFC 8032
- ISO-8601: Date and time format
- JSON: RFC 8259
- UUID: RFC 4122

## 13. Conversation Patterns

EPP supports multi-step exchanges between AI systems through conversation threading, reply chaining, and delegation.

### 13.1 Conversation Threading

The `conversation_id` field links multiple envelopes into a single conversation. The initiator generates a UUID and sets it on the first envelope. All subsequent envelopes in the exchange use the same `conversation_id`.

### 13.2 Reply Chaining

The `in_reply_to` field references the `envelope_id` of the envelope being responded to, creating request-response pairs within a conversation. This enables:
- Correlating responses with their requests
- Building ordered conversation histories
- Detecting missing or out-of-order messages

### 13.3 Delegation

The `delegation` field allows a sender to act on behalf of another entity. The `on_behalf_of` field contains the public key of the principal, and `authorization` provides optional evidence of the delegation.

Delegation is cryptographically verified: the envelope is signed by the sender (the delegate), not the principal. The recipient's trust policy determines whether to accept delegated messages.

### 13.4 Medical Network Example

A multi-party medical scenario using conversation threading and delegation:

1. **Doctor → Patient**: Doctor sends lab results to patient's AI (new `conversation_id`)
2. **Patient → Wife**: Patient's AI forwards results to wife's AI (same `conversation_id`, `in_reply_to` references step 1)
3. **Doctor → Cardiologist**: Doctor sends referral on patient's behalf (new `conversation_id`, `delegation.on_behalf_of` = patient's public key)

Trust chains: Patient trusts doctor and wife. Doctor trusts cardiologist. Each party maintains their own trust registry.

### 13.5 Commerce Example

A restaurant ordering flow using conversation threading and typed payloads:

1. **Customer → Restaurant**: Menu query (`payload_type: "menu-query"`, new `conversation_id`)
2. **Restaurant → Customer**: Menu response (`payload_type: "menu-response"`, `in_reply_to` = step 1)
3. **Customer → Restaurant**: Order request (`payload_type: "order-request"`, `in_reply_to` = step 2)
4. **Restaurant → Customer**: Order confirmation (`payload_type: "order-confirmation"`, `in_reply_to` = step 3)

All four envelopes share the same `conversation_id`. The `payload_type` field enables AI systems to route and process messages based on their semantic type.

---

**End of Specification**
