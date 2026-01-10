"""
Tests for EPP data models.
"""

from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from epp.models import Envelope, ErrorDetail, ErrorReceipt, Payload, SuccessReceipt


class TestPayload:
    """Tests for Payload model."""

    def test_valid_payload(self):
        """Test creating valid payload."""
        payload = Payload(prompt="Test prompt")
        assert payload.prompt == "Test prompt"
        assert payload.context is None
        assert payload.metadata is None

    def test_payload_with_context(self):
        """Test payload with context."""
        payload = Payload(
            prompt="Test",
            context={"key": "value"},
            metadata={"source": "test"},
        )
        assert payload.context == {"key": "value"}
        assert payload.metadata == {"source": "test"}

    def test_empty_prompt_rejected(self):
        """Test that empty prompts are rejected."""
        with pytest.raises(ValidationError):
            Payload(prompt="")

    def test_whitespace_prompt_rejected(self):
        """Test that whitespace-only prompts are rejected."""
        with pytest.raises(ValidationError):
            Payload(prompt="   \n  \t  ")


class TestEnvelope:
    """Tests for Envelope model."""

    def get_valid_envelope_data(self):
        """Get valid envelope data for testing."""
        return {
            "version": "1",
            "envelope_id": "550e8400-e29b-41d4-a716-446655440000",
            "sender": "a" * 64,
            "recipient": "b" * 64,
            "timestamp": "2024-01-01T00:00:00Z",
            "expires_at": "2024-01-01T01:00:00Z",
            "nonce": "AAAAAAAAAAAAAAAAAAAAAA==",  # 16 bytes base64
            "scope": "test-scope",
            "payload": {"prompt": "Test prompt"},
            "signature": "dGVzdHNpZ25hdHVyZQ==",  # base64
        }

    def test_valid_envelope(self):
        """Test creating valid envelope."""
        data = self.get_valid_envelope_data()
        envelope = Envelope(**data)
        assert envelope.version == "1"
        assert envelope.scope == "test-scope"

    def test_invalid_version(self):
        """Test invalid version is rejected."""
        data = self.get_valid_envelope_data()
        data["version"] = "2"
        with pytest.raises(ValidationError):
            Envelope(**data)

    def test_invalid_uuid(self):
        """Test invalid UUID is rejected."""
        data = self.get_valid_envelope_data()
        data["envelope_id"] = "not-a-uuid"
        with pytest.raises(ValidationError):
            Envelope(**data)

    def test_invalid_public_key(self):
        """Test invalid public key is rejected."""
        data = self.get_valid_envelope_data()
        data["sender"] = "not-hex"
        with pytest.raises(ValidationError):
            Envelope(**data)

    def test_public_key_wrong_length(self):
        """Test public key with wrong length is rejected."""
        data = self.get_valid_envelope_data()
        data["sender"] = "a" * 32  # Too short
        with pytest.raises(ValidationError):
            Envelope(**data)

    def test_invalid_timestamp(self):
        """Test invalid timestamp is rejected."""
        data = self.get_valid_envelope_data()
        data["timestamp"] = "not-a-timestamp"
        with pytest.raises(ValidationError):
            Envelope(**data)

    def test_invalid_scope(self):
        """Test invalid scope characters are rejected."""
        data = self.get_valid_envelope_data()
        data["scope"] = "invalid scope!"  # Spaces and special chars
        with pytest.raises(ValidationError):
            Envelope(**data)

    def test_valid_scope_formats(self):
        """Test valid scope formats."""
        data = self.get_valid_envelope_data()

        # Alphanumeric and hyphens are OK
        data["scope"] = "test-scope-123"
        envelope = Envelope(**data)
        assert envelope.scope == "test-scope-123"

    def test_short_nonce_rejected(self):
        """Test nonce shorter than 16 bytes is rejected."""
        data = self.get_valid_envelope_data()
        import base64

        data["nonce"] = base64.b64encode(b"short").decode()  # Only 5 bytes
        with pytest.raises(ValidationError):
            Envelope(**data)

    def test_expiration_before_timestamp(self):
        """Test expiration before timestamp is rejected."""
        data = self.get_valid_envelope_data()
        data["timestamp"] = "2024-01-01T02:00:00Z"
        data["expires_at"] = "2024-01-01T01:00:00Z"
        with pytest.raises(ValidationError):
            Envelope(**data)

    def test_is_expired(self):
        """Test expiration checking."""
        data = self.get_valid_envelope_data()

        # Future expiration
        future = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"
        data["expires_at"] = future
        envelope = Envelope(**data)
        assert envelope.is_expired() is False

        # Past expiration
        past = (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z"
        data["expires_at"] = past
        data["timestamp"] = (datetime.utcnow() - timedelta(hours=2)).isoformat() + "Z"
        envelope = Envelope(**data)
        assert envelope.is_expired() is True

    def test_size_bytes(self):
        """Test envelope size calculation."""
        data = self.get_valid_envelope_data()
        envelope = Envelope(**data)
        size = envelope.size_bytes()
        assert size > 0
        assert isinstance(size, int)


class TestReceipts:
    """Tests for receipt models."""

    def test_success_receipt(self):
        """Test creating success receipt."""
        receipt = SuccessReceipt(
            envelope_id="test-id",
            received_at="2024-01-01T00:00:00Z",
            receipt_id="receipt-id",
            executor="test-executor",
        )
        assert receipt.status == "accepted"
        assert receipt.receipt_id == "receipt-id"

    def test_error_receipt(self):
        """Test creating error receipt."""
        error = ErrorDetail(code="INVALID_SIGNATURE", message="Test error")
        receipt = ErrorReceipt(
            envelope_id="test-id",
            received_at="2024-01-01T00:00:00Z",
            error=error,
        )
        assert receipt.status == "rejected"
        assert receipt.error.code == "INVALID_SIGNATURE"

    def test_invalid_error_code(self):
        """Test invalid error code is rejected."""
        with pytest.raises(ValidationError):
            ErrorDetail(code="INVALID_CODE", message="Test")
