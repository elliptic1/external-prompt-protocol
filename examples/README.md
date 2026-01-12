# EPP Examples

This directory contains working examples demonstrating the External Prompt Protocol.

## Examples

### [http_inbox_server/](http_inbox_server/)

**Run your own inbox server** that receives prompts via HTTP POST. Demonstrates:
- Key generation for inbox and multiple senders
- Trust registry with per-sender policies
- FastAPI inbox server with full verification pipeline
- Coffee shop sending promotional prompts
- App store sending rejection notices
- Queue viewer for accepted envelopes

Best for: always-on servers, home infrastructure, cloud deployments.

```bash
cd http_inbox_server
python 1_setup.py           # Generate keys
python 2_configure_inbox.py  # Set up trust
python 3_run_inbox.py        # Start server (keep running)

# In another terminal:
python 4_coffee_shop_sends.py
python 5_app_store_sends.py
python 6_check_queue.py
```

### [qr_code_solana/](qr_code_solana/)

**QR code consent + blockchain polling**. Vendor displays QR code at their venue, customer scans to grant trust, vendor posts to Solana, customer's AI polls later.

Demonstrates:
- QR code generation for trust invitations
- Customer scanning and adding vendor to trust registry
- Signed envelope creation and (simulated) blockchain posting
- Polling, verification, and queueing on customer's device

Best for: museums, retail stores, venues - anywhere you want serverless prompt delivery with explicit consent.

```bash
cd qr_code_solana
pip install qrcode[pil]           # For QR code generation
python 1_vendor_setup.py          # Generate keys + QR code
python 2_customer_scans.py        # Scan QR, add to registry
python 3_vendor_sends.py          # Create and "send" envelope
python 4_customer_polls.py        # Poll, verify, queue
```

### [solana_example.py](solana_example.py)

**Blockchain-based transport** using Solana. No server required - senders post envelopes to the blockchain and recipients poll for them.

Best for: wearables, mobile devices, intermittent connectivity, no-server scenarios.

```bash
# Requires: pip install external-prompt-protocol[solana]
python solana_example.py
```

## Quick Reference

### Creating Keys

```python
from epp.crypto.keys import KeyPair

keypair = KeyPair.generate()
print(keypair.public_key_hex())  # Share this
keypair.private_key_pem()        # Keep secret
```

### Signing an Envelope

```python
from epp.crypto.signing import sign_envelope, generate_nonce

signature = sign_envelope(
    keypair,
    version="1",
    envelope_id=str(uuid4()),
    sender=keypair.public_key_hex(),
    recipient=recipient_pubkey,
    timestamp=datetime.utcnow().isoformat() + "Z",
    expires_at=(datetime.utcnow() + timedelta(minutes=15)).isoformat() + "Z",
    nonce=generate_nonce(),
    scope="notifications",
    payload={"prompt": "Hello!", "context": {}, "metadata": {}},
)
```

### Sending via HTTP

```python
import httpx

response = httpx.post(
    "http://localhost:8000/epp/v1/submit",
    json=envelope,
)
```

### Sending via Solana

```python
from epp.transport.solana import SolanaTransport

transport = SolanaTransport(keypair_path="wallet.json")
await transport.send(envelope, recipient_solana_address)
```

## More Resources

- [Protocol Specification](../docs/spec.md)
- [Threat Model](../docs/threat-model.md)
- [Quick Start Guide](../docs/quickstart.md)
- [Solana Transport](../docs/solana-transport.md)
