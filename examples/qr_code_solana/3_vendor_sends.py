#!/usr/bin/env python3
"""
Step 3: Vendor Sends a Prompt

This script simulates the museum sending a prompt to a customer
who previously scanned their QR code.

The museum:
1. Loads its private key
2. Creates an envelope with exhibit information
3. Signs the envelope
4. Posts to Solana (SIMULATED - saves to file)

In real life, this would post to the Solana blockchain.
Customers' devices would later poll Solana to find this message.

Run this after 1_vendor_setup.py and 2_customer_scans.py.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from epp.crypto.keys import KeyPair
from epp.crypto.signing import sign_envelope, generate_nonce
from epp.models import Envelope, Payload


def main():
    base_dir = Path(__file__).parent
    keys_dir = base_dir / "keys"
    data_dir = base_dir / "data"
    blockchain_sim_dir = data_dir / "blockchain_sim"

    # Create simulation directory
    blockchain_sim_dir.mkdir(parents=True, exist_ok=True)

    print()
    print("=" * 60)
    print("Museum: Sending Exhibit Information")
    print("=" * 60)
    print()

    # Step 1: Load museum's private key
    # -----------------------------------------------------------------
    print("Step 1: Loading museum credentials...")
    print()

    private_key_path = keys_dir / "museum.key"
    if not private_key_path.exists():
        print("ERROR: Museum keys not found.")
        print("Run 1_vendor_setup.py first.")
        return

    with open(private_key_path, "rb") as f:
        museum_keypair = KeyPair.from_private_pem(f.read())

    museum_pubkey = museum_keypair.public_key_hex()
    print(f"  Museum public key: {museum_pubkey[:32]}...")
    print()

    # Step 2: Get customer's address (from QR payload)
    # -----------------------------------------------------------------
    print("Step 2: Looking up customer address...")
    print()

    # In real life, the museum would have a list of customers who
    # scanned the QR code, with their Solana addresses.
    # For this demo, we use the same key (customer polls by their own key).

    # Load QR payload to get the address customers should poll
    qr_payload_path = data_dir / "qr_payload.json"
    if not qr_payload_path.exists():
        print("ERROR: QR payload not found.")
        print("Run 1_vendor_setup.py first.")
        return

    with open(qr_payload_path) as f:
        qr_payload = json.load(f)

    # For Solana transport, we address by the recipient's public key
    # In this demo, we'll use a placeholder - the customer would provide
    # their address when scanning the QR code in a real implementation
    recipient_pubkey = museum_pubkey  # Self-addressed for demo

    print(f"  Recipient: {recipient_pubkey[:32]}...")
    print("  (In production, this would be the customer's public key)")
    print()

    # Step 3: Create the envelope
    # -----------------------------------------------------------------
    print("Step 3: Creating exhibit information envelope...")
    print()

    envelope_id = str(uuid4())
    now = datetime.now(timezone.utc)
    timestamp = now.isoformat().replace("+00:00", "Z")
    expires_at = (now + timedelta(days=7)).isoformat().replace("+00:00", "Z")
    nonce = generate_nonce()

    # The actual content the museum wants to share
    prompt_text = """You're near our T-Rex exhibit! Here's some fascinating information:

The T-Rex skeleton in front of you is actually a high-quality cast, not real fossils.
The original bones are too heavy and fragile to mount. Our cast was made from "Sue" -
the most complete T-Rex ever discovered, found in South Dakota in 1990.

Some facts to share with your human:
- T-Rex had the strongest bite of any land animal ever: 12,800 pounds of force
- Despite tiny arms, they were incredibly strong - able to lift 400 pounds each
- T-Rex could run up to 12 mph, slower than originally thought
- They lived 68-66 million years ago, right before the mass extinction

Would you like me to tell you about the casting process, or nearby exhibits?"""

    # Structured context for the AI to use
    context = {
        "exhibit_id": "TREX-001",
        "exhibit_name": "Tyrannosaurus Rex",
        "location": "Hall of Dinosaurs, Section A",
        "nearby_exhibits": [
            {"id": "TRIC-002", "name": "Triceratops"},
            {"id": "VELO-003", "name": "Velociraptor Pack"},
        ],
        "visitor_location": "Detected near T-Rex skeleton",
        "time_of_day": "afternoon",
        "suggested_actions": [
            "Share T-Rex facts verbally",
            "Offer to guide to related exhibits",
            "Mention gift shop has T-Rex items",
        ],
    }

    # Metadata about this message
    metadata = {
        "category": "exhibit_info",
        "priority": "normal",
        "triggered_by": "location_beacon",
        "museum_id": "natural_history_main",
    }

    print(f"  Envelope ID: {envelope_id}")
    print(f"  Scope: exhibits")
    print(f"  Expires: {expires_at}")
    print()
    print("  Prompt preview:")
    print(f"    {prompt_text[:80]}...")
    print()

    # Step 4: Sign the envelope
    # -----------------------------------------------------------------
    print("Step 4: Signing envelope with museum's private key...")
    print()

    payload_dict = {
        "prompt": prompt_text,
        "context": context,
        "metadata": metadata,
    }

    signature = sign_envelope(
        museum_keypair,
        version="1",
        envelope_id=envelope_id,
        sender=museum_pubkey,
        recipient=recipient_pubkey,
        timestamp=timestamp,
        expires_at=expires_at,
        nonce=nonce,
        scope="exhibits",
        payload=payload_dict,
    )

    print(f"  Signature: {signature[:32]}...")
    print()

    # Create the full envelope
    envelope_dict = {
        "version": "1",
        "envelope_id": envelope_id,
        "sender": museum_pubkey,
        "recipient": recipient_pubkey,
        "timestamp": timestamp,
        "expires_at": expires_at,
        "nonce": nonce,
        "scope": "exhibits",
        "payload": payload_dict,
        "signature": signature,
    }

    # Step 5: "Post" to Solana (SIMULATED)
    # -----------------------------------------------------------------
    print("Step 5: Posting to Solana blockchain (SIMULATED)...")
    print()

    # In real life, we would use SolanaTransport:
    #
    # from epp.transport.solana import SolanaTransport
    #
    # transport = SolanaTransport(
    #     rpc_url="https://api.devnet.solana.com",
    #     keypair_path="~/.config/solana/id.json",
    # )
    #
    # envelope = Envelope(**envelope_dict)
    # tx_sig = await transport.send(envelope, recipient_solana_address)
    # print(f"Transaction: {tx_sig}")
    #
    # Cost: ~$0.0002 USD per transaction

    # For this demo, save to file
    sim_file = blockchain_sim_dir / f"{envelope_id}.json"
    with open(sim_file, "w") as f:
        json.dump(envelope_dict, f, indent=2)

    print("  [SIMULATED] Envelope would be posted to Solana memo program")
    print(f"  [SIMULATED] Transaction cost: ~$0.0002")
    print(f"  [SIMULATED] Saved to: {sim_file}")
    print()

    # Show what Solana would store
    print("  What Solana stores (memo format):")
    print("  ┌─────────────────────────────────────────────────┐")
    print('  │ {"epp":"1","env":"<base64-encoded-envelope>"}  │')
    print("  │                                                 │")
    print("  │ Transaction includes:                          │")
    print("  │   - Sender account (museum's Solana address)   │")
    print("  │   - Recipient account (for indexing)           │")
    print("  │   - Memo data (the envelope)                   │")
    print("  └─────────────────────────────────────────────────┘")
    print()

    # Step 6: Summary
    # -----------------------------------------------------------------
    print("=" * 60)
    print("Message Sent!")
    print("=" * 60)
    print()
    print("  The museum has posted exhibit information to the blockchain.")
    print()
    print("  What happens next:")
    print("    1. Customer's device polls Solana (when on WiFi)")
    print("    2. Finds this message addressed to them")
    print("    3. Verifies signature against trusted public key")
    print("    4. Checks scope and rate limits")
    print("    5. Queues prompt for AI processing")
    print("    6. AI decides how/when to notify the customer")
    print()
    print("  Next step:")
    print("    Run 4_customer_polls.py to simulate the customer's device")
    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
