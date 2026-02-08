"""
Content integrity verification for EPP envelopes.

Provides cryptographic hashing to verify payload hasn't been modified.
"""

import hashlib
import json
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# Supported hash algorithms
SUPPORTED_ALGORITHMS = ("sha256", "sha384", "sha512")
HashAlgorithm = Literal["sha256", "sha384", "sha512"]


class Integrity(BaseModel):
    """Content integrity hash for EPP envelope payloads."""

    alg: HashAlgorithm = Field(
        default="sha256",
        description="Hash algorithm (sha256, sha384, sha512)",
    )
    hash: str = Field(
        ...,
        description="Hex-encoded hash of the payload",
    )

    @field_validator("alg")
    @classmethod
    def validate_algorithm(cls, v: str) -> str:
        """Validate hash algorithm is supported."""
        if v not in SUPPORTED_ALGORITHMS:
            raise ValueError(f"Unsupported algorithm: {v}. Must be one of {SUPPORTED_ALGORITHMS}")
        return v

    @field_validator("hash")
    @classmethod
    def validate_hash_format(cls, v: str) -> str:
        """Validate hash is lowercase hexadecimal."""
        v = v.lower()
        if not all(c in "0123456789abcdef" for c in v):
            raise ValueError("Hash must be hexadecimal")
        return v


def compute_payload_hash(
    payload: Dict[str, Any],
    algorithm: HashAlgorithm = "sha256",
) -> str:
    """
    Compute hash of a payload dictionary.
    
    Args:
        payload: The payload dict to hash
        algorithm: Hash algorithm to use (sha256, sha384, sha512)
        
    Returns:
        Hex-encoded hash string
    """
    if algorithm not in SUPPORTED_ALGORITHMS:
        raise ValueError(f"Unsupported algorithm: {algorithm}")
    
    # Canonical JSON: sorted keys, no whitespace, ensure_ascii for reproducibility
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    payload_bytes = canonical_json.encode("utf-8")
    
    hasher = hashlib.new(algorithm)
    hasher.update(payload_bytes)
    return hasher.hexdigest()


def create_integrity(
    payload: Dict[str, Any],
    algorithm: HashAlgorithm = "sha256",
) -> Integrity:
    """
    Create an Integrity object for a payload.
    
    Args:
        payload: The payload dict to hash
        algorithm: Hash algorithm to use
        
    Returns:
        Integrity object with algorithm and hash
    """
    hash_value = compute_payload_hash(payload, algorithm)
    return Integrity(alg=algorithm, hash=hash_value)


def verify_integrity(
    payload: Dict[str, Any],
    integrity: Integrity,
) -> bool:
    """
    Verify payload matches the integrity hash.
    
    Args:
        payload: The payload dict to verify
        integrity: The Integrity object to check against
        
    Returns:
        True if hash matches, False otherwise
    """
    computed_hash = compute_payload_hash(payload, integrity.alg)
    return computed_hash == integrity.hash.lower()


def integrity_from_dict(data: Dict[str, Any]) -> Optional[Integrity]:
    """
    Create Integrity from a dict (for parsing envelopes).
    
    Args:
        data: Dict with 'alg' and 'hash' keys
        
    Returns:
        Integrity object or None if data is None
    """
    if data is None:
        return None
    return Integrity(**data)
