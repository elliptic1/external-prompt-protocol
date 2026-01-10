#!/usr/bin/env python3
"""
EPP Policy Example: Demonstrate policy enforcement.

This example shows:
1. Trust registry management
2. Policy configuration
3. Rate limiting
4. Scope restrictions
"""

from epp.policy.trust_registry import RateLimit, SenderPolicy, TrustRegistry
from epp.policy.rate_limiter import RateLimiter
from epp.crypto.keys import KeyPair


def main():
    print("EPP Policy Example")
    print("=" * 50)

    # Step 1: Create trust registry
    print("\n1. Creating trust registry...")
    registry = TrustRegistry()  # In-memory

    # Generate some sender keys
    sender1 = KeyPair.generate()
    sender2 = KeyPair.generate()
    sender3 = KeyPair.generate()

    # Step 2: Add senders with different policies
    print("\n2. Adding trusted senders with policies...")

    # Sender 1: Unlimited, all scopes
    print("\n   Sender 1: Unlimited access")
    policy1 = SenderPolicy(
        allowed_scopes=["*"],
        max_envelope_size=10 * 1024 * 1024,
        rate_limit=RateLimit(max_per_hour=None, max_per_day=None),
    )
    registry.add_sender(
        public_key=sender1.public_key_hex(),
        name="Unlimited Sender",
        policy=policy1,
    )
    print(f"      Public key: {sender1.public_key_hex()[:32]}...")
    print(f"      Scopes: {policy1.allowed_scopes}")
    print(f"      Rate limit: None")

    # Sender 2: Limited scopes, moderate rate limits
    print("\n   Sender 2: Limited scopes and rates")
    policy2 = SenderPolicy(
        allowed_scopes=["notifications", "support"],
        max_envelope_size=1 * 1024 * 1024,
        rate_limit=RateLimit(max_per_hour=50, max_per_day=500),
    )
    registry.add_sender(
        public_key=sender2.public_key_hex(),
        name="Moderate Sender",
        policy=policy2,
    )
    print(f"      Public key: {sender2.public_key_hex()[:32]}...")
    print(f"      Scopes: {policy2.allowed_scopes}")
    print(f"      Rate limit: 50/hour, 500/day")

    # Sender 3: Very restrictive
    print("\n   Sender 3: Highly restrictive")
    policy3 = SenderPolicy(
        allowed_scopes=["alerts"],
        max_envelope_size=100 * 1024,
        rate_limit=RateLimit(max_per_hour=5, max_per_day=20),
    )
    registry.add_sender(
        public_key=sender3.public_key_hex(),
        name="Restricted Sender",
        policy=policy3,
    )
    print(f"      Public key: {sender3.public_key_hex()[:32]}...")
    print(f"      Scopes: {policy3.allowed_scopes}")
    print(f"      Rate limit: 5/hour, 20/day")

    # Step 3: Test scope enforcement
    print("\n3. Testing scope enforcement...")
    entry2 = registry.get_sender(sender2.public_key_hex())

    test_scopes = ["notifications", "support", "code-review", "alerts"]
    for scope in test_scopes:
        allowed = entry2.policy.allows_scope(scope)
        status = "✓" if allowed else "✗"
        print(f"   {status} Scope '{scope}': {'allowed' if allowed else 'denied'}")

    # Step 4: Test size enforcement
    print("\n4. Testing size enforcement...")
    test_sizes = [50_000, 500_000, 1_000_000, 2_000_000]
    for size in test_sizes:
        allowed = entry2.policy.allows_size(size)
        status = "✓" if allowed else "✗"
        print(f"   {status} Size {size:,} bytes: {'allowed' if allowed else 'denied'}")

    # Step 5: Test rate limiting
    print("\n5. Testing rate limiting...")
    rate_limiter = RateLimiter()

    sender_key = sender3.public_key_hex()
    max_hour = policy3.rate_limit.max_per_hour
    max_day = policy3.rate_limit.max_per_day

    print(f"   Rate limit: {max_hour}/hour, {max_day}/day")

    # Simulate requests
    for i in range(7):
        allowed, reason = rate_limiter.check_and_record(sender_key, max_hour, max_day)
        status = "✓" if allowed else "✗"
        if allowed:
            stats = rate_limiter.get_stats(sender_key)
            print(
                f"   {status} Request {i+1}: accepted "
                f"(hour: {stats['last_hour']}/{max_hour}, day: {stats['last_day']}/{max_day})"
            )
        else:
            print(f"   {status} Request {i+1}: rejected - {reason}")

    # Step 6: List all senders
    print("\n6. Trust registry summary:")
    print("-" * 50)
    for entry in registry.list_senders():
        print(f"\n   {entry.name}")
        print(f"   Public key: {entry.public_key[:32]}...")
        print(f"   Scopes: {', '.join(entry.policy.allowed_scopes)}")
        print(f"   Max size: {entry.policy.max_envelope_size:,} bytes")
        if entry.policy.rate_limit.max_per_hour:
            print(f"   Max/hour: {entry.policy.rate_limit.max_per_hour}")
        if entry.policy.rate_limit.max_per_day:
            print(f"   Max/day: {entry.policy.rate_limit.max_per_day}")
        print(f"   Added: {entry.added_at}")

    print("\n" + "=" * 50)
    print("✓ Policy example completed!")


if __name__ == "__main__":
    main()
