"""
Rate limiting for EPP envelopes.
"""

import time
from collections import defaultdict, deque
from typing import Dict, Optional, Tuple


class RateLimiter:
    """
    Token bucket rate limiter for EPP envelopes.

    Tracks requests per sender and enforces hourly and daily limits.
    """

    def __init__(self) -> None:
        """Initialize rate limiter."""
        # Store timestamps of accepted envelopes per sender
        self.requests: Dict[str, deque[float]] = defaultdict(deque)

    def check_and_record(
        self,
        sender_key: str,
        max_per_hour: Optional[int],
        max_per_day: Optional[int],
    ) -> Tuple[bool, str]:
        """
        Check if sender has exceeded rate limits and record this request.

        Args:
            sender_key: Sender's public key
            max_per_hour: Maximum requests per hour (None = no limit)
            max_per_day: Maximum requests per day (None = no limit)

        Returns:
            Tuple of (allowed, reason)
            - allowed: True if request is within limits
            - reason: Description if denied, empty string if allowed
        """
        now = time.time()
        sender_key = sender_key.lower()

        # Get request history for this sender
        history = self.requests[sender_key]

        # Clean up old entries (older than 24 hours)
        cutoff_24h = now - 86400  # 24 hours
        while history and history[0] < cutoff_24h:
            history.popleft()

        # Count requests in last hour and last day
        cutoff_1h = now - 3600  # 1 hour
        count_1h = sum(1 for ts in history if ts >= cutoff_1h)
        count_24h = len(history)

        # Check hourly limit
        if max_per_hour is not None and count_1h >= max_per_hour:
            return False, f"Hourly rate limit exceeded ({count_1h}/{max_per_hour})"

        # Check daily limit
        if max_per_day is not None and count_24h >= max_per_day:
            return False, f"Daily rate limit exceeded ({count_24h}/{max_per_day})"

        # Record this request
        history.append(now)

        return True, ""

    def reset_sender(self, sender_key: str) -> None:
        """
        Reset rate limit tracking for a sender.

        Args:
            sender_key: Sender's public key
        """
        sender_key = sender_key.lower()
        if sender_key in self.requests:
            del self.requests[sender_key]

    def get_stats(self, sender_key: str) -> Dict[str, int]:
        """
        Get rate limit statistics for a sender.

        Args:
            sender_key: Sender's public key

        Returns:
            Dictionary with 'last_hour' and 'last_day' counts
        """
        now = time.time()
        sender_key = sender_key.lower()
        history = self.requests.get(sender_key, deque())

        cutoff_1h = now - 3600
        cutoff_24h = now - 86400

        # Clean history
        while history and history[0] < cutoff_24h:
            history.popleft()

        count_1h = sum(1 for ts in history if ts >= cutoff_1h)
        count_24h = len(history)

        return {"last_hour": count_1h, "last_day": count_24h}
