"""
Multi-party attestation for EPP envelopes (v1.1).

Unlike `provenance` (an ordered chain with parent_hash linking), `attestations`
expresses an unordered set of independent attestations with threshold semantics:
"this envelope must carry signatures from at least N attestors, and at least
one of them must hold each role in `required_roles`."

Each AttestationEntry is independently signed over a canonical payload covering
role || identity || timestamp || subject_hash, where subject_hash is a digest
of the envelope content being attested to (typically the integrity hash).
"""

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class AttestationEntry(BaseModel):
    """A single independent attestation."""

    role: str = Field(
        ...,
        description="Role of the attestor (auditor, reviewer, voucher, custom-role, ...)",
    )
    identity: str = Field(
        ...,
        description="Public key (hex) of the attestor",
    )
    timestamp: str = Field(
        ...,
        description="When the attestation was made (ISO-8601 UTC)",
    )
    signature: str = Field(
        ...,
        description="Ed25519 signature (base64) over role||identity||timestamp||subject_hash",
    )
    subject_hash: str = Field(
        ...,
        description="Hex digest of the envelope content being attested",
    )
    statement: Optional[str] = Field(
        default=None,
        description="Optional human-readable statement (e.g. 'reviewed and approved')",
    )

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate role is alphanumeric (allow custom roles)."""
        if not re.match(r"^[a-zA-Z0-9_\-]+$", v):
            raise ValueError(f"Invalid role: {v}")
        return v.lower()

    @field_validator("identity")
    @classmethod
    def validate_identity(cls, v: str) -> str:
        """Validate identity is a 64-char hex public key."""
        if not re.match(r"^[0-9a-fA-F]{64}$", v):
            raise ValueError(f"Identity must be 64 hex characters: {v}")
        return v.lower()

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """Validate ISO-8601 timestamp."""
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"Invalid ISO-8601 timestamp: {v}")
        return v

    @field_validator("subject_hash")
    @classmethod
    def validate_subject_hash(cls, v: str) -> str:
        """Validate subject_hash is hex."""
        if not re.match(r"^[0-9a-fA-F]+$", v):
            raise ValueError(f"subject_hash must be hex: {v}")
        return v.lower()

    def get_signing_payload(self) -> bytes:
        """Canonical bytes signed by this attestation."""
        parts = [
            self.role,
            self.identity,
            self.timestamp,
            self.statement or "",
            self.subject_hash,
        ]
        return "\n".join(parts).encode("utf-8")


class Attestations(BaseModel):
    """
    A set of independent attestations with threshold + required-role semantics.
    """

    threshold: int = Field(
        ...,
        ge=1,
        description="Minimum number of attestation entries required",
    )
    required_roles: List[str] = Field(
        default_factory=list,
        description="Roles that MUST appear among entries (each at least once)",
    )
    entries: List[AttestationEntry] = Field(
        default_factory=list,
        description="The independent attestations",
    )

    @field_validator("required_roles")
    @classmethod
    def normalize_roles(cls, v: List[str]) -> List[str]:
        """Lowercase and validate each role string."""
        out = []
        for role in v:
            if not re.match(r"^[a-zA-Z0-9_\-]+$", role):
                raise ValueError(f"Invalid required_role: {role}")
            out.append(role.lower())
        return out

    @model_validator(mode="after")
    def check_threshold_and_roles(self) -> "Attestations":
        """Threshold and required_roles are enforced at construction time."""
        if len(self.entries) < self.threshold:
            raise ValueError(
                f"Attestations requires {self.threshold} entries, got {len(self.entries)}"
            )

        present_roles = {entry.role for entry in self.entries}
        missing = [r for r in self.required_roles if r not in present_roles]
        if missing:
            raise ValueError(f"Attestations missing required roles: {missing}")

        return self

    def has_role(self, role: str) -> bool:
        """Check whether any entry holds the given role."""
        return any(entry.role == role.lower() for entry in self.entries)

    def get_by_role(self, role: str) -> List[AttestationEntry]:
        """Return all entries holding the given role."""
        return [entry for entry in self.entries if entry.role == role.lower()]


def compute_subject_hash(content: bytes, alg: str = "sha256") -> str:
    """
    Compute a hex digest of arbitrary content for use as subject_hash.

    Defaults to sha256 to match epp.crypto.integrity defaults.
    """
    hasher = hashlib.new(alg)
    hasher.update(content)
    return hasher.hexdigest()


def create_attestation_entry(
    role: str,
    identity: str,
    subject_hash: str,
    sign_func: Callable[[bytes], str],
    statement: Optional[str] = None,
) -> AttestationEntry:
    """
    Build and sign a single AttestationEntry.

    Args:
        role: Attestor role (auditor, reviewer, voucher, ...)
        identity: Hex public key of the attestor
        subject_hash: Hex digest of the envelope content being attested
        sign_func: Function bytes -> base64 signature (provided by caller)
        statement: Optional human-readable statement
    """
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    unsigned = AttestationEntry(
        role=role,
        identity=identity,
        timestamp=timestamp,
        signature="placeholder",
        subject_hash=subject_hash,
        statement=statement,
    )
    signature = sign_func(unsigned.get_signing_payload())
    return AttestationEntry(
        role=role,
        identity=identity,
        timestamp=timestamp,
        signature=signature,
        subject_hash=subject_hash,
        statement=statement,
    )


def verify_attestation_entry(
    entry: AttestationEntry,
    verify_func: Callable[[str, bytes, str], bool],
) -> bool:
    """
    Verify a single attestation entry's signature against its identity.
    """
    return verify_func(entry.identity, entry.get_signing_payload(), entry.signature)


def verify_attestations(
    attestations: Attestations,
    expected_subject_hash: str,
    verify_func: Callable[[str, bytes, str], bool],
) -> tuple[bool, List[str]]:
    """
    Verify all entries' signatures, that each entry's subject_hash matches the
    expected one, and that threshold + required_roles are satisfied.

    Returns:
        (ok, errors) — ok is True when every check passes; errors lists problems.
    """
    errors: List[str] = []
    expected = expected_subject_hash.lower()

    for i, entry in enumerate(attestations.entries):
        if entry.subject_hash != expected:
            errors.append(
                f"entry[{i}] subject_hash mismatch: expected {expected}, got {entry.subject_hash}"
            )
            continue
        if not verify_attestation_entry(entry, verify_func):
            errors.append(f"entry[{i}] signature invalid for identity {entry.identity[:16]}...")

    if len(attestations.entries) < attestations.threshold:
        errors.append(
            f"only {len(attestations.entries)} entries, threshold is {attestations.threshold}"
        )

    present_roles = {e.role for e in attestations.entries}
    for required in attestations.required_roles:
        if required not in present_roles:
            errors.append(f"missing required role: {required}")

    return (len(errors) == 0, errors)


def attestations_from_dict(data: Optional[Dict[str, Any]]) -> Optional[Attestations]:
    """Construct Attestations from a plain dict, or return None."""
    if data is None:
        return None
    return Attestations(**data)
