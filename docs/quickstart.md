# EPP Quickstart Guide

This guide will walk you through setting up and using the External Prompt Protocol reference implementation.

## Installation

### From Source

```bash
git clone https://github.com/yourusername/external-prompt-protocol.git
cd external-prompt-protocol
pip install -e ".[dev]"
```

### From PyPI (when available)

```bash
pip install external-prompt-protocol
```

## Quick Start

### 1. Generate Keys

First, generate key pairs for both the sender and recipient (inbox):

```bash
# Generate sender keys
eppctl keys generate --output sender

# Generate inbox keys
eppctl keys generate --output inbox
```

This creates:
- `sender.key` - Sender's private key
- `sender.pub` - Sender's public key
- `inbox.key` - Inbox's private key
- `inbox.pub` - Inbox's public key

### 2. Start the Inbox Server

Create a configuration file `.epp-inbox/config.yaml`:

```yaml
inbox:
  host: 0.0.0.0
  port: 8000
  data_dir: .epp-inbox/data

keys:
  private_key_path: inbox.key
  public_key_path: inbox.pub

storage:
  trust_registry: .epp-inbox/data/trust_registry.json

executor:
  type: file_queue
  queue_dir: .epp-inbox/data/queue
```

Start the inbox server:

```bash
epp-inbox --config .epp-inbox/config.yaml
```

The server will display:
```
Starting EPP Inbox on 0.0.0.0:8000
Inbox public key: a1b2c3d4...
Submit endpoint: http://0.0.0.0:8000/epp/v1/submit
```

### 3. Add Trusted Sender

Add the sender's public key to the inbox's trust registry:

```bash
# Read sender's public key
SENDER_KEY=$(cat sender.pub)

# Add to trust registry
eppctl trust add \
  --registry .epp-inbox/data/trust_registry.json \
  --public-key "$SENDER_KEY" \
  --name "My Trusted Sender" \
  --scopes "notifications,support" \
  --max-per-hour 100 \
  --max-per-day 1000
```

### 4. Create and Send an Envelope

Create an envelope:

```bash
# Get recipient's public key
RECIPIENT_KEY=$(cat inbox.pub)

# Create envelope
eppctl envelope create \
  --private-key sender.key \
  --recipient "$RECIPIENT_KEY" \
  --scope notifications \
  --prompt "Hello from EPP! This is a test notification." \
  --expires 15 \
  --output envelope.json
```

Send the envelope to the inbox:

```bash
eppctl envelope send envelope.json http://localhost:8000
```

If successful, you'll see:
```
✓ Envelope accepted
  Receipt ID: 550e8400-e29b-41d4-a716-446655440000
  Executor: file_queue
```

### 5. Check the Queue

The file queue executor writes envelopes to files:

```bash
ls -la .epp-inbox/data/queue/
cat .epp-inbox/data/queue/*.json
```

## Common Scenarios

### Scenario 1: Local Development

**Goal**: Test EPP locally without network.

1. Generate keys for sender and inbox
2. Start inbox with `file_queue` executor
3. Add sender to trust registry
4. Create and send envelopes locally

### Scenario 2: Remote Submission

**Goal**: Send prompts from a remote service to your AI.

**On the AI host (recipient):**
```bash
# Start inbox with public endpoint
epp-inbox --config config.yaml
```

**On the sender:**
```bash
# Create envelope
eppctl envelope create \
  --private-key my-service.key \
  --recipient <INBOX_PUBLIC_KEY> \
  --scope code-review \
  --prompt "Review this PR: https://github.com/..." \
  --output envelope.json

# Send to remote inbox
eppctl envelope send envelope.json https://ai.example.com/epp/v1/submit
```

### Scenario 3: App Store Rejection Notice

**Goal**: App store delivers signed rejection notice to developer's AI.

**App Store (sender):**
```bash
eppctl envelope create \
  --private-key appstore.key \
  --recipient <DEVELOPER_INBOX_KEY> \
  --scope app-review \
  --prompt "Your app was rejected. Reason: Missing privacy policy." \
  --context context.json \
  --output rejection.json

eppctl envelope send rejection.json https://dev.example.com/epp/v1/submit
```

**Developer's Inbox:**
- Verifies signature from app store
- Checks trust registry
- Forwards to AI for analysis
- AI suggests fixes

## Configuration Options

### Executor Types

**NoOp Executor** (testing):
```yaml
executor:
  type: noop
```

**File Queue Executor** (default):
```yaml
executor:
  type: file_queue
  queue_dir: .epp-inbox/data/queue
```

**Logger Executor**:
```yaml
executor:
  type: logger
  log_file: .epp-inbox/data/envelopes.log
```

### Trust Registry Policies

**Wildcard scopes** (allow all):
```bash
eppctl trust add --scopes "*" ...
```

**Specific scopes**:
```bash
eppctl trust add --scopes "notifications,support,code-review" ...
```

**No rate limits**:
```bash
eppctl trust add --name "Unlimited Sender" ...
# (omit --max-per-hour and --max-per-day)
```

**Strict limits**:
```bash
eppctl trust add \
  --max-per-hour 10 \
  --max-per-day 50 \
  --max-size 100000 \
  ...
```

## Programmatic Usage

### Python API

```python
from epp.crypto.keys import KeyPair
from epp.crypto.signing import sign_envelope, generate_nonce
from epp.models import Envelope, Payload
from datetime import datetime, timedelta
from uuid import uuid4
import httpx

# Generate or load keys
sender_key = KeyPair.generate()
recipient_key_hex = "a1b2c3d4..."  # Inbox public key

# Create envelope
envelope_id = str(uuid4())
timestamp = datetime.utcnow().isoformat() + "Z"
expires_at = (datetime.utcnow() + timedelta(minutes=15)).isoformat() + "Z"
nonce = generate_nonce()

payload = Payload(
    prompt="Test prompt from Python",
    context={"key": "value"}
)

signature = sign_envelope(
    sender_key,
    version="1",
    envelope_id=envelope_id,
    sender=sender_key.public_key_hex(),
    recipient=recipient_key_hex,
    timestamp=timestamp,
    expires_at=expires_at,
    nonce=nonce,
    scope="test",
    payload=payload.model_dump(exclude_none=True)
)

envelope_dict = {
    "version": "1",
    "envelope_id": envelope_id,
    "sender": sender_key.public_key_hex(),
    "recipient": recipient_key_hex,
    "timestamp": timestamp,
    "expires_at": expires_at,
    "nonce": nonce,
    "scope": "test",
    "payload": payload.model_dump(exclude_none=True),
    "signature": signature
}

# Send envelope
response = httpx.post(
    "http://localhost:8000/epp/v1/submit",
    json=envelope_dict,
    timeout=30
)

receipt = response.json()
print(f"Status: {receipt['status']}")
```

## Troubleshooting

### "INVALID_SIGNATURE" Error

**Cause**: Signature verification failed.

**Solutions**:
- Ensure you're using the correct private key
- Verify sender's public key matches the one in the envelope
- Check that envelope data hasn't been modified

### "UNTRUSTED_SENDER" Error

**Cause**: Sender not in trust registry.

**Solutions**:
```bash
# Check trust registry
eppctl trust list --registry .epp-inbox/data/trust_registry.json

# Add sender
eppctl trust add --public-key <KEY> --name "Sender Name" ...
```

### "RATE_LIMITED" Error

**Cause**: Exceeded rate limits.

**Solutions**:
- Wait for rate limit window to reset
- Increase limits in trust registry
- Remove and re-add sender with higher limits

### "EXPIRED" Error

**Cause**: Envelope has expired.

**Solutions**:
- Create a new envelope with fresh timestamp
- Use longer expiration time (--expires option)

### Connection Refused

**Cause**: Inbox server not running or wrong address.

**Solutions**:
```bash
# Check if server is running
curl http://localhost:8000/health

# Start server
epp-inbox --config .epp-inbox/config.yaml
```

## Next Steps

- Read the [Protocol Specification](spec.md) for technical details
- Review [Threat Model](threat-model.md) for security considerations
- Explore [Examples](../examples/) for more use cases
- Implement custom executors for your use case

## Support

- GitHub Issues: https://github.com/yourusername/external-prompt-protocol/issues
- Documentation: https://github.com/yourusername/external-prompt-protocol/docs
