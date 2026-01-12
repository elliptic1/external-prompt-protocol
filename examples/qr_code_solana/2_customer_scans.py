#!/usr/bin/env python3
"""
Step 2: Customer Scans QR Code

This script simulates what happens when a customer scans the
vendor's QR code with their phone/wearable:

1. Parse the QR code payload
2. Validate the trust invitation
3. Show the customer what permissions are requested
4. Add the vendor to the customer's trust registry

In real life, this would be a camera scan on a mobile device.
Here we read from the JSON file created by 1_vendor_setup.py.

Run this after 1_vendor_setup.py.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from epp.policy.trust_registry import TrustRegistry, SenderPolicy, RateLimit


def validate_invitation(payload: dict) -> tuple[bool, str]:
    """Validate a trust invitation payload."""

    # Check EPP version
    if payload.get("epp") != "1":
        return False, f"Unsupported EPP version: {payload.get('epp')}"

    # Check type
    if payload.get("type") != "trust_invitation":
        return False, f"Not a trust invitation: {payload.get('type')}"

    # Check required fields
    vendor = payload.get("vendor", {})
    if not vendor.get("name"):
        return False, "Missing vendor name"
    if not vendor.get("public_key"):
        return False, "Missing vendor public key"

    # Check expiration
    expires = payload.get("invitation_expires")
    if expires:
        try:
            exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if exp_dt < datetime.now(timezone.utc):
                return False, f"Invitation expired: {expires}"
        except ValueError:
            return False, f"Invalid expiration format: {expires}"

    return True, "Valid"


def main():
    base_dir = Path(__file__).parent
    data_dir = base_dir / "data"

    print()
    print("=" * 60)
    print("Customer: Scanning QR Code")
    print("=" * 60)
    print()

    # Step 1: "Scan" the QR code (read from file)
    # -----------------------------------------------------------------
    print("Step 1: Scanning QR code...")
    print()

    qr_payload_path = data_dir / "qr_payload.json"
    if not qr_payload_path.exists():
        print("ERROR: QR payload not found.")
        print("Run 1_vendor_setup.py first to generate the QR code.")
        return

    with open(qr_payload_path) as f:
        payload = json.load(f)

    print(f"  [Camera captures QR code]")
    print(f"  [Decoding JSON payload...]")
    print()

    # Step 2: Validate the invitation
    # -----------------------------------------------------------------
    print("Step 2: Validating trust invitation...")
    print()

    valid, message = validate_invitation(payload)
    if not valid:
        print(f"  ERROR: {message}")
        print("  Invitation rejected.")
        return

    print(f"  Status: {message}")
    print()

    # Step 3: Show the customer what's being requested
    # -----------------------------------------------------------------
    print("Step 3: Reviewing permissions...")
    print()
    print("  ┌─────────────────────────────────────────────────┐")
    print("  │                                                 │")
    print(f"  │  {payload['vendor']['name']:^45}  │")
    print("  │  wants to send prompts to your AI              │")
    print("  │                                                 │")
    print("  │  Requested permissions:                        │")

    policy = payload.get("policy", {})
    scopes = policy.get("scopes", [])
    print(f"  │    Scopes: {', '.join(scopes):<35} │")

    max_hour = policy.get("max_per_hour", "unlimited")
    max_day = policy.get("max_per_day", "unlimited")
    print(f"  │    Rate: {max_hour}/hour, {max_day}/day{' ' * 21}│")

    max_size = policy.get("max_envelope_size", 0)
    print(f"  │    Max size: {max_size:,} bytes{' ' * 24}│")

    print("  │                                                 │")
    print("  │  [Accept]  [Modify]  [Decline]                  │")
    print("  │                                                 │")
    print("  └─────────────────────────────────────────────────┘")
    print()

    # In a real app, the user would tap Accept/Modify/Decline
    # Here we simulate accepting
    print("  [User taps Accept]")
    print()

    # Step 4: Add to trust registry
    # -----------------------------------------------------------------
    print("Step 4: Adding to trust registry...")
    print()

    # Create customer's trust registry if it doesn't exist
    registry_path = data_dir / "customer_trust_registry.json"
    registry = TrustRegistry(storage_path=str(registry_path))

    # Check if already trusted
    vendor_key = payload["vendor"]["public_key"]
    if registry.is_trusted(vendor_key):
        print(f"  Note: {payload['vendor']['name']} is already trusted.")
        print("  Updating policy...")
        registry.remove_sender(vendor_key)

    # Create policy from invitation
    sender_policy = SenderPolicy(
        allowed_scopes=policy.get("scopes", []),
        max_envelope_size=policy.get("max_envelope_size", 10 * 1024),
        rate_limit=RateLimit(
            max_per_hour=policy.get("max_per_hour"),
            max_per_day=policy.get("max_per_day"),
        ),
    )

    # Add to registry
    entry = registry.add_sender(
        public_key=vendor_key,
        name=payload["vendor"]["name"],
        policy=sender_policy,
    )

    print(f"  Added: {entry.name}")
    print(f"  Public key: {entry.public_key[:32]}...")
    print(f"  Scopes: {', '.join(entry.policy.allowed_scopes)}")
    print(f"  Rate limit: {entry.policy.rate_limit.max_per_hour}/hour, {entry.policy.rate_limit.max_per_day}/day")
    print()
    print(f"  Registry saved: {registry_path}")
    print()

    # Step 5: Summary
    # -----------------------------------------------------------------
    print("=" * 60)
    print("Trust Granted!")
    print("=" * 60)
    print()
    print(f"  {payload['vendor']['name']} can now send prompts to your AI.")
    print()
    print("  What this means:")
    print("    - Museum can post messages to Solana addressed to you")
    print("    - Your AI will poll Solana and find these messages")
    print("    - Messages will be verified against this public key")
    print("    - Rate limits and scopes will be enforced")
    print()
    print("  To revoke access:")
    print("    - Remove the vendor from your trust registry")
    print("    - Your AI will ignore their messages")
    print()
    print("  Next steps:")
    print("    - Run 3_vendor_sends.py to simulate museum sending a prompt")
    print("    - Run 4_customer_polls.py to simulate your AI receiving it")
    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
