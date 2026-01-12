#!/usr/bin/env python3
"""
Step 2: Configure the Inbox Trust Registry

This script sets up your inbox's trust registry, which defines:
- Which senders are trusted
- What scopes each sender can use
- Rate limits per sender

Think of this as your "contacts list" for EPP - only people
in this list can send prompts to your AI.

Run this after 1_setup.py generates the keys.
"""

import json
from pathlib import Path

from epp.policy.trust_registry import TrustRegistry, TrustEntry, SenderPolicy, RateLimit


def main():
    keys_dir = Path(__file__).parent / "keys"
    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(exist_ok=True)

    print("=" * 60)
    print("EPP Trust Registry Configuration")
    print("=" * 60)
    print()

    # Load public keys
    def load_pubkey(name: str) -> str:
        path = keys_dir / f"{name}.pub"
        if not path.exists():
            raise FileNotFoundError(f"Run 1_setup.py first! Missing: {path}")
        return path.read_text().strip()

    inbox_pubkey = load_pubkey("inbox")
    coffee_shop_pubkey = load_pubkey("coffee_shop")
    app_store_pubkey = load_pubkey("app_store")

    print(f"Inbox public key: {inbox_pubkey[:32]}...")
    print()

    # Create trust registry
    registry = TrustRegistry(storage_path=str(data_dir / "trust_registry.json"))

    # Add Coffee Shop as trusted sender
    print("Adding trusted sender: Bean Counter Coffee")
    print("  - Allowed scopes: retail, promotions")
    print("  - Rate limit: 10/hour, 50/day")
    print("  - Max envelope size: 10 KB")

    registry.add_sender(
        public_key=coffee_shop_pubkey,
        name="Bean Counter Coffee",
        policy=SenderPolicy(
            allowed_scopes=["retail", "promotions"],
            max_envelope_size=10 * 1024,  # 10 KB
            rate_limit=RateLimit(max_per_hour=10, max_per_day=50),
        ),
    )
    print()

    # Add App Store as trusted sender
    print("Adding trusted sender: App Store Review Team")
    print("  - Allowed scopes: app-review, account")
    print("  - Rate limit: 5/hour, 20/day")
    print("  - Max envelope size: 100 KB")

    registry.add_sender(
        public_key=app_store_pubkey,
        name="App Store Review Team",
        policy=SenderPolicy(
            allowed_scopes=["app-review", "account"],
            max_envelope_size=100 * 1024,  # 100 KB (reviews can be detailed)
            rate_limit=RateLimit(max_per_hour=5, max_per_day=20),
        ),
    )
    print()

    # Save the registry
    registry.save()
    print(f"Trust registry saved to: {data_dir / 'trust_registry.json'}")

    # Show the registry contents
    print()
    print("=" * 60)
    print("Trust Registry Contents")
    print("=" * 60)

    for entry in registry.list_senders():
        print(f"\nSender: {entry.name}")
        print(f"  Public key: {entry.public_key[:32]}...")
        print(f"  Scopes: {', '.join(entry.policy.allowed_scopes)}")
        print(f"  Rate limit: {entry.policy.rate_limit.max_per_hour}/hour, {entry.policy.rate_limit.max_per_day}/day")

    print()
    print("=" * 60)
    print("Configuration complete!")
    print()
    print("Your inbox will now accept prompts from:")
    print("  - Bean Counter Coffee (retail, promotions)")
    print("  - App Store Review Team (app-review, account)")
    print()
    print("All other senders will be rejected.")
    print("=" * 60)


if __name__ == "__main__":
    main()
