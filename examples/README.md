# EPP Examples

This directory contains working examples demonstrating the External Prompt Protocol.

## Examples

### [full_demo/](full_demo/)

**Complete end-to-end demonstration** of EPP with:
- Key generation for multiple parties
- Trust registry configuration
- Running an inbox server
- Sending prompts from a coffee shop
- Sending app store rejection notices
- Viewing the queue

This is the best place to start. Follow the numbered scripts in order.

```bash
cd full_demo
python 1_setup.py           # Generate keys
python 2_configure_inbox.py  # Set up trust
python 3_run_inbox.py        # Start server (keep running)

# In another terminal:
python 4_coffee_shop_sends.py
python 5_app_store_sends.py
python 6_check_queue.py
```

### [solana_example.py](solana_example.py)

Demonstrates **blockchain-based transport** using Solana. No server required - envelopes are posted to the blockchain and recipients poll for them.

Best for: wearables, IoT devices, offline-first scenarios.

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
