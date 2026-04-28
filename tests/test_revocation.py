"""Tests for the v1.1 revocation module + processor integration."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from epp.crypto.keys import KeyPair
from epp.crypto.signing import generate_nonce, sign_envelope
from epp.executors.noop import NoOpExecutor
from epp.inbox.processor import InboxProcessor
from epp.models import Envelope, ErrorReceipt, Payload, SuccessReceipt
from epp.policy.nonce_registry import NonceRegistry
from epp.policy.rate_limiter import RateLimiter
from epp.policy.trust_registry import RateLimit, SenderPolicy, TrustRegistry
from epp.revocation import (
    RevocationCheck,
    RevocationLookup,
    RevocationStatus,
    revocation_check_from_dict,
)

# RevocationCheck shape ---------------------------------------------------- #


class TestRevocationCheck:
    def test_https_url_accepted(self):
        rc = RevocationCheck(registry="https://revoke.example/api", required=True)
        assert rc.registry == "https://revoke.example/api"
        assert rc.required is True

    def test_http_url_accepted(self):
        rc = RevocationCheck(registry="http://revoke.local")
        assert rc.registry.startswith("http://")

    def test_did_accepted(self):
        rc = RevocationCheck(registry="did:web:revoke.example")
        assert rc.registry.startswith("did:")

    def test_garbage_rejected(self):
        with pytest.raises(ValueError, match="DID or http"):
            RevocationCheck(registry="ftp://nope")

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            RevocationCheck(registry="   ")

    def test_required_default_true(self):
        rc = RevocationCheck(registry="https://x")
        assert rc.required is True

    def test_from_dict_round_trip(self):
        rc = RevocationCheck(registry="https://x", required=False)
        rebuilt = revocation_check_from_dict(rc.model_dump(exclude_none=True))
        assert rebuilt is not None
        assert rebuilt.required is False

    def test_from_dict_none(self):
        assert revocation_check_from_dict(None) is None


# Stub lookup -------------------------------------------------------------- #


class TestDefaultLookup:
    def test_default_returns_not_revoked(self):
        s = RevocationLookup().lookup("ab" * 32, "https://x")
        assert s.revoked is False
        assert s.source == "stub"


# Processor integration ---------------------------------------------------- #


class _FakeRevoker(RevocationLookup):
    """Returns whatever the test wants."""

    def __init__(self, revoked: bool = False, raises: bool = False):
        self._revoked = revoked
        self._raises = raises

    def lookup(self, sender_pubkey: str, registry: str) -> RevocationStatus:
        if self._raises:
            raise RuntimeError("simulated registry outage")
        return RevocationStatus(
            revoked=self._revoked,
            checked_at="2026-04-28T00:00:00Z",
            source="fake",
            reason="test" if self._revoked else None,
        )


def _build_envelope(
    sender_kp: KeyPair,
    recipient_pubkey_hex: str,
    *,
    revocation_check: RevocationCheck = None,
):
    now = datetime.now(timezone.utc)
    payload = Payload(prompt="hello")
    envelope_id = str(uuid4())
    ts = now.isoformat().replace("+00:00", "Z")
    exp = (now + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    nonce = generate_nonce()

    sig = sign_envelope(
        sender_kp,
        version="1",
        envelope_id=envelope_id,
        sender=sender_kp.public_key_hex(),
        recipient=recipient_pubkey_hex,
        timestamp=ts,
        expires_at=exp,
        nonce=nonce,
        scope="demo-echo",
        payload=payload.model_dump(exclude_none=True),
    )
    env = Envelope(
        version="1",
        envelope_id=envelope_id,
        sender=sender_kp.public_key_hex(),
        recipient=recipient_pubkey_hex,
        timestamp=ts,
        expires_at=exp,
        nonce=nonce,
        scope="demo-echo",
        payload=payload,
        signature=sig,
        revocation_check=revocation_check,
    )
    return env.model_dump(exclude_none=True)


def _make_processor(
    sender_pubkey: str,
    recipient_pubkey: str,
    *,
    revocation_check_url: str = None,
    on_failure: str = "deny",
    revoker: RevocationLookup = None,
):
    trust = TrustRegistry()
    trust.add_sender(
        public_key=sender_pubkey,
        name="alice",
        policy=SenderPolicy(
            allowed_scopes=["*"],
            rate_limit=RateLimit(),
            revocation_check_url=revocation_check_url,
            revocation_on_failure=on_failure,
        ),
    )
    return InboxProcessor(
        recipient_public_key_hex=recipient_pubkey,
        trust_registry=trust,
        nonce_registry=NonceRegistry(),
        rate_limiter=RateLimiter(),
        executor=NoOpExecutor(),
        revocation_lookup=revoker,
    )


class TestProcessorRevocation:
    def test_no_policy_means_no_lookup_no_block(self):
        sender = KeyPair.generate()
        recipient = KeyPair.generate()
        proc = _make_processor(
            sender.public_key_hex(),
            recipient.public_key_hex(),
            revocation_check_url=None,
        )
        env = _build_envelope(sender, recipient.public_key_hex())
        receipt = proc.process_envelope(env)
        assert isinstance(receipt, SuccessReceipt)

    def test_policy_url_revoked_denies(self):
        sender = KeyPair.generate()
        recipient = KeyPair.generate()
        proc = _make_processor(
            sender.public_key_hex(),
            recipient.public_key_hex(),
            revocation_check_url="https://revoker.test",
            on_failure="deny",
            revoker=_FakeRevoker(revoked=True),
        )
        env = _build_envelope(sender, recipient.public_key_hex())
        receipt = proc.process_envelope(env)
        assert isinstance(receipt, ErrorReceipt)
        assert receipt.error.code == "SENDER_REVOKED"

    def test_policy_url_revoked_log_only_passes(self):
        sender = KeyPair.generate()
        recipient = KeyPair.generate()
        proc = _make_processor(
            sender.public_key_hex(),
            recipient.public_key_hex(),
            revocation_check_url="https://revoker.test",
            on_failure="log-only",
            revoker=_FakeRevoker(revoked=True),
        )
        env = _build_envelope(sender, recipient.public_key_hex())
        receipt = proc.process_envelope(env)
        assert isinstance(receipt, SuccessReceipt)

    def test_policy_url_revoked_allow_passes(self):
        sender = KeyPair.generate()
        recipient = KeyPair.generate()
        proc = _make_processor(
            sender.public_key_hex(),
            recipient.public_key_hex(),
            revocation_check_url="https://revoker.test",
            on_failure="allow",
            revoker=_FakeRevoker(revoked=True),
        )
        env = _build_envelope(sender, recipient.public_key_hex())
        receipt = proc.process_envelope(env)
        assert isinstance(receipt, SuccessReceipt)

    def test_lookup_exception_with_deny_returns_error(self):
        sender = KeyPair.generate()
        recipient = KeyPair.generate()
        proc = _make_processor(
            sender.public_key_hex(),
            recipient.public_key_hex(),
            revocation_check_url="https://revoker.test",
            on_failure="deny",
            revoker=_FakeRevoker(raises=True),
        )
        env = _build_envelope(sender, recipient.public_key_hex())
        receipt = proc.process_envelope(env)
        assert isinstance(receipt, ErrorReceipt)
        assert receipt.error.code == "SENDER_REVOKED"

    def test_envelope_carried_check_required_triggers_lookup(self):
        sender = KeyPair.generate()
        recipient = KeyPair.generate()
        # No URL in policy, but envelope itself carries one with required=True
        proc = _make_processor(
            sender.public_key_hex(),
            recipient.public_key_hex(),
            revocation_check_url=None,
            on_failure="deny",
            revoker=_FakeRevoker(revoked=True),
        )
        env = _build_envelope(
            sender,
            recipient.public_key_hex(),
            revocation_check=RevocationCheck(registry="https://revoker.test", required=True),
        )
        receipt = proc.process_envelope(env)
        assert isinstance(receipt, ErrorReceipt)
        assert receipt.error.code == "SENDER_REVOKED"

    def test_envelope_carried_check_optional_does_not_trigger(self):
        sender = KeyPair.generate()
        recipient = KeyPair.generate()
        proc = _make_processor(
            sender.public_key_hex(),
            recipient.public_key_hex(),
            revocation_check_url=None,
            revoker=_FakeRevoker(revoked=True),
        )
        env = _build_envelope(
            sender,
            recipient.public_key_hex(),
            revocation_check=RevocationCheck(registry="https://revoker.test", required=False),
        )
        receipt = proc.process_envelope(env)
        assert isinstance(receipt, SuccessReceipt)
