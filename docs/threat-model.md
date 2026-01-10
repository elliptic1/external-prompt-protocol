# EPP Threat Model and Security Considerations

## Overview

This document analyzes the security properties, attack vectors, and mitigations for the External Prompt Protocol (EPP).

## Security Goals

1. **Authentication**: Verify the identity of prompt senders
2. **Authorization**: Ensure only trusted senders can deliver prompts
3. **Integrity**: Detect tampering with envelopes in transit
4. **Replay Protection**: Prevent reuse of captured envelopes
5. **Consent**: Enforce user control over what prompts are accepted
6. **Availability**: Prevent denial-of-service attacks on the inbox

## Threat Actors

### Untrusted External Sender
- **Goal**: Deliver unauthorized prompts to the user's AI
- **Capability**: Can send HTTP requests, observe network traffic
- **Mitigation**: Trust registry + signature verification

### Compromised Sender
- **Goal**: Abuse legitimate access to send malicious prompts
- **Capability**: Has valid private key for a trusted sender
- **Mitigation**: Scope restrictions, rate limits, revocation capability

### Network Attacker
- **Goal**: Intercept or modify envelopes in transit
- **Capability**: Man-in-the-middle, packet injection
- **Mitigation**: End-to-end signatures (independent of transport), HTTPS recommended

### Malicious Recipient Claim
- **Goal**: Process envelopes intended for another user
- **Capability**: Runs an inbox, attempts to accept arbitrary envelopes
- **Mitigation**: Recipient field verification, signatures bind to specific recipient

## Attack Vectors and Mitigations

### 1. Impersonation Attack

**Attack**: Attacker sends envelope claiming to be from trusted sender without valid signature.

**Mitigation**:
- All envelopes MUST be cryptographically signed
- Signature verification MUST occur before any processing
- Reject unsigned or incorrectly signed envelopes immediately
- Log failed signature attempts for monitoring

**Status**: ✅ Mitigated by design

### 2. Replay Attack

**Attack**: Attacker captures a valid envelope and re-sends it multiple times.

**Mitigation**:
- Require unique nonce in every envelope
- Maintain nonce registry with expiration tracking
- Reject any envelope with previously seen nonce
- Enforce strict expiration times
- Garbage collect expired nonces

**Implementation Requirements**:
```python
# Pseudo-code
if nonce_registry.has_seen(envelope.nonce):
    reject("REPLAY_DETECTED")
if current_time > envelope.expires_at:
    reject("EXPIRED")
nonce_registry.add(envelope.nonce, envelope.expires_at)
```

**Status**: ✅ Mitigated by nonce + expiration

### 3. Unauthorized Sender

**Attack**: Attacker with their own valid key pair tries to send prompts.

**Mitigation**:
- Maintain explicit trust registry
- Only accept envelopes from known, trusted sender keys
- Require manual trust addition (no auto-trust)
- Reject unknown senders immediately

**Status**: ✅ Mitigated by trust registry

### 4. Scope Escalation

**Attack**: Trusted sender sends envelope with scope they're not authorized for.

**Mitigation**:
- Define allowed scopes per sender in policy
- Reject envelopes with disallowed scopes
- Log scope violations for monitoring
- Use allowlist approach (deny by default)

**Example**:
```json
{
  "sender": "pubkey-abc123",
  "policy": {
    "allowed_scopes": ["notifications", "support"]
    // "code-execution" not allowed
  }
}
```

**Status**: ✅ Mitigated by policy enforcement

### 5. Resource Exhaustion (DoS)

**Attack Vectors**:

a) **Large Envelope Flood**: Send massive envelopes to exhaust storage/memory
   - **Mitigation**: Enforce maximum envelope size per sender
   - **Implementation**: Check size before parsing

b) **High-Frequency Requests**: Send envelopes at extreme rate
   - **Mitigation**: Rate limiting per sender
   - **Implementation**: Token bucket or sliding window

c) **Signature Verification DoS**: Send invalid envelopes to burn CPU
   - **Mitigation**: Early format validation, rate limit invalid attempts
   - **Implementation**: Validate JSON structure before crypto operations

d) **Nonce Registry Bloat**: Send unique envelopes to bloat nonce storage
   - **Mitigation**: Enforce short expiration times, aggressive GC
   - **Implementation**: Periodic cleanup of expired nonces

**Status**: ⚠️ Requires careful implementation

### 6. Prompt Injection

**Attack**: Attacker (even trusted sender) crafts prompt to manipulate AI behavior.

**Mitigation Options**:
- This is largely outside EPP's scope (EPP verifies *who*, not *what*)
- Executors SHOULD implement prompt sanitization
- Users SHOULD carefully vet trusted senders
- Consider scope-based prompt templates
- Log all prompts for audit

**Status**: ⚠️ Partial - requires executor-level defenses

### 7. Signature Algorithm Weakness

**Attack**: Exploit cryptographic vulnerabilities in signature scheme.

**Mitigation**:
- Use well-vetted algorithms (Ed25519 recommended)
- Support algorithm agility for future upgrades
- Monitor for cryptographic breaks
- Version field allows protocol evolution

**Status**: ✅ Mitigated by algorithm choice

### 8. Time-Based Attacks

**Attack Vectors**:

a) **Clock Skew Exploitation**: Use incorrect clocks to bypass expiration
   - **Mitigation**: Inbox uses own clock, rejects if current_time > expires_at
   - **Best Practice**: Senders use short expiration windows (minutes, not days)

b) **Timestamp Manipulation**: Backdating or future-dating envelopes
   - **Mitigation**: Timestamps are signed, cannot be altered
   - **Additional**: Consider rejecting timestamps too far in past/future

**Status**: ✅ Mitigated by signature + local clock enforcement

### 9. Key Compromise

**Attack**: Sender's private key is stolen.

**Mitigation**:
- Key rotation capability (though not specified in v1)
- Revocation mechanism (remove from trust registry)
- Scope and rate limits contain blast radius
- Monitor for unusual activity
- Encourage hardware key storage

**Incident Response**:
1. Remove sender from trust registry immediately
2. Audit recent envelopes from compromised sender
3. Notify user of compromise
4. Sender generates new key pair

**Status**: ✅ Mitigated by revocation (manual in v1)

### 10. Trust Registry Tampering

**Attack**: Attacker modifies trust registry to add malicious senders.

**Mitigation**:
- File system permissions (only inbox process can write)
- Integrity monitoring (detect unauthorized changes)
- Audit logging of trust additions/removals
- Consider signing trust registry itself (future)

**Status**: ⚠️ Depends on deployment security

### 11. Side-Channel Attacks

**Attack Vectors**:

a) **Timing Attacks**: Infer information from signature verification time
   - **Mitigation**: Use constant-time crypto libraries

b) **Traffic Analysis**: Infer activity from envelope frequency/size
   - **Mitigation**: Outside EPP scope; use TLS, consider dummy traffic

**Status**: ⚠️ Cryptographic library dependent

### 12. Metadata Leakage

**Attack**: Infer private information from envelope metadata.

**Observation**:
- Sender, recipient, scope, timestamp are not encrypted
- Envelopes are signed, not sealed

**Mitigations**:
- Use HTTPS transport for confidentiality
- Consider envelope encryption in future versions (not v1)
- Be mindful of sensitive data in scope identifiers

**Status**: ⚠️ Transport encryption recommended

## Security Best Practices

### For Inbox Operators (Users)

1. **Trust Carefully**: Only add senders you genuinely trust
2. **Scope Minimally**: Grant minimum necessary scopes
3. **Rate Limit Aggressively**: Start with conservative limits
4. **Monitor Logs**: Watch for unusual patterns
5. **Keep Keys Secure**: Protect inbox private key
6. **Update Regularly**: Apply security patches
7. **Use HTTPS**: Always use TLS for HTTP transport
8. **Isolate Executor**: Run executors in sandboxed environments

### For Senders

1. **Protect Private Keys**: Use hardware security modules when possible
2. **Short Expirations**: Use minimal expiration windows (5-15 minutes)
3. **Unique Nonces**: Always generate cryptographically random nonces
4. **Audit Prompts**: Review prompts for injection risks
5. **Monitor Rejections**: Watch for policy violations
6. **Respect Policies**: Honor rate limits and scope restrictions

### For Implementers

1. **Validate Early**: Check sizes and formats before expensive operations
2. **Constant-Time Crypto**: Use constant-time signature verification
3. **Secure Defaults**: Deny by default, allow by exception
4. **Defense in Depth**: Multiple layers of validation
5. **Audit Logging**: Log all security-relevant events
6. **Fail Closed**: Reject on any validation error
7. **Resource Limits**: Enforce timeouts, memory limits, connection limits

## Security Checklist for Implementations

- [ ] Signature verification before any processing
- [ ] Nonce registry with expiration tracking
- [ ] Trust registry enforcement
- [ ] Scope-based policy enforcement
- [ ] Rate limiting per sender
- [ ] Maximum envelope size limits
- [ ] Expiration time enforcement
- [ ] Recipient verification
- [ ] Input validation (JSON structure, field formats)
- [ ] Audit logging (accepted, rejected, errors)
- [ ] Secure key storage
- [ ] HTTPS transport support
- [ ] Error handling without information leakage
- [ ] Resource limits (memory, CPU, disk)
- [ ] Graceful degradation under load

## Known Limitations (v1)

1. **No Encryption**: Envelopes are signed but not encrypted (use TLS)
2. **No Forward Secrecy**: Same keys used indefinitely
3. **No Delegation**: Trust is not transitive or delegatable
4. **Manual Revocation**: No automated key revocation mechanism
5. **Prompt Content**: EPP doesn't validate prompt safety
6. **No Reputation System**: Binary trust (yes/no), no scoring

## Future Enhancements

Potential security improvements for future versions:

- Envelope encryption (confidentiality)
- Automated key rotation and revocation
- Delegation and trust chains
- Reputation scoring
- Prompt content scanning
- Federated trust models
- Zero-knowledge proofs for privacy
- Quantum-resistant signatures

---

**Security is a shared responsibility between protocol designers, implementers, and operators.**
