# QR Code + Solana Polling Example

This example demonstrates the **serverless EPP pattern**: vendors deliver prompts to customer AIs without anyone running a server.

## The Scenario

You're visiting the **Natural History Museum**. At the entrance, there's a sign:

```
┌─────────────────────────────────────────┐
│                                         │
│   Enhance your visit with AI guidance   │
│                                         │
│   Scan to let our AI send exhibit       │
│   information to your personal AI:      │
│                                         │
│         ┌───────────────┐               │
│         │ ▄▄▄▄▄ ▄▄▄▄▄  │               │
│         │ █   █ █▄▄▄█  │               │
│         │ █▄▄▄█ █   █  │               │
│         │ ▄▄▄▄▄ █▄▄▄█  │               │
│         │ █   █ ▄▄▄▄▄  │               │
│         └───────────────┘               │
│                                         │
│   Your AI decides what to tell you.     │
│   Revoke access anytime.                │
│                                         │
└─────────────────────────────────────────┘
```

When you scan:
1. Your phone parses the QR code
2. Museum is added to your AI's trust registry
3. You continue your visit

Later, while you're looking at the T-Rex exhibit, the museum posts a prompt to Solana. Your AI (running on your wearable/phone) polls Solana, finds the message, verifies the signature, and whispers:

> "The T-Rex skeleton you're looking at is actually a cast. The real bones are too heavy to mount. Want me to tell you about the casting process?"

## Why No Server?

The **http_inbox_server** example requires running a FastAPI server 24/7. That's fine for home servers or cloud deployments. But what if:

- You're wearing smart glasses with intermittent connectivity?
- Your AI runs on a phone that's often offline?
- You don't want to manage infrastructure?

**Solana solves this:**
- Vendor posts message to blockchain (~$0.0002)
- Your device polls when convenient (free to read)
- Messages persist until you fetch them
- No server required on either side

## The Flow

```
┌─────────────┐                              ┌─────────────┐
│   MUSEUM    │                              │  CUSTOMER   │
│   (Vendor)  │                              │  (Your AI)  │
└──────┬──────┘                              └──────┬──────┘
       │                                            │
       │  1. Generate keys                          │
       │  2. Create QR code                         │
       ▼                                            │
   [QR Code displayed]                              │
       │                                            │
       │◄──────── 3. Customer scans ───────────────┤
       │                                            │
       │                                            ▼
       │                              4. Add museum to trust registry
       │                                            │
       │  5. Post prompt to Solana                  │
       │─────────────────────────────────►          │
       │                              ┌─────────────┴─────────────┐
       │                              │       SOLANA              │
       │                              │    (Blockchain)           │
       │                              └─────────────┬─────────────┘
       │                                            │
       │                              6. Poll for messages
       │                              7. Verify signature
       │                              8. Check trust registry
       │                              9. Queue for AI
       │                                            ▼
       │                              [Your AI processes prompt]
```

## Running the Example

### Prerequisites

```bash
pip install external-prompt-protocol
pip install qrcode[pil]  # For QR code generation
```

### Step 1: Museum Sets Up (Vendor Side)

```bash
python 1_vendor_setup.py
```

This generates:
- Museum's keypair (`keys/museum.key`, `keys/museum.pub`)
- QR code image (`data/museum_qr.png`)
- QR payload JSON (`data/qr_payload.json`)

### Step 2: Customer Scans QR

```bash
python 2_customer_scans.py
```

This simulates scanning the QR code:
- Parses the QR payload
- Adds museum to customer's trust registry
- Shows granted permissions

### Step 3: Museum Sends Prompt (Simulated)

```bash
python 3_vendor_sends.py
```

This creates and signs an envelope:
- Loads museum's private key
- Creates exhibit info prompt
- Signs with Ed25519
- **Simulated**: Saves to file (real version posts to Solana)

### Step 4: Customer Polls (Simulated)

```bash
python 4_customer_polls.py
```

This simulates polling Solana:
- **Simulated**: Reads envelope from file
- Verifies cryptographic signature
- Checks trust registry
- Applies rate limits
- Queues for AI processing

## What's Simulated?

To avoid requiring Solana devnet SOL and actual blockchain transactions, this example:

- **Simulates sending**: Saves envelope to `data/blockchain_sim/` instead of posting to Solana
- **Simulates polling**: Reads from that directory instead of querying Solana RPC

The **actual Solana code** is included but commented out. To run for real:

1. Get devnet SOL: `solana airdrop 1 --url devnet`
2. Uncomment the Solana transport code in scripts 3 and 4
3. Install Solana deps: `pip install external-prompt-protocol[solana]`

## QR Code Format

The QR code encodes a **trust invitation**:

```json
{
  "epp": "1",
  "type": "trust_invitation",
  "vendor": {
    "name": "Natural History Museum",
    "public_key": "a1b2c3d4e5f6...",
    "solana_address": "ABC123xyz..."
  },
  "policy": {
    "scopes": ["exhibits", "tours", "events"],
    "max_envelope_size": 10240,
    "max_per_hour": 10,
    "max_per_day": 50
  },
  "invitation_expires": "2024-12-31T23:59:59Z"
}
```

Key fields:
- **vendor.public_key**: Used to verify signatures
- **vendor.solana_address**: Where to poll for messages
- **policy**: What the vendor is allowed to do (customer can modify)
- **invitation_expires**: QR codes should have limited validity

## Security Notes

1. **QR codes are consent, not authentication**: Scanning grants trust, but the vendor must still sign messages with their private key.

2. **Customer controls policy**: The QR suggests a policy, but the customer can modify it (reduce scopes, lower rate limits) before accepting.

3. **Revocation**: Customer can remove the vendor from their trust registry at any time.

4. **Signature verification**: Every message is verified against the public key from the QR code. A fake QR with a different public key can't impersonate the real vendor.

## Real-World Considerations

**For vendors:**
- Generate keys securely, store private key safely
- Rotate QR codes periodically (new invitation_expires)
- Monitor Solana costs (~$0.0002 per message)

**For customers:**
- Review policies before accepting
- Periodically audit trust registry
- Set up automatic expiration for temporary trusts

## Files

| File | Description |
|------|-------------|
| `1_vendor_setup.py` | Generate keys and QR code |
| `2_customer_scans.py` | Parse QR, add to trust registry |
| `3_vendor_sends.py` | Create, sign, "send" envelope |
| `4_customer_polls.py` | "Poll", verify, queue envelope |
| `keys/` | Generated keypairs (gitignored) |
| `data/` | QR codes, registry, queue (gitignored) |
