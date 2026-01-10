"""
Tests for policy enforcement components.
"""

import time
from datetime import datetime

import pytest

from epp.policy.nonce_registry import NonceRegistry
from epp.policy.rate_limiter import RateLimiter
from epp.policy.trust_registry import SenderPolicy, TrustRegistry


class TestNonceRegistry:
    """Tests for NonceRegistry."""

    def test_add_and_check_nonce(self):
        """Test adding and checking nonces."""
        registry = NonceRegistry()
        nonce = "test-nonce-123"
        expires_at = "2024-01-01T01:00:00Z"

        assert registry.has_seen(nonce) is False

        registry.add(nonce, expires_at)
        assert registry.has_seen(nonce) is True

    def test_duplicate_nonce_rejected(self):
        """Test duplicate nonce is rejected."""
        registry = NonceRegistry()
        nonce = "test-nonce-123"
        expires_at = "2024-01-01T01:00:00Z"

        registry.add(nonce, expires_at)

        with pytest.raises(ValueError):
            registry.add(nonce, expires_at)

    def test_cleanup_expired(self):
        """Test cleanup of expired nonces."""
        registry = NonceRegistry()

        # Add expired nonce
        past = "2020-01-01T00:00:00Z"
        registry.add("expired-nonce", past)

        # Add future nonce
        future = "2030-01-01T00:00:00Z"
        registry.add("future-nonce", future)

        assert registry.size() == 2

        # Cleanup
        removed = registry.cleanup_expired()
        assert removed >= 1
        assert registry.has_seen("future-nonce") is True
        assert registry.has_seen("expired-nonce") is False


class TestRateLimiter:
    """Tests for RateLimiter."""

    def test_within_hourly_limit(self):
        """Test requests within hourly limit are allowed."""
        limiter = RateLimiter()
        sender = "test-sender"

        allowed, reason = limiter.check_and_record(sender, max_per_hour=10, max_per_day=100)
        assert allowed is True
        assert reason == ""

    def test_exceed_hourly_limit(self):
        """Test exceeding hourly limit is blocked."""
        limiter = RateLimiter()
        sender = "test-sender"

        # Make 5 requests
        for _ in range(5):
            allowed, _ = limiter.check_and_record(sender, max_per_hour=5, max_per_day=100)
            assert allowed is True

        # 6th request should be blocked
        allowed, reason = limiter.check_and_record(sender, max_per_hour=5, max_per_day=100)
        assert allowed is False
        assert "Hourly" in reason

    def test_exceed_daily_limit(self):
        """Test exceeding daily limit is blocked."""
        limiter = RateLimiter()
        sender = "test-sender"

        # Make 3 requests
        for _ in range(3):
            allowed, _ = limiter.check_and_record(sender, max_per_hour=None, max_per_day=3)
            assert allowed is True

        # 4th request should be blocked
        allowed, reason = limiter.check_and_record(sender, max_per_hour=None, max_per_day=3)
        assert allowed is False
        assert "Daily" in reason

    def test_no_limits(self):
        """Test no limits allows all requests."""
        limiter = RateLimiter()
        sender = "test-sender"

        for _ in range(1000):
            allowed, _ = limiter.check_and_record(sender, max_per_hour=None, max_per_day=None)
            assert allowed is True

    def test_get_stats(self):
        """Test getting rate limit statistics."""
        limiter = RateLimiter()
        sender = "test-sender"

        limiter.check_and_record(sender, None, None)
        limiter.check_and_record(sender, None, None)

        stats = limiter.get_stats(sender)
        assert stats["last_hour"] == 2
        assert stats["last_day"] == 2


class TestSenderPolicy:
    """Tests for SenderPolicy."""

    def test_allows_scope_wildcard(self):
        """Test wildcard scope allows all."""
        policy = SenderPolicy(allowed_scopes=["*"])
        assert policy.allows_scope("any-scope") is True
        assert policy.allows_scope("another-scope") is True

    def test_allows_scope_specific(self):
        """Test specific scopes."""
        policy = SenderPolicy(allowed_scopes=["scope1", "scope2"])
        assert policy.allows_scope("scope1") is True
        assert policy.allows_scope("scope2") is True
        assert policy.allows_scope("scope3") is False

    def test_allows_size(self):
        """Test size limits."""
        policy = SenderPolicy(max_envelope_size=1000)
        assert policy.allows_size(500) is True
        assert policy.allows_size(1000) is True
        assert policy.allows_size(1001) is False


class TestTrustRegistry:
    """Tests for TrustRegistry."""

    def test_add_sender(self, tmp_path):
        """Test adding a sender."""
        registry_file = tmp_path / "registry.json"
        registry = TrustRegistry(storage_path=str(registry_file))

        entry = registry.add_sender(
            public_key="a" * 64,
            name="Test Sender",
        )

        assert entry.public_key == "a" * 64
        assert entry.name == "Test Sender"
        assert registry.is_trusted("a" * 64) is True

    def test_duplicate_sender_rejected(self, tmp_path):
        """Test duplicate sender is rejected."""
        registry_file = tmp_path / "registry.json"
        registry = TrustRegistry(storage_path=str(registry_file))

        registry.add_sender(public_key="a" * 64, name="Test")

        with pytest.raises(ValueError):
            registry.add_sender(public_key="a" * 64, name="Duplicate")

    def test_remove_sender(self, tmp_path):
        """Test removing a sender."""
        registry_file = tmp_path / "registry.json"
        registry = TrustRegistry(storage_path=str(registry_file))

        registry.add_sender(public_key="a" * 64, name="Test")
        assert registry.is_trusted("a" * 64) is True

        registry.remove_sender("a" * 64)
        assert registry.is_trusted("a" * 64) is False

    def test_save_and_load(self, tmp_path):
        """Test saving and loading registry."""
        registry_file = tmp_path / "registry.json"

        # Create and save
        registry1 = TrustRegistry(storage_path=str(registry_file))
        registry1.add_sender(public_key="a" * 64, name="Test Sender")

        # Load in new instance
        registry2 = TrustRegistry(storage_path=str(registry_file))
        assert registry2.is_trusted("a" * 64) is True
        entry = registry2.get_sender("a" * 64)
        assert entry.name == "Test Sender"

    def test_case_insensitive_keys(self, tmp_path):
        """Test public keys are case-insensitive."""
        registry_file = tmp_path / "registry.json"
        registry = TrustRegistry(storage_path=str(registry_file))

        registry.add_sender(public_key="A" * 64, name="Test")
        assert registry.is_trusted("a" * 64) is True
        assert registry.is_trusted("A" * 64) is True
