"""
Provenance chains for EPP envelopes.

Implements isnad-style trust chains: author → auditor → voucher.
Each attestation is independently signed, creating a verifiable chain of custody.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# Standard roles in the provenance chain
ProvenanceRole = Literal["author", "auditor", "reviewer", "voucher", "forwarder", "operator"]

STANDARD_ROLES = ("author", "auditor", "reviewer", "voucher", "forwarder", "operator")


class ProvenanceEntry(BaseModel):
    """
    A single entry in a provenance chain.

    Each entry represents an attestation by an entity about the envelope content.
    The signature covers: role||identity||timestamp||statement||parent_hash
    """

    role: str = Field(
        ...,
        description="Role of the attestor (author, auditor, reviewer, voucher, forwarder, operator)",
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
        description="Ed25519 signature over the attestation payload (base64)",
    )
    statement: Optional[str] = Field(
        default=None,
        description="Optional statement about the attestation (e.g., 'I reviewed and found no issues')",
    )
    parent_hash: Optional[str] = Field(
        default=None,
        description="Hash of the previous provenance entry (for chain integrity)",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional metadata about the attestation",
    )

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate role is alphanumeric (allow custom roles)."""
        import re

        if not re.match(r"^[a-zA-Z0-9_\-]+$", v):
            raise ValueError(f"Invalid role: {v}")
        return v.lower()

    @field_validator("identity")
    @classmethod
    def validate_identity(cls, v: str) -> str:
        """Validate identity is a 64-char hex public key."""
        import re

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

    def get_signing_payload(self, content_hash: str) -> bytes:
        """
        Get the canonical payload for signing this attestation.

        Args:
            content_hash: Hash of the content being attested to

        Returns:
            Bytes to sign
        """
        parts = [
            self.role,
            self.identity,
            self.timestamp,
            self.statement or "",
            self.parent_hash or "",
            content_hash,
        ]
        return "\n".join(parts).encode("utf-8")

    def compute_hash(self) -> str:
        """Compute hash of this entry for chain linking."""
        data = {
            "role": self.role,
            "identity": self.identity,
            "timestamp": self.timestamp,
            "signature": self.signature,
            "statement": self.statement,
            "parent_hash": self.parent_hash,
        }
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


class Provenance(BaseModel):
    """
    A provenance chain for an EPP envelope.

    Contains a list of attestations forming a chain of custody.
    Each entry links to the previous via parent_hash.
    """

    entries: List[ProvenanceEntry] = Field(
        default_factory=list,
        description="Ordered list of provenance entries (oldest first)",
    )
    content_hash: str = Field(
        ...,
        description="Hash of the content being attested to (e.g., payload hash)",
    )

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, v: str) -> str:
        """Validate content hash is hex."""
        if not all(c in "0123456789abcdef" for c in v.lower()):
            raise ValueError("content_hash must be hexadecimal")
        return v.lower()

    def chain_depth(self) -> int:
        """Return the number of attestations in the chain."""
        return len(self.entries)

    def has_role(self, role: str) -> bool:
        """Check if chain contains an attestation with the given role."""
        return any(e.role == role.lower() for e in self.entries)

    def get_by_role(self, role: str) -> List[ProvenanceEntry]:
        """Get all entries with the given role."""
        return [e for e in self.entries if e.role == role.lower()]

    def get_author(self) -> Optional[ProvenanceEntry]:
        """Get the author entry if present."""
        authors = self.get_by_role("author")
        return authors[0] if authors else None

    def get_auditors(self) -> List[ProvenanceEntry]:
        """Get all auditor entries."""
        return self.get_by_role("auditor")

    def get_vouchers(self) -> List[ProvenanceEntry]:
        """Get all voucher entries."""
        return self.get_by_role("voucher")

    def verify_chain_integrity(self) -> tuple[bool, Optional[str]]:
        """
        Verify the chain's parent_hash links are valid.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.entries:
            return (True, None)

        # First entry should have no parent_hash (or it's the content_hash)
        for i, entry in enumerate(self.entries):
            if i == 0:
                # First entry: parent_hash should be None or content_hash
                if entry.parent_hash and entry.parent_hash != self.content_hash:
                    return (
                        False,
                        f"First entry parent_hash mismatch: expected None or {self.content_hash}",
                    )
            else:
                # Subsequent entries: parent_hash should match previous entry's hash
                expected_parent = self.entries[i - 1].compute_hash()
                if entry.parent_hash != expected_parent:
                    return (False, f"Entry {i} parent_hash mismatch: expected {expected_parent}")

        return (True, None)


def create_provenance_entry(
    role: str,
    identity: str,
    content_hash: str,
    sign_func,
    statement: Optional[str] = None,
    parent_hash: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> ProvenanceEntry:
    """
    Create a signed provenance entry.

    Args:
        role: Role of the attestor
        identity: Public key (hex) of the attestor
        content_hash: Hash of content being attested to
        sign_func: Function that takes bytes and returns base64 signature
        statement: Optional statement about the attestation
        parent_hash: Hash of previous entry in chain
        metadata: Optional additional metadata

    Returns:
        Signed ProvenanceEntry
    """
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Create entry without signature first
    entry = ProvenanceEntry(
        role=role,
        identity=identity,
        timestamp=timestamp,
        signature="",  # Placeholder
        statement=statement,
        parent_hash=parent_hash,
        metadata=metadata,
    )

    # Get signing payload and sign
    payload = entry.get_signing_payload(content_hash)
    signature = sign_func(payload)

    # Return entry with signature
    return ProvenanceEntry(
        role=role,
        identity=identity,
        timestamp=timestamp,
        signature=signature,
        statement=statement,
        parent_hash=parent_hash,
        metadata=metadata,
    )


def verify_provenance_entry(
    entry: ProvenanceEntry,
    content_hash: str,
    verify_func,
) -> bool:
    """
    Verify a provenance entry's signature.

    Args:
        entry: The entry to verify
        content_hash: Hash of content being attested to
        verify_func: Function that takes (identity, payload, signature) and returns bool

    Returns:
        True if signature is valid
    """
    payload = entry.get_signing_payload(content_hash)
    return verify_func(entry.identity, payload, entry.signature)


def add_attestation(
    provenance: Provenance,
    role: str,
    identity: str,
    sign_func,
    statement: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Provenance:
    """
    Add a new attestation to the provenance chain.

    Args:
        provenance: Existing provenance chain
        role: Role of the new attestor
        identity: Public key (hex) of the attestor
        sign_func: Signing function
        statement: Optional statement
        metadata: Optional metadata

    Returns:
        New Provenance with the attestation added
    """
    # Compute parent hash
    parent_hash = None
    if provenance.entries:
        parent_hash = provenance.entries[-1].compute_hash()
    else:
        parent_hash = provenance.content_hash

    # Create new entry
    new_entry = create_provenance_entry(
        role=role,
        identity=identity,
        content_hash=provenance.content_hash,
        sign_func=sign_func,
        statement=statement,
        parent_hash=parent_hash,
        metadata=metadata,
    )

    # Return new provenance with entry added
    return Provenance(
        content_hash=provenance.content_hash,
        entries=provenance.entries + [new_entry],
    )


def verify_provenance_chain(
    provenance: Provenance,
    verify_func,
) -> tuple[bool, List[str]]:
    """
    Verify all signatures and chain integrity in a provenance chain.

    Args:
        provenance: The provenance chain to verify
        verify_func: Function that takes (identity, payload, signature) and returns bool

    Returns:
        Tuple of (is_valid, list of errors)
    """
    errors = []

    # Check chain integrity
    valid, err = provenance.verify_chain_integrity()
    if not valid:
        errors.append(f"Chain integrity: {err}")

    # Verify each signature
    for i, entry in enumerate(provenance.entries):
        if not verify_provenance_entry(entry, provenance.content_hash, verify_func):
            errors.append(
                f"Invalid signature for entry {i} (role={entry.role}, identity={entry.identity[:16]}...)"
            )

    return (len(errors) == 0, errors)


def check_provenance_requirements(
    provenance: Provenance,
    min_depth: int = 0,
    required_roles: Optional[List[str]] = None,
    min_auditors: int = 0,
    min_vouchers: int = 0,
) -> tuple[bool, List[str]]:
    """
    Check if provenance meets requirements.

    Args:
        provenance: The provenance chain to check
        min_depth: Minimum chain depth required
        required_roles: Roles that must be present
        min_auditors: Minimum number of auditor attestations
        min_vouchers: Minimum number of voucher attestations

    Returns:
        Tuple of (meets_requirements, list of unmet requirements)
    """
    unmet = []

    if provenance.chain_depth() < min_depth:
        unmet.append(f"Chain depth {provenance.chain_depth()} < required {min_depth}")

    if required_roles:
        for role in required_roles:
            if not provenance.has_role(role):
                unmet.append(f"Missing required role: {role}")

    num_auditors = len(provenance.get_auditors())
    if num_auditors < min_auditors:
        unmet.append(f"Auditors {num_auditors} < required {min_auditors}")

    num_vouchers = len(provenance.get_vouchers())
    if num_vouchers < min_vouchers:
        unmet.append(f"Vouchers {num_vouchers} < required {min_vouchers}")

    return (len(unmet) == 0, unmet)


def provenance_from_dict(data: Optional[Dict[str, Any]]) -> Optional[Provenance]:
    """
    Create Provenance from a dict (for parsing envelopes).

    Args:
        data: Dict with provenance data

    Returns:
        Provenance object or None
    """
    if data is None:
        return None
    return Provenance(**data)
