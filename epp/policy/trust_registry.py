"""
Trust registry for managing trusted senders and their policies.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class RateLimit(BaseModel):
    """Rate limiting configuration."""

    max_per_hour: Optional[int] = Field(default=None, ge=0)
    max_per_day: Optional[int] = Field(default=None, ge=0)


class SenderPolicy(BaseModel):
    """Policy for a trusted sender."""

    allowed_scopes: List[str] = Field(
        default_factory=list, description="List of allowed scopes, or ['*'] for all"
    )
    max_envelope_size: int = Field(
        default=10 * 1024 * 1024, ge=0, description="Maximum envelope size in bytes"
    )
    rate_limit: RateLimit = Field(default_factory=RateLimit)

    def allows_scope(self, scope: str) -> bool:
        """Check if a scope is allowed by this policy."""
        return "*" in self.allowed_scopes or scope in self.allowed_scopes

    def allows_size(self, size_bytes: int) -> bool:
        """Check if an envelope size is allowed."""
        return size_bytes <= self.max_envelope_size


class TrustEntry(BaseModel):
    """Entry in the trust registry."""

    public_key: str = Field(..., description="Sender's public key (hex)")
    name: str = Field(..., description="Human-readable name for the sender")
    added_at: str = Field(..., description="ISO-8601 timestamp when trust was added")
    policy: SenderPolicy = Field(default_factory=SenderPolicy)


class TrustRegistry:
    """Manages trusted senders and their policies."""

    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize trust registry.

        Args:
            storage_path: Path to JSON file for persistent storage (optional)
        """
        self.storage_path = storage_path
        self.trusted_senders: Dict[str, TrustEntry] = {}
        if storage_path and os.path.exists(storage_path):
            self.load()

    def add_sender(
        self,
        public_key: str,
        name: str,
        policy: Optional[SenderPolicy] = None,
    ) -> TrustEntry:
        """
        Add a trusted sender to the registry.

        Args:
            public_key: Sender's public key (hex)
            name: Human-readable name
            policy: Sender policy (uses default if not provided)

        Returns:
            The created trust entry
        """
        public_key = public_key.lower()

        if public_key in self.trusted_senders:
            raise ValueError(f"Sender {public_key} is already trusted")

        entry = TrustEntry(
            public_key=public_key,
            name=name,
            added_at=datetime.utcnow().isoformat() + "Z",
            policy=policy or SenderPolicy(),
        )

        self.trusted_senders[public_key] = entry
        if self.storage_path:
            self.save()

        return entry

    def remove_sender(self, public_key: str) -> None:
        """
        Remove a sender from the trust registry.

        Args:
            public_key: Sender's public key (hex)
        """
        public_key = public_key.lower()

        if public_key not in self.trusted_senders:
            raise ValueError(f"Sender {public_key} is not trusted")

        del self.trusted_senders[public_key]
        if self.storage_path:
            self.save()

    def get_sender(self, public_key: str) -> Optional[TrustEntry]:
        """
        Get a trust entry for a sender.

        Args:
            public_key: Sender's public key (hex)

        Returns:
            Trust entry if found, None otherwise
        """
        public_key = public_key.lower()
        return self.trusted_senders.get(public_key)

    def is_trusted(self, public_key: str) -> bool:
        """
        Check if a sender is trusted.

        Args:
            public_key: Sender's public key (hex)

        Returns:
            True if sender is trusted, False otherwise
        """
        return self.get_sender(public_key) is not None

    def list_senders(self) -> List[TrustEntry]:
        """List all trusted senders."""
        return list(self.trusted_senders.values())

    def save(self) -> None:
        """Save trust registry to file."""
        if not self.storage_path:
            raise ValueError("No storage path configured")

        # Ensure directory exists
        Path(self.storage_path).parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": "1",
            "senders": [entry.model_dump() for entry in self.trusted_senders.values()],
        }

        with open(self.storage_path, "w") as f:
            json.dump(data, f, indent=2)

        # Restrict permissions
        os.chmod(self.storage_path, 0o600)

    def load(self) -> None:
        """Load trust registry from file."""
        if not self.storage_path:
            raise ValueError("No storage path configured")

        with open(self.storage_path, "r") as f:
            data = json.load(f)

        if data.get("version") != "1":
            raise ValueError(f"Unsupported trust registry version: {data.get('version')}")

        self.trusted_senders = {}
        for sender_data in data.get("senders", []):
            entry = TrustEntry(**sender_data)
            self.trusted_senders[entry.public_key.lower()] = entry
