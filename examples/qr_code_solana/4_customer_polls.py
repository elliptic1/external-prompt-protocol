#!/usr/bin/env python3
"""
Step 4: Customer's AI Polls for Messages

This script simulates what happens on the customer's device
(wearable, phone, etc.) when it polls for new messages:

1. Poll Solana for messages (SIMULATED - reads from file)
2. Verify cryptographic signature
3. Check trust registry
4. Apply rate limits and policies
5. Queue for AI processing

The customer's AI runs this periodically (e.g., when on WiFi).
No server needed - just poll the blockchain.

Run this after 3_vendor_sends.py.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from epp.crypto.keys import PublicKey
from epp.crypto.signing import verify_envelope_signature
from epp.models import Envelope
from epp.policy.trust_registry import TrustRegistry
from epp.policy.rate_limiter import RateLimiter


def main():
    base_dir = Path(__file__).parent
    data_dir = base_dir / "data"
    blockchain_sim_dir = data_dir / "blockchain_sim"
    queue_dir = data_dir / "queue"

    # Create queue directory
    queue_dir.mkdir(parents=True, exist_ok=True)

    print()
    print("=" * 60)
    print("Customer's AI: Polling for Messages")
    print("=" * 60)
    print()

    # Step 1: Poll Solana (SIMULATED)
    # -----------------------------------------------------------------
    print("Step 1: Polling Solana blockchain (SIMULATED)...")
    print()

    # In real life, we would use SolanaTransport:
    #
    # from epp.transport.solana import SolanaTransport
    #
    # transport = SolanaTransport(
    #     rpc_url="https://api.mainnet-beta.solana.com"
    # )
    #
    # my_pubkey = my_keypair.public_key_hex()
    # async for envelope in transport.receive(my_pubkey, since=last_cursor):
    #     process_envelope(envelope)
    #
    # Cost: Free (reading is free on Solana)

    # For this demo, read from simulation directory
    if not blockchain_sim_dir.exists():
        print("  No messages found.")
        print("  Run 3_vendor_sends.py first to simulate a message.")
        return

    envelope_files = list(blockchain_sim_dir.glob("*.json"))
    if not envelope_files:
        print("  No messages found.")
        print("  Run 3_vendor_sends.py first to simulate a message.")
        return

    print(f"  [SIMULATED] Polling Solana for messages addressed to us...")
    print(f"  [SIMULATED] Found {len(envelope_files)} message(s)")
    print()

    # Load trust registry
    registry_path = data_dir / "customer_trust_registry.json"
    if not registry_path.exists():
        print("ERROR: Trust registry not found.")
        print("Run 2_customer_scans.py first to set up trust.")
        return

    registry = TrustRegistry(storage_path=str(registry_path))
    rate_limiter = RateLimiter()

    # Process each envelope
    processed = 0
    queued = 0

    for envelope_file in envelope_files:
        print(f"  Processing: {envelope_file.name}")

        with open(envelope_file) as f:
            envelope_dict = json.load(f)

        envelope_id = envelope_dict.get("envelope_id", "unknown")

        # Step 2: Verify signature
        # -------------------------------------------------------------
        print()
        print("Step 2: Verifying cryptographic signature...")

        try:
            sender_key = PublicKey.from_hex(envelope_dict["sender"])
            is_valid = verify_envelope_signature(
                sender_key,
                envelope_dict["signature"],
                envelope_dict["version"],
                envelope_dict["envelope_id"],
                envelope_dict["sender"],
                envelope_dict["recipient"],
                envelope_dict["timestamp"],
                envelope_dict["expires_at"],
                envelope_dict["nonce"],
                envelope_dict["scope"],
                envelope_dict["payload"],
            )

            if not is_valid:
                print("  REJECTED: Invalid signature")
                continue

            print("  Signature: VALID")

        except Exception as e:
            print(f"  REJECTED: Signature error - {e}")
            continue

        # Step 3: Check trust registry
        # -------------------------------------------------------------
        print()
        print("Step 3: Checking trust registry...")

        sender_pubkey = envelope_dict["sender"]
        trust_entry = registry.get_sender(sender_pubkey)

        if not trust_entry:
            print(f"  REJECTED: Sender not trusted")
            print(f"  Sender key: {sender_pubkey[:32]}...")
            continue

        print(f"  Sender: {trust_entry.name}")
        print(f"  Status: TRUSTED")

        # Step 4: Check scope policy
        # -------------------------------------------------------------
        print()
        print("Step 4: Checking scope policy...")

        scope = envelope_dict["scope"]
        if not trust_entry.policy.allows_scope(scope):
            print(f"  REJECTED: Scope '{scope}' not allowed")
            print(f"  Allowed scopes: {', '.join(trust_entry.policy.allowed_scopes)}")
            continue

        print(f"  Scope: {scope}")
        print(f"  Status: ALLOWED")

        # Step 5: Check expiration
        # -------------------------------------------------------------
        print()
        print("Step 5: Checking expiration...")

        expires_at = envelope_dict["expires_at"]
        try:
            exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if exp_dt < datetime.now(timezone.utc):
                print(f"  REJECTED: Expired at {expires_at}")
                continue
            print(f"  Expires: {expires_at}")
            print(f"  Status: NOT EXPIRED")
        except ValueError:
            print(f"  REJECTED: Invalid expiration format")
            continue

        # Step 6: Check size limit
        # -------------------------------------------------------------
        print()
        print("Step 6: Checking size limit...")

        envelope_size = len(json.dumps(envelope_dict))
        max_size = trust_entry.policy.max_envelope_size

        if envelope_size > max_size:
            print(f"  REJECTED: Size {envelope_size} exceeds limit {max_size}")
            continue

        print(f"  Size: {envelope_size:,} bytes")
        print(f"  Limit: {max_size:,} bytes")
        print(f"  Status: WITHIN LIMIT")

        # Step 7: Check rate limit
        # -------------------------------------------------------------
        print()
        print("Step 7: Checking rate limit...")

        rate_allowed, rate_msg = rate_limiter.check_and_record(
            sender_pubkey,
            trust_entry.policy.rate_limit.max_per_hour,
            trust_entry.policy.rate_limit.max_per_day,
        )

        if not rate_allowed:
            print(f"  REJECTED: {rate_msg}")
            continue

        print(f"  Rate: {trust_entry.policy.rate_limit.max_per_hour}/hour, {trust_entry.policy.rate_limit.max_per_day}/day")
        print(f"  Status: WITHIN LIMITS")

        # Step 8: Queue for AI processing
        # -------------------------------------------------------------
        print()
        print("Step 8: Queueing for AI processing...")

        # Save to queue
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        queue_file = queue_dir / f"{timestamp}_{envelope_id}.json"

        queue_entry = {
            "envelope": envelope_dict,
            "trust_entry": {
                "name": trust_entry.name,
                "public_key": trust_entry.public_key[:32] + "...",
            },
            "received_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
        }

        with open(queue_file, "w") as f:
            json.dump(queue_entry, f, indent=2)

        print(f"  Queued: {queue_file.name}")
        queued += 1

        # Clean up processed envelope from "blockchain"
        envelope_file.unlink()
        processed += 1

        print()
        print("-" * 60)

    # Summary
    # -----------------------------------------------------------------
    print()
    print("=" * 60)
    print("Polling Complete!")
    print("=" * 60)
    print()
    print(f"  Processed: {processed} message(s)")
    print(f"  Queued: {queued} message(s)")
    print()

    if queued > 0:
        print("  What your AI would do next:")
        print("    1. Read the queued prompt")
        print("    2. Analyze context (exhibit info, location, etc.)")
        print("    3. Decide relevance and timing")
        print("    4. Notify you appropriately")
        print()
        print("  Example notification:")
        print("  ┌─────────────────────────────────────────────────┐")
        print("  │                                                 │")
        print("  │  [Whispered through earbuds]                    │")
        print("  │                                                 │")
        print("  │  'The T-Rex skeleton in front of you is        │")
        print("  │   actually a cast of Sue, the most complete    │")
        print("  │   T-Rex ever found. Want to know more?'        │")
        print("  │                                                 │")
        print("  └─────────────────────────────────────────────────┘")
        print()

    print("  Queue location: {0}".format(queue_dir))
    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
