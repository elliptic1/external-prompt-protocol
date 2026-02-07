#!/usr/bin/env python3
"""
Basic EPP example: Create and send an envelope.

This example demonstrates:
1. Generating key pairs
2. Creating a signed envelope
3. Sending it to an inbox (simulated)
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from epp.crypto.keys import KeyPair
from epp.crypto.signing import generate_nonce, sign_envelope
from epp.models import Envelope, Payload


def main():
    print("EPP Basic Example")
    print("=" * 50)

    # Step 1: Generate keys
    print("\n1. Generating key pairs...")
    sender_key = KeyPair.generate()
    recipient_key = KeyPair.generate()

    print(f"   Sender public key: {sender_key.public_key_hex()[:32]}...")
    print(f"   Recipient public key: {recipient_key.public_key_hex()[:32]}...")

    # Step 2: Create envelope
    print("\n2. Creating envelope...")
    envelope_id = str(uuid4())
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat().replace("+00:00", "Z")
    nonce = generate_nonce()

    payload = Payload(
        prompt="Hello from EPP! This is a test message.",
        context={"source": "basic_example.py", "version": "1.0"},
        metadata={"priority": "low"},
    )

    print(f"   Envelope ID: {envelope_id}")
    print(f"   Scope: test")
    print(f"   Prompt: {payload.prompt}")

    # Step 3: Sign envelope
    print("\n3. Signing envelope...")
    signature = sign_envelope(
        sender_key,
        version="1",
        envelope_id=envelope_id,
        sender=sender_key.public_key_hex(),
        recipient=recipient_key.public_key_hex(),
        timestamp=timestamp,
        expires_at=expires_at,
        nonce=nonce,
        scope="test",
        payload=payload.model_dump(exclude_none=True),
    )

    print(f"   Signature: {signature[:32]}...")

    # Step 4: Create envelope object
    print("\n4. Creating envelope object...")
    envelope_dict = {
        "version": "1",
        "envelope_id": envelope_id,
        "sender": sender_key.public_key_hex(),
        "recipient": recipient_key.public_key_hex(),
        "timestamp": timestamp,
        "expires_at": expires_at,
        "nonce": nonce,
        "scope": "test",
        "payload": payload.model_dump(exclude_none=True),
        "signature": signature,
    }

    # Validate envelope
    envelope = Envelope(**envelope_dict)
    print(f"   Envelope size: {envelope.size_bytes()} bytes")
    print(f"   Expires at: {envelope.expires_at}")
    print(f"   Is expired: {envelope.is_expired()}")

    # Step 5: Display envelope
    print("\n5. Complete envelope:")
    print("-" * 50)
    import json

    print(json.dumps(envelope_dict, indent=2))
    print("-" * 50)

    print("\n✓ Envelope created successfully!")
    print("\nNext steps:")
    print("  - Start an inbox: epp-inbox")
    print("  - Add sender to trust registry: eppctl trust add ...")
    print("  - Send envelope: eppctl envelope send envelope.json http://localhost:8000")


if __name__ == "__main__":
    main()
