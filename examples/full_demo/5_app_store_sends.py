#!/usr/bin/env python3
"""
Step 5: App Store Sends a Rejection Notice

This script simulates an app store sending you a rejection
notice for your app via EPP. This is a more serious use case:

Instead of checking emails and logging into a web portal,
the rejection goes directly to your AI, which can:
- Analyze the rejection reason
- Search your codebase for the issue
- Suggest fixes
- Draft an appeal

The app store:
1. Creates a detailed rejection envelope
2. Signs it with their private key
3. Sends it to your inbox

Your AI receives structured data, not just plain text.

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
from epp.models import Payload


def main():
    keys_dir = Path(__file__).parent / "keys"

    print()
    print("=" * 60)
    print("App Store: Sending Rejection Notice")
    print("=" * 60)
    print()

    # Load app store's private key
    private_key_path = keys_dir / "app_store.key"
    if not private_key_path.exists():
        print("ERROR: App store keys not found.")
        print("Run 1_setup.py first.")
        return

    with open(private_key_path, "rb") as f:
        app_store_keypair = KeyPair.from_private_pem(f.read())

    sender_pubkey = app_store_keypair.public_key_hex()
    print(f"Sender (App Store): {sender_pubkey[:32]}...")

    # Load recipient's public key
    recipient_pubkey_path = keys_dir / "inbox.pub"
    if not recipient_pubkey_path.exists():
        print("ERROR: Inbox public key not found.")
        print("Run 1_setup.py first.")
        return

    recipient_pubkey = recipient_pubkey_path.read_text().strip()
    print(f"Recipient (Your Inbox): {recipient_pubkey[:32]}...")
    print()

    # Create the rejection envelope
    # -----------------------------------------------------------------

    envelope_id = str(uuid4())
    now = datetime.now(timezone.utc)
    timestamp = now.isoformat().replace("+00:00", "Z")
    expires_at = (now + timedelta(days=7)).isoformat().replace("+00:00", "Z")
    nonce = generate_nonce()

    # Detailed rejection with structured data
    payload = Payload(
        prompt=(
            "Your app 'WeatherWidget' (version 2.1.0) has been rejected. "
            "Please review the issues below and submit a new build."
        ),
        context={
            # App identification
            "app_id": "com.example.weatherwidget",
            "app_name": "WeatherWidget",
            "version": "2.1.0",
            "build_number": "42",
            "submission_id": "SUB-2025-01-12-001",

            # Rejection details
            "rejection_reason": "Guideline 4.2 - Minimum Functionality",
            "rejection_details": (
                "Your app appears to be a simple web wrapper that provides "
                "a limited user experience. Apps that are not very useful, "
                "unique, or 'app-like' may be rejected. Consider adding native "
                "features such as widgets, notifications, or offline support."
            ),

            # Specific issues found
            "issues": [
                {
                    "guideline": "4.2",
                    "title": "Minimum Functionality",
                    "description": "App is primarily a WebView wrapper",
                    "suggestion": "Add native iOS widgets or complications",
                },
                {
                    "guideline": "4.2.2",
                    "title": "No Offline Mode",
                    "description": "App shows error when offline",
                    "suggestion": "Cache weather data for offline viewing",
                },
            ],

            # Timeline
            "submitted_at": "2025-01-10T14:30:00Z",
            "reviewed_at": timestamp,
            "appeal_deadline": (now + timedelta(days=14)).isoformat().replace("+00:00", "Z"),

            # Links
            "app_store_connect_url": "https://appstoreconnect.apple.com/apps/123456789",
            "guidelines_url": "https://developer.apple.com/app-store/review/guidelines/#minimum-functionality",
        },
        metadata={
            "priority": "high",
            "category": "app-review",
            "action_type": "review-required",
            "reviewer_id": "reviewer-7823",
        },
    )

    print("Creating rejection envelope...")
    print(f"  Envelope ID: {envelope_id}")
    print(f"  Scope: app-review")
    print(f"  Expires: {expires_at}")
    print()
    print("Rejection Summary:")
    print(f"  App: {payload.context['app_name']} v{payload.context['version']}")
    print(f"  Reason: {payload.context['rejection_reason']}")
    print()
    print("Issues Found:")
    for i, issue in enumerate(payload.context['issues'], 1):
        print(f"  {i}. [{issue['guideline']}] {issue['title']}")
        print(f"     {issue['description']}")
        print(f"     Suggestion: {issue['suggestion']}")
    print()

    # Sign the envelope
    print("Signing envelope with app store's private key...")

    signature = sign_envelope(
        app_store_keypair,
        version="1",
        envelope_id=envelope_id,
        sender=sender_pubkey,
        recipient=recipient_pubkey,
        timestamp=timestamp,
        expires_at=expires_at,
        nonce=nonce,
        scope="app-review",
        payload=payload.model_dump(exclude_none=True),
    )

    print(f"  Signature: {signature[:32]}...")
    print()

    # Build complete envelope
    envelope = {
        "version": "1",
        "envelope_id": envelope_id,
        "sender": sender_pubkey,
        "recipient": recipient_pubkey,
        "timestamp": timestamp,
        "expires_at": expires_at,
        "nonce": nonce,
        "scope": "app-review",
        "payload": payload.model_dump(exclude_none=True),
        "signature": signature,
    }

    # Send to inbox
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
            print("SUCCESS! Rejection notice delivered to inbox.")
            print()
            print("What your AI could do with this:")
            print("  1. Alert you immediately (high priority)")
            print("  2. Analyze rejection against guidelines")
            print("  3. Search your codebase for WebView usage")
            print("  4. Suggest adding native widgets")
            print("  5. Draft an appeal or create fix tasks")
            print("  6. Set reminder before appeal deadline")
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
