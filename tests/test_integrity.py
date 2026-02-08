"""Tests for content integrity verification."""

import pytest

from epp.crypto.integrity import (
    Integrity,
    compute_payload_hash,
    create_integrity,
    verify_integrity,
)


class TestIntegrity:
    """Tests for Integrity model."""

    def test_create_integrity(self):
        """Test creating Integrity object."""
        integrity = Integrity(alg="sha256", hash="abcd1234")
        assert integrity.alg == "sha256"
        assert integrity.hash == "abcd1234"

    def test_supported_algorithms(self):
        """Test all supported algorithms."""
        for alg in ["sha256", "sha384", "sha512"]:
            integrity = Integrity(alg=alg, hash="abcd1234")
            assert integrity.alg == alg

    def test_invalid_algorithm(self):
        """Test rejection of invalid algorithm."""
        with pytest.raises(Exception):  # Pydantic raises ValidationError
            Integrity(alg="md5", hash="abcd1234")

    def test_hash_normalized_to_lowercase(self):
        """Test hash is normalized to lowercase."""
        integrity = Integrity(alg="sha256", hash="ABCD1234")
        assert integrity.hash == "abcd1234"


class TestComputePayloadHash:
    """Tests for compute_payload_hash function."""

    def test_compute_hash_sha256(self):
        """Test SHA256 hash computation."""
        payload = {"prompt": "Hello, world!", "context": None, "metadata": None}
        hash_value = compute_payload_hash(payload, "sha256")

        assert len(hash_value) == 64  # SHA256 produces 64 hex chars
        assert all(c in "0123456789abcdef" for c in hash_value)

    def test_compute_hash_sha512(self):
        """Test SHA512 hash computation."""
        payload = {"prompt": "Hello, world!"}
        hash_value = compute_payload_hash(payload, "sha512")

        assert len(hash_value) == 128  # SHA512 produces 128 hex chars

    def test_hash_is_deterministic(self):
        """Test that same payload produces same hash."""
        payload = {"prompt": "Test prompt", "context": {"key": "value"}}

        hash1 = compute_payload_hash(payload, "sha256")
        hash2 = compute_payload_hash(payload, "sha256")

        assert hash1 == hash2

    def test_hash_is_order_independent(self):
        """Test that dict key order doesn't affect hash."""
        payload1 = {"a": 1, "b": 2, "c": 3}
        payload2 = {"c": 3, "a": 1, "b": 2}

        hash1 = compute_payload_hash(payload1, "sha256")
        hash2 = compute_payload_hash(payload2, "sha256")

        assert hash1 == hash2

    def test_different_payloads_different_hashes(self):
        """Test that different payloads produce different hashes."""
        payload1 = {"prompt": "Hello"}
        payload2 = {"prompt": "World"}

        hash1 = compute_payload_hash(payload1, "sha256")
        hash2 = compute_payload_hash(payload2, "sha256")

        assert hash1 != hash2


class TestCreateIntegrity:
    """Tests for create_integrity function."""

    def test_create_integrity_default_algorithm(self):
        """Test creating Integrity with default algorithm."""
        payload = {"prompt": "Test"}
        integrity = create_integrity(payload)

        assert integrity.alg == "sha256"
        assert len(integrity.hash) == 64

    def test_create_integrity_custom_algorithm(self):
        """Test creating Integrity with custom algorithm."""
        payload = {"prompt": "Test"}
        integrity = create_integrity(payload, "sha512")

        assert integrity.alg == "sha512"
        assert len(integrity.hash) == 128


class TestVerifyIntegrity:
    """Tests for verify_integrity function."""

    def test_verify_valid_integrity(self):
        """Test verification of valid integrity."""
        payload = {"prompt": "Test prompt", "context": {"key": "value"}}
        integrity = create_integrity(payload)

        assert verify_integrity(payload, integrity) is True

    def test_verify_modified_payload_fails(self):
        """Test that modified payload fails verification."""
        original_payload = {"prompt": "Original"}
        integrity = create_integrity(original_payload)

        modified_payload = {"prompt": "Modified"}
        assert verify_integrity(modified_payload, integrity) is False

    def test_verify_with_different_algorithms(self):
        """Test verification works with different algorithms."""
        payload = {"prompt": "Test"}

        for alg in ["sha256", "sha384", "sha512"]:
            integrity = create_integrity(payload, alg)
            assert verify_integrity(payload, integrity) is True

    def test_verify_wrong_hash_fails(self):
        """Test that wrong hash fails verification."""
        payload = {"prompt": "Test"}
        wrong_integrity = Integrity(alg="sha256", hash="0" * 64)

        assert verify_integrity(payload, wrong_integrity) is False
