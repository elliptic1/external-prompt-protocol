"""
Envelope signing and verification for EPP.
"""

import base64
import json
from typing import Any, Dict
from cryptography.exceptions import InvalidSignature

from .keys import KeyPair, PublicKey


def create_canonical_payload(
    version: str,
    envelope_id: str,
    sender: str,
    recipient: str,
    timestamp: str,
    expires_at: str,
    nonce: str,
    scope: str,
    payload: Dict[str, Any],
) -> bytes:
    """
    Create the canonical signing payload for an EPP envelope.

    Fields are concatenated with newline separators in the specified order.
    The payload object is serialized as compact JSON.
    """
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)

    canonical_parts = [
        version,
        envelope_id,
        sender,
        recipient,
        timestamp,
        expires_at,
        nonce,
        scope,
        payload_json,
    ]

    return "\n".join(canonical_parts).encode("utf-8")


def sign_envelope(
    key_pair: KeyPair,
    version: str,
    envelope_id: str,
    sender: str,
    recipient: str,
    timestamp: str,
    expires_at: str,
    nonce: str,
    scope: str,
    payload: Dict[str, Any],
) -> str:
    """
    Sign an EPP envelope and return the base64-encoded signature.

    Args:
        key_pair: Sender's key pair
        version: Protocol version
        envelope_id: Unique envelope identifier
        sender: Sender's public key (hex)
        recipient: Recipient's public key (hex)
        timestamp: ISO-8601 timestamp
        expires_at: ISO-8601 expiration time
        nonce: Base64-encoded random nonce
        scope: Scope identifier
        payload: Payload dictionary

    Returns:
        Base64-encoded signature
    """
    canonical = create_canonical_payload(
        version, envelope_id, sender, recipient, timestamp, expires_at, nonce, scope, payload
    )

    signature = key_pair.private_key.sign(canonical)
    return base64.b64encode(signature).decode("ascii")


def verify_envelope_signature(
    public_key: PublicKey,
    signature_b64: str,
    version: str,
    envelope_id: str,
    sender: str,
    recipient: str,
    timestamp: str,
    expires_at: str,
    nonce: str,
    scope: str,
    payload: Dict[str, Any],
) -> bool:
    """
    Verify an EPP envelope signature.

    Args:
        public_key: Sender's public key
        signature_b64: Base64-encoded signature
        version: Protocol version
        envelope_id: Unique envelope identifier
        sender: Sender's public key (hex)
        recipient: Recipient's public key (hex)
        timestamp: ISO-8601 timestamp
        expires_at: ISO-8601 expiration time
        nonce: Base64-encoded random nonce
        scope: Scope identifier
        payload: Payload dictionary

    Returns:
        True if signature is valid, False otherwise
    """
    try:
        canonical = create_canonical_payload(
            version, envelope_id, sender, recipient, timestamp, expires_at, nonce, scope, payload
        )

        signature = base64.b64decode(signature_b64)
        public_key.public_key.verify(signature, canonical)
        return True
    except (InvalidSignature, ValueError, Exception):
        return False


def generate_nonce(length: int = 16) -> str:
    """
    Generate a cryptographically random nonce.

    Args:
        length: Number of random bytes (default: 16)

    Returns:
        Base64-encoded nonce
    """
    import os

    random_bytes = os.urandom(length)
    return base64.b64encode(random_bytes).decode("ascii")
