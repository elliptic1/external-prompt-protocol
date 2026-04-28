"""
Key revocation hint for EPP envelopes (v1.1).

A `RevocationCheck` field on an envelope tells receivers where to look up
the sender's revocation status, and whether the check is mandatory.

The actual lookup is intentionally a stub in v1.1 — production deployments
wire in their own registry client (HTTP, DID, on-chain, ...). The interface
is defined so the inbox processor can call it consistently.
"""

import re
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, field_validator

SupportedFailureMode = Literal["deny", "allow", "log-only"]
SUPPORTED_FAILURE_MODES = ("deny", "allow", "log-only")


class RevocationCheck(BaseModel):
    """
    Tells the receiver where to consult for the sender's revocation status.
    """

    registry: str = Field(
        ...,
        description="Revocation registry locator (https URL or DID)",
    )
    required: bool = Field(
        default=True,
        description="If True, receivers MUST consult before accepting the envelope",
    )

    @field_validator("registry")
    @classmethod
    def validate_registry(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("registry must not be empty")
        if v.startswith("did:"):
            if not re.match(r"^did:[a-z0-9]+:[a-zA-Z0-9._\-:]+$", v):
                raise ValueError(f"Invalid DID: {v}")
            return v
        if v.startswith(("https://", "http://")):
            return v
        raise ValueError(f"registry must be a DID or http(s) URL, got: {v}")


def revocation_check_from_dict(data: Optional[Dict[str, Any]]) -> Optional[RevocationCheck]:
    """Construct RevocationCheck from a dict, or return None."""
    if data is None:
        return None
    return RevocationCheck(**data)


class RevocationStatus(BaseModel):
    """
    Result of a revocation lookup.
    """

    revoked: bool
    checked_at: str
    source: str = Field(
        default="stub",
        description="Identifier of the registry / client that produced this status",
    )
    reason: Optional[str] = Field(
        default=None,
        description="Human-readable reason if revoked, or note from the lookup",
    )


class RevocationLookup:
    """
    Pluggable interface for revocation lookups.

    The default implementation always returns "not revoked" — receivers wire
    in their own subclass that talks to their actual registry. The processor
    treats RevocationLookup as a hard dependency only when policy demands it.
    """

    def lookup(self, sender_pubkey: str, registry: str) -> RevocationStatus:
        """
        Look up revocation status for a sender against a registry.

        Default behavior: return not-revoked. Subclass and override.
        """
        from datetime import datetime, timezone

        return RevocationStatus(
            revoked=False,
            checked_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source="stub",
            reason="default RevocationLookup always returns not-revoked",
        )
