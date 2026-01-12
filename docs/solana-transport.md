# EPP Solana Transport

Deliver EPP envelopes via Solana blockchain instead of HTTP. No server required.

## Why Blockchain?

The HTTP transport requires running an inbox server. For wearable devices or offline-first scenarios, blockchain offers:

- **No server** - Your device polls the chain when convenient
- **Async delivery** - Envelopes wait on-chain until you fetch them
- **Global reach** - Works anywhere with internet
- **Permanent record** - Envelopes persist indefinitely
- **Sender pays** - Recipients read for free

## Costs

| Action | Cost | Who Pays |
|--------|------|----------|
| Send envelope | ~0.000005 SOL (~$0.0002) | Sender |
| Receive/read | Free | - |

A store sending 10,000 prompts/day pays ~$2/day. Recipients pay nothing.

## Installation

```bash
pip install external-prompt-protocol[solana]
```

## How It Works

```
Sender                          Solana                        Recipient
   │                               │                              │
   │ Create & sign EPP envelope    │                              │
   │ Post as memo tx ──────────────▶ Stored on-chain              │
   │ (pays ~$0.0002)               │                              │
   │                               │    Poll for new txs ◀────────│
   │                               │─────────────────────▶ Verify & process
```

EPP envelopes are stored in Solana transaction memos. The recipient's Solana address is derived from their EPP public key (both use Ed25519).

## Sending Envelopes

```python
import asyncio
from epp.transport.solana import SolanaTransport, epp_pubkey_to_solana_address
from epp.models import Envelope

async def send():
    transport = SolanaTransport(
        rpc_url="https://api.mainnet-beta.solana.com",
        keypair_path="~/.config/solana/id.json",  # Sender's funded wallet
    )

    # envelope = ... (create and sign as usual)

    recipient_solana = epp_pubkey_to_solana_address(envelope.recipient)
    tx_sig = await transport.send(envelope, recipient_solana)

    print(f"Sent: https://explorer.solana.com/tx/{tx_sig}")
    await transport.close()

asyncio.run(send())
```

## Receiving Envelopes

```python
import asyncio
from epp.transport.solana import SolanaTransport

async def receive():
    transport = SolanaTransport(
        rpc_url="https://api.mainnet-beta.solana.com"
    )

    # Poll for envelopes addressed to your EPP pubkey
    my_pubkey = "a1b2c3d4..."  # Your 64-char hex EPP public key

    async for envelope in transport.receive(my_pubkey, limit=50):
        print(f"Received: {envelope.envelope_id}")
        print(f"From: {envelope.sender}")
        print(f"Prompt: {envelope.payload.prompt}")

        # Verify and apply policies locally
        # ...

    await transport.close()

asyncio.run(receive())
```

## Address Conversion

EPP and Solana both use Ed25519 keys. Convert between formats:

```python
from epp.transport.solana import epp_pubkey_to_solana_address

# EPP pubkey (64-char hex)
epp_pubkey = "a1b2c3d4e5f6..."

# Solana address (base58)
solana_addr = epp_pubkey_to_solana_address(epp_pubkey)
# "A1B2c3D4e5F6..."
```

## Wearable Device Flow

For a device on your body:

1. **Setup**: Generate EPP keypair, derive Solana address
2. **Trust**: Add trusted senders to local policy (stores, services)
3. **Poll**: When on WiFi, query Solana for new transactions to your address
4. **Filter**: Check memo prefix `{"epp":"1"` to identify EPP envelopes
5. **Verify**: Validate signature, check trust registry, apply policies
6. **Decide**: Local AI determines if/when to notify user

```python
# Pseudo-code for wearable background task
async def background_sync():
    transport = SolanaTransport()
    last_seen = load_last_signature()

    async for envelope in transport.receive(MY_PUBKEY, since=last_seen):
        if verify_and_check_policy(envelope):
            queue_for_ai(envelope)
        save_last_signature(envelope.tx_signature)
```

## Large Envelopes

Solana memos have practical limits (~1KB recommended). For larger payloads:

1. Store envelope on Arweave (~$0.003, permanent)
2. Post pointer to Solana:
   ```json
   {"epp":"1","loc":"ar://abc123","hash":"sha256:..."}
   ```
3. Recipient fetches full envelope from Arweave

## RPC Endpoints

| Network | URL | Use |
|---------|-----|-----|
| Mainnet | `https://api.mainnet-beta.solana.com` | Production |
| Devnet | `https://api.devnet.solana.com` | Testing |
| Testnet | `https://api.testnet.solana.com` | Testing |

For production, consider a dedicated RPC (QuickNode, Helius, etc.) for reliability.

## Security Considerations

- **On-chain data is public** - Anyone can see envelopes (but can't forge signatures)
- **Recipient privacy** - Your Solana address reveals you receive EPP prompts
- **Spam** - Rate limiting must be done locally (blockchain can't prevent sends)
- **Key management** - Protect sender's Solana keypair (has SOL for fees)

## Comparison: HTTP vs Solana

| | HTTP Transport | Solana Transport |
|--|----------------|------------------|
| Server required | Yes (inbox) | No |
| Always online | Yes | No (poll when convenient) |
| Delivery | Push (instant) | Pull (async) |
| Cost | Hosting fees | ~$0.0002/envelope |
| Offline support | No | Yes |
| Best for | Web services | Wearables, IoT |
