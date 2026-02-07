"""
Tests for EPP data models.
"""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from epp.models import Delegation, Envelope, ErrorDetail, ErrorReceipt, Payload, SuccessReceipt


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

    def test_payload_type_valid(self):
        """Test valid payload_type."""
        payload = Payload(prompt="Test", payload_type="order-request")
        assert payload.payload_type == "order-request"

    def test_payload_type_none(self):
        """Test payload_type defaults to None."""
        payload = Payload(prompt="Test")
        assert payload.payload_type is None

    def test_payload_type_invalid_chars(self):
        """Test payload_type with invalid characters is rejected."""
        with pytest.raises(ValidationError):
            Payload(prompt="Test", payload_type="invalid type!")

    def test_payload_type_alphanumeric_hyphens(self):
        """Test payload_type allows alphanumeric and hyphens."""
        payload = Payload(prompt="Test", payload_type="medical-record-v2")
        assert payload.payload_type == "medical-record-v2"


class TestDelegation:
    """Tests for Delegation model."""

    def test_valid_delegation(self):
        """Test creating valid delegation."""
        delegation = Delegation(on_behalf_of="a" * 64)
        assert delegation.on_behalf_of == "a" * 64
        assert delegation.authorization is None

    def test_delegation_with_authorization(self):
        """Test delegation with authorization evidence."""
        delegation = Delegation(on_behalf_of="b" * 64, authorization="signed-token-xyz")
        assert delegation.authorization == "signed-token-xyz"

    def test_invalid_public_key_format(self):
        """Test delegation with invalid public key is rejected."""
        with pytest.raises(ValidationError):
            Delegation(on_behalf_of="not-a-valid-key")

    def test_short_public_key(self):
        """Test delegation with too-short public key is rejected."""
        with pytest.raises(ValidationError):
            Delegation(on_behalf_of="a" * 32)

    def test_uppercase_normalized(self):
        """Test that uppercase hex is normalized to lowercase."""
        delegation = Delegation(on_behalf_of="A" * 64)
        assert delegation.on_behalf_of == "a" * 64


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
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        data["expires_at"] = future
        envelope = Envelope(**data)
        assert envelope.is_expired() is False

        # Past expiration
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        data["expires_at"] = past
        data["timestamp"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
        envelope = Envelope(**data)
        assert envelope.is_expired() is True

    def test_size_bytes(self):
        """Test envelope size calculation."""
        data = self.get_valid_envelope_data()
        envelope = Envelope(**data)
        size = envelope.size_bytes()
        assert size > 0
        assert isinstance(size, int)

    def test_conversation_id_valid(self):
        """Test valid conversation_id UUID."""
        data = self.get_valid_envelope_data()
        data["conversation_id"] = "550e8400-e29b-41d4-a716-446655440001"
        envelope = Envelope(**data)
        assert envelope.conversation_id == "550e8400-e29b-41d4-a716-446655440001"

    def test_conversation_id_invalid(self):
        """Test invalid conversation_id is rejected."""
        data = self.get_valid_envelope_data()
        data["conversation_id"] = "not-a-uuid"
        with pytest.raises(ValidationError):
            Envelope(**data)

    def test_in_reply_to_valid(self):
        """Test valid in_reply_to UUID."""
        data = self.get_valid_envelope_data()
        data["in_reply_to"] = "550e8400-e29b-41d4-a716-446655440002"
        envelope = Envelope(**data)
        assert envelope.in_reply_to == "550e8400-e29b-41d4-a716-446655440002"

    def test_in_reply_to_invalid(self):
        """Test invalid in_reply_to is rejected."""
        data = self.get_valid_envelope_data()
        data["in_reply_to"] = "not-a-uuid"
        with pytest.raises(ValidationError):
            Envelope(**data)

    def test_delegation_nested(self):
        """Test delegation as nested object on envelope."""
        data = self.get_valid_envelope_data()
        data["delegation"] = {"on_behalf_of": "c" * 64}
        envelope = Envelope(**data)
        assert envelope.delegation is not None
        assert envelope.delegation.on_behalf_of == "c" * 64

    def test_new_fields_default_none(self):
        """Test that all new fields default to None (backward compatibility)."""
        data = self.get_valid_envelope_data()
        envelope = Envelope(**data)
        assert envelope.conversation_id is None
        assert envelope.in_reply_to is None
        assert envelope.delegation is None

    def test_backward_compatibility(self):
        """Test envelope without new fields still works (existing format)."""
        data = self.get_valid_envelope_data()
        # Explicitly no conversation_id, in_reply_to, or delegation
        envelope = Envelope(**data)
        assert envelope.version == "1"
        assert envelope.scope == "test-scope"
        assert envelope.conversation_id is None


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
