#!/usr/bin/env python3
"""
EPP on Solana - Example of blockchain-based prompt delivery.

This example shows how to:
1. Send EPP envelopes via Solana transactions
2. Receive envelopes by polling the chain
3. No server required - just read from the blockchain

Requirements:
    pip install external-prompt-protocol[solana]

Costs:
    - Send: ~0.000005 SOL (~$0.0002 USD) per envelope
    - Receive: Free (read-only RPC calls)
"""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from epp.crypto.keys import KeyPair
from epp.crypto.signing import sign_envelope, generate_nonce
from epp.models import Envelope, Payload
from epp.transport.solana import SolanaTransport, epp_pubkey_to_solana_address


async def main():
    # === SETUP ===

    # Generate EPP keys for sender and recipient
    sender_keys = KeyPair.generate()
    recipient_keys = KeyPair.generate()

    print("=== EPP on Solana Demo ===\n")
    print(f"Sender EPP pubkey:    {sender_keys.public_key_hex()}")
    print(f"Recipient EPP pubkey: {recipient_keys.public_key_hex()}")

    # Convert EPP pubkey to Solana address
    recipient_solana = epp_pubkey_to_solana_address(recipient_keys.public_key_hex())
    print(f"Recipient Solana:     {recipient_solana}")

    # === CREATE ENVELOPE ===

    envelope_id = str(uuid4())
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat().replace("+00:00", "Z")
    nonce = generate_nonce()

    payload = Payload(
        prompt="The coffee shop next door has your usual ready. 20% off today.",
        context={
            "store": "Bean Counter Coffee",
            "offer_id": "LOYAL-2025-001",
            "valid_until": expires_at,
        },
        metadata={
            "category": "retail-offer",
            "priority": "low",
        }
    )

    # Sign the envelope
    signature = sign_envelope(
        sender_keys,
        version="1",
        envelope_id=envelope_id,
        sender=sender_keys.public_key_hex(),
        recipient=recipient_keys.public_key_hex(),
        timestamp=timestamp,
        expires_at=expires_at,
        nonce=nonce,
        scope="retail-notifications",
        payload=payload.model_dump(exclude_none=True),
    )

    envelope = Envelope(
        version="1",
        envelope_id=envelope_id,
        sender=sender_keys.public_key_hex(),
        recipient=recipient_keys.public_key_hex(),
        timestamp=timestamp,
        expires_at=expires_at,
        nonce=nonce,
        scope="retail-notifications",
        payload=payload,
        signature=signature,
    )

    print(f"\n=== Created Envelope ===")
    print(f"ID: {envelope.envelope_id}")
    print(f"Scope: {envelope.scope}")
    print(f"Prompt: {envelope.payload.prompt[:50]}...")
    print(f"Size: {envelope.size_bytes()} bytes")

    # === SEND VIA SOLANA ===

    print("\n=== Sending via Solana ===")
    print("(In production, this would post to Solana mainnet)")
    print("(Sender pays ~$0.0002, recipient reads for free)")

    # To actually send, you'd need a funded Solana wallet:
    #
    # transport = SolanaTransport(
    #     rpc_url="https://api.mainnet-beta.solana.com",
    #     keypair_path="~/.config/solana/id.json"
    # )
    # tx_sig = await transport.send(envelope, recipient_solana)
    # print(f"Transaction: https://explorer.solana.com/tx/{tx_sig}")

    # === RECEIVE (POLL) ===

    print("\n=== Receiving (Polling Solana) ===")
    print("(Wearable device would do this periodically)")

    # To receive envelopes addressed to you:
    #
    # transport = SolanaTransport(rpc_url="https://api.mainnet-beta.solana.com")
    # async for env in transport.receive(recipient_keys.public_key_hex()):
    #     print(f"Received: {env.envelope_id}")
    #     print(f"From: {env.sender[:16]}...")
    #     print(f"Prompt: {env.payload.prompt}")
    #
    #     # Verify signature and apply policies locally
    #     # Then decide whether to tell the user

    print("\n=== Flow Summary ===")
    print("""
    1. Store signs envelope with their EPP key
    2. Store posts to Solana (pays ~$0.0002)
    3. Your wearable polls Solana when on WiFi (free)
    4. Local AI verifies signature, checks trust registry
    5. AI decides: "Tell user about coffee deal? It's nearby and relevant."
    6. AI whispers in your ear: "Coffee shop has your usual ready, 20% off"
    """)


if __name__ == "__main__":
    asyncio.run(main())
