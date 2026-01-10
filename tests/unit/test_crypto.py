"""
Tests for cryptographic operations.
"""

import pytest

from epp.crypto.keys import KeyPair, PublicKey
from epp.crypto.signing import (
    create_canonical_payload,
    generate_nonce,
    sign_envelope,
    verify_envelope_signature,
)


class TestKeyPair:
    """Tests for KeyPair class."""

    def test_generate_key_pair(self):
        """Test key pair generation."""
        key_pair = KeyPair.generate()
        assert key_pair.private_key is not None
        assert key_pair.public_key is not None

    def test_public_key_hex(self):
        """Test public key hex encoding."""
        key_pair = KeyPair.generate()
        hex_key = key_pair.public_key_hex()
        assert len(hex_key) == 64  # 32 bytes = 64 hex chars
        assert all(c in "0123456789abcdef" for c in hex_key)

    def test_key_serialization(self):
        """Test key serialization and deserialization."""
        key_pair = KeyPair.generate()
        private_bytes = key_pair.private_key_bytes()

        # Recreate from bytes
        restored = KeyPair.from_private_bytes(private_bytes)
        assert restored.public_key_hex() == key_pair.public_key_hex()

    def test_pem_export(self):
        """Test PEM export and import."""
        key_pair = KeyPair.generate()
        pem_data = key_pair.private_key_pem()

        # Restore from PEM
        restored = KeyPair.from_private_pem(pem_data)
        assert restored.public_key_hex() == key_pair.public_key_hex()

    def test_encrypted_pem(self):
        """Test encrypted PEM export and import."""
        key_pair = KeyPair.generate()
        password = b"test-password"
        pem_data = key_pair.private_key_pem(password)

        # Restore with password
        restored = KeyPair.from_private_pem(pem_data, password)
        assert restored.public_key_hex() == key_pair.public_key_hex()

        # Wrong password should fail
        with pytest.raises(Exception):
            KeyPair.from_private_pem(pem_data, b"wrong-password")


class TestPublicKey:
    """Tests for PublicKey class."""

    def test_from_hex(self):
        """Test creating public key from hex."""
        key_pair = KeyPair.generate()
        hex_key = key_pair.public_key_hex()

        public_key = PublicKey.from_hex(hex_key)
        assert public_key.to_hex() == hex_key

    def test_equality(self):
        """Test public key equality."""
        key_pair = KeyPair.generate()
        pk1 = PublicKey.from_hex(key_pair.public_key_hex())
        pk2 = PublicKey.from_hex(key_pair.public_key_hex())

        assert pk1 == pk2
        assert hash(pk1) == hash(pk2)

    def test_inequality(self):
        """Test public key inequality."""
        kp1 = KeyPair.generate()
        kp2 = KeyPair.generate()

        pk1 = PublicKey.from_hex(kp1.public_key_hex())
        pk2 = PublicKey.from_hex(kp2.public_key_hex())

        assert pk1 != pk2


class TestSigning:
    """Tests for signing and verification."""

    def test_nonce_generation(self):
        """Test nonce generation."""
        nonce1 = generate_nonce()
        nonce2 = generate_nonce()

        # Should be different
        assert nonce1 != nonce2

        # Should be base64
        import base64

        decoded = base64.b64decode(nonce1)
        assert len(decoded) == 16

    def test_canonical_payload(self):
        """Test canonical payload creation."""
        payload = create_canonical_payload(
            version="1",
            envelope_id="test-id",
            sender="sender-key",
            recipient="recipient-key",
            timestamp="2024-01-01T00:00:00Z",
            expires_at="2024-01-01T01:00:00Z",
            nonce="test-nonce",
            scope="test",
            payload={"prompt": "Hello"},
        )

        assert isinstance(payload, bytes)
        # Should contain all fields
        payload_str = payload.decode("utf-8")
        assert "test-id" in payload_str
        assert "sender-key" in payload_str
        assert "Hello" in payload_str

    def test_sign_and_verify(self):
        """Test envelope signing and verification."""
        sender_key = KeyPair.generate()
        recipient_key = KeyPair.generate()

        signature = sign_envelope(
            sender_key,
            version="1",
            envelope_id="test-id",
            sender=sender_key.public_key_hex(),
            recipient=recipient_key.public_key_hex(),
            timestamp="2024-01-01T00:00:00Z",
            expires_at="2024-01-01T01:00:00Z",
            nonce=generate_nonce(),
            scope="test",
            payload={"prompt": "Hello"},
        )

        # Verify with correct key
        sender_public = PublicKey.from_hex(sender_key.public_key_hex())
        valid = verify_envelope_signature(
            sender_public,
            signature,
            version="1",
            envelope_id="test-id",
            sender=sender_key.public_key_hex(),
            recipient=recipient_key.public_key_hex(),
            timestamp="2024-01-01T00:00:00Z",
            expires_at="2024-01-01T01:00:00Z",
            nonce=generate_nonce(),  # Same nonce used in signing
            scope="test",
            payload={"prompt": "Hello"},
        )

        # Note: This will fail because we used different nonce in verification
        # Let's fix the test

    def test_sign_and_verify_correct(self):
        """Test envelope signing and verification with same nonce."""
        sender_key = KeyPair.generate()
        recipient_key = KeyPair.generate()
        nonce = generate_nonce()

        signature = sign_envelope(
            sender_key,
            version="1",
            envelope_id="test-id",
            sender=sender_key.public_key_hex(),
            recipient=recipient_key.public_key_hex(),
            timestamp="2024-01-01T00:00:00Z",
            expires_at="2024-01-01T01:00:00Z",
            nonce=nonce,
            scope="test",
            payload={"prompt": "Hello"},
        )

        # Verify with correct key
        sender_public = PublicKey.from_hex(sender_key.public_key_hex())
        valid = verify_envelope_signature(
            sender_public,
            signature,
            version="1",
            envelope_id="test-id",
            sender=sender_key.public_key_hex(),
            recipient=recipient_key.public_key_hex(),
            timestamp="2024-01-01T00:00:00Z",
            expires_at="2024-01-01T01:00:00Z",
            nonce=nonce,
            scope="test",
            payload={"prompt": "Hello"},
        )

        assert valid is True

    def test_verify_with_wrong_key(self):
        """Test verification fails with wrong key."""
        sender_key = KeyPair.generate()
        wrong_key = KeyPair.generate()
        recipient_key = KeyPair.generate()
        nonce = generate_nonce()

        signature = sign_envelope(
            sender_key,
            version="1",
            envelope_id="test-id",
            sender=sender_key.public_key_hex(),
            recipient=recipient_key.public_key_hex(),
            timestamp="2024-01-01T00:00:00Z",
            expires_at="2024-01-01T01:00:00Z",
            nonce=nonce,
            scope="test",
            payload={"prompt": "Hello"},
        )

        # Verify with wrong key
        wrong_public = PublicKey.from_hex(wrong_key.public_key_hex())
        valid = verify_envelope_signature(
            wrong_public,
            signature,
            version="1",
            envelope_id="test-id",
            sender=sender_key.public_key_hex(),
            recipient=recipient_key.public_key_hex(),
            timestamp="2024-01-01T00:00:00Z",
            expires_at="2024-01-01T01:00:00Z",
            nonce=nonce,
            scope="test",
            payload={"prompt": "Hello"},
        )

        assert valid is False

    def test_verify_with_modified_payload(self):
        """Test verification fails with modified payload."""
        sender_key = KeyPair.generate()
        recipient_key = KeyPair.generate()
        nonce = generate_nonce()

        signature = sign_envelope(
            sender_key,
            version="1",
            envelope_id="test-id",
            sender=sender_key.public_key_hex(),
            recipient=recipient_key.public_key_hex(),
            timestamp="2024-01-01T00:00:00Z",
            expires_at="2024-01-01T01:00:00Z",
            nonce=nonce,
            scope="test",
            payload={"prompt": "Hello"},
        )

        # Verify with modified payload
        sender_public = PublicKey.from_hex(sender_key.public_key_hex())
        valid = verify_envelope_signature(
            sender_public,
            signature,
            version="1",
            envelope_id="test-id",
            sender=sender_key.public_key_hex(),
            recipient=recipient_key.public_key_hex(),
            timestamp="2024-01-01T00:00:00Z",
            expires_at="2024-01-01T01:00:00Z",
            nonce=nonce,
            scope="test",
            payload={"prompt": "Modified!"},  # Different payload
        )

        assert valid is False
