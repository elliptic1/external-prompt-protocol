#!/usr/bin/env python3
"""
Step 1: Generate Keys for All Parties

This script creates Ed25519 key pairs for:
- Your inbox (the recipient)
- Coffee shop (a sender)
- App store (another sender)

Each party needs:
- A private key (kept secret, used to sign)
- A public key (shared, used to verify and identify)

Run this first before any other scripts.
"""

import os
from pathlib import Path

from epp.crypto.keys import KeyPair


def main():
    # Create keys directory
    keys_dir = Path(__file__).parent / "keys"
    keys_dir.mkdir(exist_ok=True)

    print("=" * 60)
    print("EPP Key Generation")
    print("=" * 60)
    print()

    # Generate keys for each party
    parties = [
        ("inbox", "Your personal AI inbox"),
        ("coffee_shop", "Bean Counter Coffee"),
        ("app_store", "App Store Review Team"),
    ]

    for name, description in parties:
        print(f"Generating keys for: {description}")

        # Generate a new Ed25519 key pair
        keypair = KeyPair.generate()

        # Save private key (PEM format)
        private_key_path = keys_dir / f"{name}.key"
        with open(private_key_path, "wb") as f:
            f.write(keypair.private_key_pem())
        os.chmod(private_key_path, 0o600)  # Owner read/write only

        # Save public key (hex format for easy sharing)
        public_key_path = keys_dir / f"{name}.pub"
        with open(public_key_path, "w") as f:
            f.write(keypair.public_key_hex())

        print(f"  Private key: {private_key_path}")
        print(f"  Public key:  {public_key_path}")
        print(f"  Public key (hex): {keypair.public_key_hex()[:32]}...")
        print()

    print("=" * 60)
    print("Key generation complete!")
    print()
    print("IMPORTANT:")
    print("- Private keys (.key) must be kept secret")
    print("- Public keys (.pub) can be shared freely")
    print("- Share your inbox.pub with trusted senders")
    print("=" * 60)


if __name__ == "__main__":
    main()
