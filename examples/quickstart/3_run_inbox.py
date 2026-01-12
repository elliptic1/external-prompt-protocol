#!/usr/bin/env python3
"""
Step 3: Run the EPP Inbox Server

This script starts a FastAPI server that:
1. Listens for incoming EPP envelopes
2. Verifies cryptographic signatures
3. Checks the trust registry
4. Applies rate limits and policies
5. Queues accepted prompts for your AI

The inbox is YOUR server - it runs on your infrastructure
and only accepts prompts from senders YOU trust.

Run this after:
- 1_setup.py (generates keys)
- 2_configure_inbox.py (sets up trust registry)

Keep this running while senders submit envelopes.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

import yaml
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from epp.crypto.keys import KeyPair
from epp.models import Envelope, SuccessReceipt, ErrorReceipt
from epp.inbox.processor import InboxProcessor
from epp.policy.trust_registry import TrustRegistry
from epp.policy.nonce_registry import NonceRegistry
from epp.policy.rate_limiter import RateLimiter
from epp.executors.file_queue import FileQueueExecutor


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("epp.inbox")


def load_config() -> dict:
    """Load configuration from config.yaml"""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="EPP Inbox",
        description="External Prompt Protocol inbox server",
        version="1.0.0",
    )

    # Load configuration
    config = load_config()
    base_dir = Path(__file__).parent

    # Resolve paths relative to script directory
    keys_dir = base_dir / "keys"
    data_dir = base_dir / "data"
    queue_dir = data_dir / "queue"

    # Ensure directories exist
    data_dir.mkdir(exist_ok=True)
    queue_dir.mkdir(exist_ok=True)

    # Load inbox keys
    private_key_path = keys_dir / "inbox.key"
    public_key_path = keys_dir / "inbox.pub"

    if not private_key_path.exists():
        raise RuntimeError(
            f"Inbox private key not found: {private_key_path}\n"
            "Run 1_setup.py first to generate keys."
        )

    with open(private_key_path, "rb") as f:
        inbox_keypair = KeyPair.from_private_pem(f.read())

    inbox_pubkey = inbox_keypair.public_key_hex()
    logger.info(f"Inbox public key: {inbox_pubkey[:32]}...")

    # Load trust registry
    trust_registry = TrustRegistry(
        storage_path=str(data_dir / "trust_registry.json")
    )
    trust_registry.load()
    logger.info(f"Loaded {len(list(trust_registry.list_senders()))} trusted senders")

    # Create nonce registry (replay protection)
    nonce_registry = NonceRegistry()

    # Create rate limiter
    rate_limiter = RateLimiter()

    # Create executor (what happens when an envelope is accepted)
    executor = FileQueueExecutor(queue_dir=str(queue_dir))

    # Create inbox processor
    processor = InboxProcessor(
        recipient_public_key_hex=inbox_pubkey,
        trust_registry=trust_registry,
        nonce_registry=nonce_registry,
        rate_limiter=rate_limiter,
        executor=executor,
    )

    @app.get("/")
    async def root():
        """Health check endpoint."""
        return {
            "service": "EPP Inbox",
            "status": "running",
            "inbox_public_key": inbox_pubkey,
            "submit_endpoint": "/epp/v1/submit",
        }

    @app.get("/health")
    async def health():
        """Health check for monitoring."""
        return {"status": "healthy"}

    @app.post("/epp/v1/submit")
    async def submit_envelope(request: Request):
        """
        Submit an EPP envelope.

        The envelope is validated through this pipeline:
        1. Parse JSON structure
        2. Check version compatibility
        3. Verify recipient matches this inbox
        4. Check expiration
        5. Verify cryptographic signature
        6. Check for replay (nonce)
        7. Verify sender is trusted
        8. Check scope policy
        9. Check size limits
        10. Check rate limits
        11. Execute (queue for AI)
        """
        try:
            # Parse request body
            body = await request.json()

            # Process the envelope
            result = processor.process_envelope(body)

            if isinstance(result, SuccessReceipt):
                logger.info(
                    f"Accepted envelope {result.envelope_id} "
                    f"from {body.get('sender', 'unknown')[:16]}..."
                )
                return JSONResponse(
                    status_code=200,
                    content=result.model_dump(mode="json"),
                )
            else:
                logger.warning(
                    f"Rejected envelope: {result.error.code} - {result.error.message}"
                )
                # Map error codes to HTTP status
                status_map = {
                    "INVALID_FORMAT": 400,
                    "UNSUPPORTED_VERSION": 400,
                    "WRONG_RECIPIENT": 400,
                    "EXPIRED": 400,
                    "INVALID_SIGNATURE": 401,
                    "REPLAY_DETECTED": 400,
                    "UNTRUSTED_SENDER": 403,
                    "POLICY_DENIED": 403,
                    "SIZE_EXCEEDED": 400,
                    "RATE_LIMITED": 429,
                }
                status = status_map.get(result.error.code, 400)
                return JSONResponse(
                    status_code=status,
                    content=result.model_dump(mode="json"),
                )

        except Exception as e:
            logger.exception("Error processing envelope")
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "error_code": "INTERNAL_ERROR",
                    "message": str(e),
                },
            )

    return app


def main():
    """Run the inbox server."""
    print()
    print("=" * 60)
    print("EPP Inbox Server")
    print("=" * 60)
    print()

    config = load_config()
    host = config["inbox"]["host"]
    port = config["inbox"]["port"]

    # Load and display inbox public key
    keys_dir = Path(__file__).parent / "keys"
    public_key_path = keys_dir / "inbox.pub"

    if public_key_path.exists():
        inbox_pubkey = public_key_path.read_text().strip()
        print(f"Inbox public key: {inbox_pubkey}")
        print()

    print(f"Starting server on http://{host}:{port}")
    print(f"Submit endpoint: http://{host}:{port}/epp/v1/submit")
    print()
    print("Waiting for envelopes...")
    print("Press Ctrl+C to stop")
    print("=" * 60)
    print()

    # Create and run the app
    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
