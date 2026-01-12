#!/usr/bin/env python3
"""
Step 4: Coffee Shop Sends a Promotional Prompt

This script simulates a coffee shop sending you a personalized
promotion via EPP. The coffee shop:

1. Loads its private key (to sign the envelope)
2. Loads your public key (to address the envelope)
3. Creates an envelope with a promotional message
4. Signs the envelope cryptographically
5. Sends it to your inbox via HTTP POST

Your inbox will:
1. Verify the signature (proves it's really from the coffee shop)
2. Check that the coffee shop is in your trust registry
3. Verify the scope "retail" is allowed for this sender
4. Check rate limits aren't exceeded
5. Queue the prompt for your AI

Run this after the inbox is running (3_run_inbox.py).
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from epp.crypto.keys import KeyPair
from epp.crypto.signing import sign_envelope, generate_nonce
from epp.models import Envelope, Payload


def main():
    keys_dir = Path(__file__).parent / "keys"

    print()
    print("=" * 60)
    print("Coffee Shop: Sending Promotional Prompt")
    print("=" * 60)
    print()

    # Load coffee shop's private key (for signing)
    private_key_path = keys_dir / "coffee_shop.key"
    if not private_key_path.exists():
        print("ERROR: Coffee shop keys not found.")
        print("Run 1_setup.py first.")
        return

    with open(private_key_path, "rb") as f:
        coffee_shop_keypair = KeyPair.from_private_pem(f.read())

    sender_pubkey = coffee_shop_keypair.public_key_hex()
    print(f"Sender (Coffee Shop): {sender_pubkey[:32]}...")

    # Load recipient's public key (your inbox)
    recipient_pubkey_path = keys_dir / "inbox.pub"
    if not recipient_pubkey_path.exists():
        print("ERROR: Inbox public key not found.")
        print("Run 1_setup.py first.")
        return

    recipient_pubkey = recipient_pubkey_path.read_text().strip()
    print(f"Recipient (Your Inbox): {recipient_pubkey[:32]}...")
    print()

    # Create the envelope
    # -----------------------------------------------------------------
    # This is the actual prompt being sent to your AI

    envelope_id = str(uuid4())
    now = datetime.now(timezone.utc)
    timestamp = now.isoformat().replace("+00:00", "Z")
    expires_at = (now + timedelta(hours=4)).isoformat().replace("+00:00", "Z")
    nonce = generate_nonce()

    # The payload contains the prompt and context
    payload = Payload(
        prompt="Your usual vanilla oat latte is ready for pickup! "
               "We're offering 20% off for loyalty members today.",
        context={
            "store_name": "Bean Counter Coffee",
            "store_location": "123 Main Street",
            "offer_code": "LOYAL20",
            "offer_discount": "20%",
            "valid_until": expires_at,
            "your_usual_order": "Vanilla Oat Latte, Large, Extra Shot",
        },
        metadata={
            "priority": "low",
            "category": "promotion",
            "action_type": "notification",
        },
    )

    print("Creating envelope...")
    print(f"  Envelope ID: {envelope_id}")
    print(f"  Scope: retail")
    print(f"  Expires: {expires_at}")
    print()
    print("Prompt:")
    print(f"  \"{payload.prompt}\"")
    print()
    print("Context:")
    for key, value in payload.context.items():
        print(f"  {key}: {value}")
    print()

    # Sign the envelope
    # -----------------------------------------------------------------
    # The signature proves this envelope really came from the coffee shop

    print("Signing envelope with coffee shop's private key...")

    signature = sign_envelope(
        coffee_shop_keypair,
        version="1",
        envelope_id=envelope_id,
        sender=sender_pubkey,
        recipient=recipient_pubkey,
        timestamp=timestamp,
        expires_at=expires_at,
        nonce=nonce,
        scope="retail",
        payload=payload.model_dump(exclude_none=True),
    )

    print(f"  Signature: {signature[:32]}...")
    print()

    # Build the complete envelope
    envelope = {
        "version": "1",
        "envelope_id": envelope_id,
        "sender": sender_pubkey,
        "recipient": recipient_pubkey,
        "timestamp": timestamp,
        "expires_at": expires_at,
        "nonce": nonce,
        "scope": "retail",
        "payload": payload.model_dump(exclude_none=True),
        "signature": signature,
    }

    # Send to inbox
    # -----------------------------------------------------------------

    inbox_url = "http://localhost:8000/epp/v1/submit"
    print(f"Sending to inbox: {inbox_url}")
    print()

    try:
        response = httpx.post(
            inbox_url,
            json=envelope,
            timeout=30.0,
        )

        print(f"Response status: {response.status_code}")
        print()

        result = response.json()
        print("Response:")
        print(json.dumps(result, indent=2))
        print()

        if response.status_code == 200:
            print("=" * 60)
            print("SUCCESS! Envelope accepted by inbox.")
            print()
            print("What happens next:")
            print("  1. Envelope is queued for your AI")
            print("  2. Your AI reads the prompt and context")
            print("  3. AI decides when/how to notify you")
            print("  4. Maybe whispers: 'Coffee shop has your usual ready'")
            print("=" * 60)
        else:
            print("=" * 60)
            print(f"REJECTED: {result.get('error_code', 'Unknown error')}")
            print(f"Message: {result.get('message', 'No message')}")
            print("=" * 60)

    except httpx.ConnectError:
        print("ERROR: Could not connect to inbox.")
        print("Make sure 3_run_inbox.py is running.")
    except Exception as e:
        print(f"ERROR: {e}")


if __name__ == "__main__":
    main()
