#!/usr/bin/env python3
"""
Step 6: Check the Queue

This script shows what envelopes have been received and
queued for your AI.

The file queue executor writes each accepted envelope to a
timestamped JSON file. In a real system, your AI would:
- Watch this directory for new files
- Read and parse each envelope
- Decide how to handle the prompt
- Take action (notify you, analyze, respond, etc.)

Run this after sending some envelopes (4 and 5).
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def format_timestamp(ts: str) -> str:
    """Format ISO timestamp for display."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except:
        return ts


def main():
    queue_dir = Path(__file__).parent / "data" / "queue"

    print()
    print("=" * 60)
    print("EPP Inbox Queue")
    print("=" * 60)
    print()

    if not queue_dir.exists():
        print("Queue directory not found.")
        print("Make sure you've run the inbox and sent some envelopes.")
        return

    # Find all envelope files
    envelope_files = sorted(queue_dir.glob("*.json"))

    if not envelope_files:
        print("No envelopes in queue.")
        print()
        print("Try running:")
        print("  1. python 3_run_inbox.py  (in one terminal)")
        print("  2. python 4_coffee_shop_sends.py")
        print("  3. python 5_app_store_sends.py")
        return

    print(f"Found {len(envelope_files)} envelope(s) in queue:")
    print()

    for i, filepath in enumerate(envelope_files, 1):
        try:
            with open(filepath) as f:
                envelope = json.load(f)

            # Extract key information
            sender = envelope.get("sender", "unknown")[:16]
            scope = envelope.get("scope", "unknown")
            timestamp = envelope.get("timestamp", "unknown")
            payload = envelope.get("payload", {})
            prompt = payload.get("prompt", "No prompt")
            context = payload.get("context", {})
            metadata = payload.get("metadata", {})

            # Determine sender name from context if available
            sender_name = context.get("store_name") or context.get("app_name") or f"Sender {sender}..."

            # Determine priority
            priority = metadata.get("priority", "normal")
            priority_indicator = {
                "high": "[!]",
                "normal": "[-]",
                "low": "[.]",
            }.get(priority, "[-]")

            print(f"{priority_indicator} Envelope #{i}")
            print(f"    File: {filepath.name}")
            print(f"    From: {sender_name}")
            print(f"    Scope: {scope}")
            print(f"    Received: {format_timestamp(timestamp)}")
            print(f"    Priority: {priority}")
            print()
            print(f"    Prompt:")
            # Word wrap the prompt
            words = prompt.split()
            line = "      "
            for word in words:
                if len(line) + len(word) > 70:
                    print(line)
                    line = "      "
                line += word + " "
            if line.strip():
                print(line)
            print()

            # Show key context items
            if context:
                print("    Context:")
                # Show first few context items
                shown = 0
                for key, value in context.items():
                    if shown >= 4:
                        remaining = len(context) - shown
                        print(f"      ... and {remaining} more fields")
                        break
                    if isinstance(value, (str, int, float, bool)):
                        print(f"      {key}: {value}")
                        shown += 1
                    elif isinstance(value, list):
                        print(f"      {key}: [{len(value)} items]")
                        shown += 1
            print()
            print("-" * 60)
            print()

        except Exception as e:
            print(f"[?] Envelope #{i}: Error reading {filepath.name}")
            print(f"    Error: {e}")
            print()

    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print()
    print(f"Total envelopes: {len(envelope_files)}")
    print()
    print("What your AI would do next:")
    print("  1. Read each envelope from the queue")
    print("  2. Evaluate priority and relevance")
    print("  3. Decide when/how to notify you")
    print("  4. Take action based on the prompt and context")
    print()
    print("Examples:")
    print("  - Coffee promotion → Low priority → Whisper when near store")
    print("  - App rejection → High priority → Alert immediately, analyze")
    print()


if __name__ == "__main__":
    main()
