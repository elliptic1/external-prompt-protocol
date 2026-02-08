"""
EPP data models and validation.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from epp.capabilities import Capabilities
from epp.crypto.integrity import Integrity


class Payload(BaseModel):
    """EPP envelope payload."""

    prompt: str = Field(..., min_length=1, description="The prompt text to be delivered")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Structured context data")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")
    payload_type: Optional[str] = Field(
        default=None,
        description="Type hint for payload schema (e.g., 'order-request', 'medical-record')",
    )

    @field_validator("prompt")
    @classmethod
    def validate_prompt_not_empty(cls, v: str) -> str:
        """Ensure prompt is not just whitespace."""
        if not v.strip():
            raise ValueError("Prompt cannot be empty or whitespace-only")
        return v

    @field_validator("payload_type")
    @classmethod
    def validate_payload_type(cls, v: Optional[str]) -> Optional[str]:
        """Validate payload_type contains only alphanumeric characters and hyphens."""
        if v is not None and not re.match(r"^[a-zA-Z0-9\-]+$", v):
            raise ValueError(
                f"payload_type must contain only alphanumeric characters and hyphens: {v}"
            )
        return v


class Delegation(BaseModel):
    """Delegation info for acting on behalf of another entity."""

    on_behalf_of: str = Field(..., description="Public key hex (64 chars) of the principal")
    authorization: Optional[str] = Field(
        default=None, description="Optional evidence (e.g., signed token, reference)"
    )

    @field_validator("on_behalf_of")
    @classmethod
    def validate_on_behalf_of(cls, v: str) -> str:
        """Validate on_behalf_of is a 64-char hex public key."""
        if not re.match(r"^[0-9a-fA-F]{64}$", v):
            raise ValueError(f"on_behalf_of must be 64 hexadecimal characters (32 bytes): {v}")
        return v.lower()


class Envelope(BaseModel):
    """EPP envelope with cryptographic signature."""

    version: str = Field(..., pattern="^1$", description="Protocol version (must be '1')")
    envelope_id: str = Field(..., description="Unique envelope identifier (UUID v4)")
    sender: str = Field(..., description="Sender's public key (hexadecimal)")
    recipient: str = Field(..., description="Recipient's public key (hexadecimal)")
    timestamp: str = Field(..., description="Creation time (ISO-8601 UTC)")
    expires_at: str = Field(..., description="Expiration time (ISO-8601 UTC)")
    nonce: str = Field(..., description="Random nonce (base64)")
    scope: str = Field(..., description="Scope identifier for policy matching")
    payload: Payload = Field(..., description="Envelope payload")
    signature: str = Field(..., description="Cryptographic signature (base64)")
    conversation_id: Optional[str] = Field(
        default=None, description="Conversation thread ID (UUID)"
    )
    in_reply_to: Optional[str] = Field(
        default=None, description="envelope_id being replied to (UUID)"
    )
    delegation: Optional[Delegation] = Field(
        default=None,
        description="Delegation info for acting on behalf of another entity",
    )
    integrity: Optional[Integrity] = Field(
        default=None,
        description="Content integrity hash for payload verification (v1.1)",
    )
    capabilities: Optional[Capabilities] = Field(
        default=None,
        description="Capability declarations for permission requests (v1.1)",
    )

    @field_validator("envelope_id")
    @classmethod
    def validate_envelope_id(cls, v: str) -> str:
        """Validate envelope_id is a valid UUID."""
        try:
            UUID(v)
        except ValueError:
            raise ValueError(f"envelope_id must be a valid UUID: {v}")
        return v

    @field_validator("conversation_id")
    @classmethod
    def validate_conversation_id(cls, v: Optional[str]) -> Optional[str]:
        """Validate conversation_id is a valid UUID when present."""
        if v is not None:
            try:
                UUID(v)
            except ValueError:
                raise ValueError(f"conversation_id must be a valid UUID: {v}")
        return v

    @field_validator("in_reply_to")
    @classmethod
    def validate_in_reply_to(cls, v: Optional[str]) -> Optional[str]:
        """Validate in_reply_to is a valid UUID when present."""
        if v is not None:
            try:
                UUID(v)
            except ValueError:
                raise ValueError(f"in_reply_to must be a valid UUID: {v}")
        return v

    @field_validator("sender", "recipient")
    @classmethod
    def validate_public_key(cls, v: str) -> str:
        """Validate public key is hexadecimal."""
        if not re.match(r"^[0-9a-fA-F]{64}$", v):
            raise ValueError(f"Public key must be 64 hexadecimal characters (32 bytes): {v}")
        return v.lower()

    @field_validator("timestamp", "expires_at")
    @classmethod
    def validate_iso8601(cls, v: str) -> str:
        """Validate ISO-8601 timestamp format."""
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"Invalid ISO-8601 timestamp: {v}")
        return v

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, v: str) -> str:
        """Validate scope contains only alphanumeric characters and hyphens."""
        if not re.match(r"^[a-zA-Z0-9\-]+$", v):
            raise ValueError(f"Scope must contain only alphanumeric characters and hyphens: {v}")
        return v

    @field_validator("nonce")
    @classmethod
    def validate_nonce(cls, v: str) -> str:
        """Validate nonce is valid base64 and minimum length."""
        import base64

        try:
            decoded = base64.b64decode(v)
            if len(decoded) < 16:
                raise ValueError(f"Nonce must be at least 16 bytes: {len(decoded)} bytes")
        except Exception as e:
            raise ValueError(f"Invalid base64 nonce: {e}")
        return v

    @field_validator("signature")
    @classmethod
    def validate_signature(cls, v: str) -> str:
        """Validate signature is valid base64."""
        import base64

        try:
            base64.b64decode(v)
        except Exception as e:
            raise ValueError(f"Invalid base64 signature: {e}")
        return v

    @model_validator(mode="after")
    def validate_expiration(self) -> "Envelope":
        """Validate expiration is after timestamp."""
        timestamp_dt = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
        expires_dt = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))

        if expires_dt <= timestamp_dt:
            raise ValueError("expires_at must be after timestamp")

        return self

    def is_expired(self) -> bool:
        """Check if envelope has expired."""
        expires_dt = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        return datetime.now(expires_dt.tzinfo) > expires_dt

    def size_bytes(self) -> int:
        """Calculate the size of the envelope in bytes."""
        return len(self.model_dump_json().encode("utf-8"))


class Receipt(BaseModel):
    """Receipt returned after envelope processing."""

    status: str = Field(..., pattern="^(accepted|rejected)$")
    envelope_id: str
    received_at: str

    @field_validator("received_at")
    @classmethod
    def validate_iso8601(cls, v: str) -> str:
        """Validate ISO-8601 timestamp format."""
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"Invalid ISO-8601 timestamp: {v}")
        return v


class SuccessReceipt(Receipt):
    """Receipt for accepted envelope."""

    status: str = Field(default="accepted", pattern="^accepted$")
    receipt_id: str
    executor: str


class ErrorDetail(BaseModel):
    """Error details for rejected envelope."""

    code: str = Field(
        ...,
        pattern="^(INVALID_FORMAT|UNSUPPORTED_VERSION|WRONG_RECIPIENT|EXPIRED|"
        "INVALID_SIGNATURE|REPLAY_DETECTED|UNTRUSTED_SENDER|POLICY_DENIED|"
        "SIZE_EXCEEDED|RATE_LIMITED)$",
    )
    message: str


class ErrorReceipt(Receipt):
    """Receipt for rejected envelope."""

    status: str = Field(default="rejected", pattern="^rejected$")
    error: ErrorDetail
