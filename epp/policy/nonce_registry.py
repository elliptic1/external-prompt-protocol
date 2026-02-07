"""
Nonce registry for replay attack prevention.
"""

import time
from datetime import datetime
from typing import Dict


class NonceRegistry:
    """
    Registry for tracking used nonces to prevent replay attacks.

    Nonces are stored with their expiration times and periodically garbage collected.
    """

    def __init__(self, cleanup_interval: int = 300) -> None:
        """
        Initialize nonce registry.

        Args:
            cleanup_interval: Seconds between garbage collection runs (default: 5 minutes)
        """
        # Map of nonce -> expiration timestamp
        self.nonces: Dict[str, float] = {}
        self.cleanup_interval = cleanup_interval
        self.last_cleanup = time.time()

    def has_seen(self, nonce: str) -> bool:
        """
        Check if a nonce has been seen before.

        Args:
            nonce: The nonce to check

        Returns:
            True if nonce has been seen, False otherwise
        """
        self._cleanup_if_needed()
        return nonce in self.nonces

    def add(self, nonce: str, expires_at: str) -> None:
        """
        Add a nonce to the registry.

        Args:
            nonce: The nonce to add
            expires_at: ISO-8601 expiration time

        Raises:
            ValueError: If nonce has already been seen
        """
        if self.has_seen(nonce):
            raise ValueError(f"Nonce has already been seen: {nonce}")

        # Convert expiration to timestamp
        expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        expires_ts = expires_dt.timestamp()

        self.nonces[nonce] = expires_ts

    def remove(self, nonce: str) -> None:
        """
        Remove a nonce from the registry.

        Args:
            nonce: The nonce to remove
        """
        self.nonces.pop(nonce, None)

    def cleanup_expired(self) -> int:
        """
        Remove all expired nonces from the registry.

        Returns:
            Number of nonces removed
        """
        now = time.time()
        expired = [nonce for nonce, exp_ts in self.nonces.items() if exp_ts <= now]

        for nonce in expired:
            del self.nonces[nonce]

        self.last_cleanup = now
        return len(expired)

    def _cleanup_if_needed(self) -> None:
        """Run cleanup if interval has passed."""
        if time.time() - self.last_cleanup >= self.cleanup_interval:
            self.cleanup_expired()

    def size(self) -> int:
        """Get the number of nonces currently stored."""
        return len(self.nonces)

    def clear(self) -> None:
        """Clear all nonces from the registry."""
        self.nonces.clear()
        self.last_cleanup = time.time()
