#!/usr/bin/env python3
"""
Step 1: Vendor Setup - Generate Keys and QR Code

This script simulates what a vendor (museum, store, etc.) would do
to set up their EPP identity and create a QR code for customers to scan.

The vendor:
1. Generates an Ed25519 keypair
2. Converts the public key to a Solana address
3. Creates a QR code containing their identity and proposed policy
4. Displays the QR code for customers to scan

Run this first before the other scripts.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from epp.crypto.keys import KeyPair

# Try to import qrcode, provide helpful message if not installed
try:
    import qrcode
except ImportError:
    print("ERROR: qrcode library not installed.")
    print("Install with: pip install qrcode[pil]")
    print()
    print("Or for ASCII-only (no image): pip install qrcode")
    sys.exit(1)


def main():
    base_dir = Path(__file__).parent
    keys_dir = base_dir / "keys"
    data_dir = base_dir / "data"

    # Create directories
    keys_dir.mkdir(exist_ok=True)
    data_dir.mkdir(exist_ok=True)

    print()
    print("=" * 60)
    print("Vendor Setup: Natural History Museum")
    print("=" * 60)
    print()

    # Step 1: Generate vendor keypair
    # -----------------------------------------------------------------
    print("Step 1: Generating Ed25519 keypair...")
    print()

    keypair = KeyPair.generate()
    public_key_hex = keypair.public_key_hex()

    # Save keys
    private_key_path = keys_dir / "museum.key"
    public_key_path = keys_dir / "museum.pub"

    with open(private_key_path, "wb") as f:
        f.write(keypair.private_key_pem())

    with open(public_key_path, "w") as f:
        f.write(public_key_hex)

    print(f"  Private key saved: {private_key_path}")
    print(f"  Public key saved: {public_key_path}")
    print()
    print(f"  Public key (hex): {public_key_hex[:32]}...")
    print()

    # Step 2: Convert to Solana address
    # -----------------------------------------------------------------
    print("Step 2: Converting to Solana address...")
    print()

    # EPP uses Ed25519, same as Solana. Direct conversion.
    # For this example, we'll show the conversion but use the hex key.
    # The actual Solana address would be base58-encoded.

    try:
        from epp.transport.solana import epp_pubkey_to_solana_address
        solana_address = epp_pubkey_to_solana_address(public_key_hex)
        print(f"  Solana address: {solana_address}")
    except ImportError:
        # Solana deps not installed, create a placeholder
        solana_address = f"(install solana deps to see address)"
        print(f"  Solana address: {solana_address}")
        print("  (Install with: pip install external-prompt-protocol[solana])")

    print()

    # Step 3: Create QR code payload
    # -----------------------------------------------------------------
    print("Step 3: Creating trust invitation payload...")
    print()

    # The QR code contains everything a customer needs to:
    # 1. Identify the vendor
    # 2. Know where to poll for messages
    # 3. Understand what permissions are requested

    invitation_expires = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()

    qr_payload = {
        "epp": "1",
        "type": "trust_invitation",
        "vendor": {
            "name": "Natural History Museum",
            "public_key": public_key_hex,
            "solana_address": solana_address if "(" not in str(solana_address) else None,
        },
        "policy": {
            "scopes": ["exhibits", "tours", "events"],
            "max_envelope_size": 10 * 1024,  # 10 KB
            "max_per_hour": 10,
            "max_per_day": 50,
        },
        "invitation_expires": invitation_expires,
    }

    # Save payload for inspection
    payload_path = data_dir / "qr_payload.json"
    with open(payload_path, "w") as f:
        json.dump(qr_payload, f, indent=2)

    print(f"  Payload saved: {payload_path}")
    print()
    print("  Payload contents:")
    print(f"    Vendor: {qr_payload['vendor']['name']}")
    print(f"    Scopes: {', '.join(qr_payload['policy']['scopes'])}")
    print(f"    Rate limit: {qr_payload['policy']['max_per_hour']}/hour, {qr_payload['policy']['max_per_day']}/day")
    print(f"    Max size: {qr_payload['policy']['max_envelope_size']} bytes")
    print(f"    Expires: {invitation_expires[:10]}")
    print()

    # Step 4: Generate QR code
    # -----------------------------------------------------------------
    print("Step 4: Generating QR code...")
    print()

    # Create compact JSON for QR code (no whitespace)
    qr_data = json.dumps(qr_payload, separators=(",", ":"))

    qr = qrcode.QRCode(
        version=None,  # Auto-size
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)

    # Save as PNG image
    qr_image_path = data_dir / "museum_qr.png"
    try:
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(str(qr_image_path))
        print(f"  QR code image saved: {qr_image_path}")
    except Exception as e:
        print(f"  Could not save PNG (PIL not installed): {e}")
        print("  Install with: pip install qrcode[pil]")

    # Print ASCII version to terminal
    print()
    print("  QR Code (scan with your phone):")
    print()
    qr.print_ascii(invert=True)

    # Step 5: Summary
    # -----------------------------------------------------------------
    print()
    print("=" * 60)
    print("Setup Complete!")
    print("=" * 60)
    print()
    print("What was created:")
    print(f"  1. Keypair: {keys_dir}/")
    print(f"  2. QR payload: {payload_path}")
    print(f"  3. QR image: {qr_image_path}")
    print()
    print("Next steps:")
    print("  1. Display QR code at museum entrance")
    print("  2. Customers scan to grant trust")
    print("  3. Run 2_customer_scans.py to simulate scanning")
    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
