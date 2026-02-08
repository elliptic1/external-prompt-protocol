"""Tests for provenance chains."""

import base64
import pytest

from epp.provenance import (
    Provenance,
    ProvenanceEntry,
    add_attestation,
    check_provenance_requirements,
    create_provenance_entry,
    provenance_from_dict,
    verify_provenance_chain,
    verify_provenance_entry,
)


# Test fixtures
SAMPLE_IDENTITY = "a" * 64
SAMPLE_IDENTITY_2 = "b" * 64
SAMPLE_IDENTITY_3 = "c" * 64
SAMPLE_CONTENT_HASH = "d" * 64
SAMPLE_SIGNATURE = base64.b64encode(b"test_signature").decode()


class TestProvenanceEntry:
    """Tests for ProvenanceEntry model."""

    def test_create_entry(self):
        """Test creating a provenance entry."""
        entry = ProvenanceEntry(
            role="author",
            identity=SAMPLE_IDENTITY,
            timestamp="2026-02-08T00:00:00Z",
            signature=SAMPLE_SIGNATURE,
            statement="I authored this content",
        )
        assert entry.role == "author"
        assert entry.identity == SAMPLE_IDENTITY
        assert entry.statement == "I authored this content"

    def test_role_normalized_to_lowercase(self):
        """Test that role is normalized to lowercase."""
        entry = ProvenanceEntry(
            role="AUTHOR",
            identity=SAMPLE_IDENTITY,
            timestamp="2026-02-08T00:00:00Z",
            signature=SAMPLE_SIGNATURE,
        )
        assert entry.role == "author"

    def test_identity_normalized_to_lowercase(self):
        """Test that identity is normalized to lowercase."""
        entry = ProvenanceEntry(
            role="author",
            identity="A" * 64,
            timestamp="2026-02-08T00:00:00Z",
            signature=SAMPLE_SIGNATURE,
        )
        assert entry.identity == "a" * 64

    def test_invalid_identity_rejected(self):
        """Test that invalid identity is rejected."""
        with pytest.raises(ValueError, match="64 hex characters"):
            ProvenanceEntry(
                role="author",
                identity="invalid",
                timestamp="2026-02-08T00:00:00Z",
                signature=SAMPLE_SIGNATURE,
            )

    def test_invalid_timestamp_rejected(self):
        """Test that invalid timestamp is rejected."""
        with pytest.raises(ValueError, match="Invalid ISO-8601"):
            ProvenanceEntry(
                role="author",
                identity=SAMPLE_IDENTITY,
                timestamp="not-a-timestamp",
                signature=SAMPLE_SIGNATURE,
            )

    def test_compute_hash_deterministic(self):
        """Test that compute_hash is deterministic."""
        entry = ProvenanceEntry(
            role="author",
            identity=SAMPLE_IDENTITY,
            timestamp="2026-02-08T00:00:00Z",
            signature=SAMPLE_SIGNATURE,
        )
        hash1 = entry.compute_hash()
        hash2 = entry.compute_hash()
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256

    def test_get_signing_payload(self):
        """Test getting signing payload."""
        entry = ProvenanceEntry(
            role="author",
            identity=SAMPLE_IDENTITY,
            timestamp="2026-02-08T00:00:00Z",
            signature=SAMPLE_SIGNATURE,
            statement="Test statement",
        )
        payload = entry.get_signing_payload(SAMPLE_CONTENT_HASH)
        assert isinstance(payload, bytes)
        assert b"author" in payload
        assert b"Test statement" in payload


class TestProvenance:
    """Tests for Provenance model."""

    def test_create_empty_provenance(self):
        """Test creating empty provenance."""
        prov = Provenance(content_hash=SAMPLE_CONTENT_HASH)
        assert prov.chain_depth() == 0
        assert prov.entries == []

    def test_create_with_entries(self):
        """Test creating provenance with entries."""
        entry = ProvenanceEntry(
            role="author",
            identity=SAMPLE_IDENTITY,
            timestamp="2026-02-08T00:00:00Z",
            signature=SAMPLE_SIGNATURE,
        )
        prov = Provenance(
            content_hash=SAMPLE_CONTENT_HASH,
            entries=[entry],
        )
        assert prov.chain_depth() == 1

    def test_has_role(self):
        """Test checking for role presence."""
        entry = ProvenanceEntry(
            role="author",
            identity=SAMPLE_IDENTITY,
            timestamp="2026-02-08T00:00:00Z",
            signature=SAMPLE_SIGNATURE,
        )
        prov = Provenance(content_hash=SAMPLE_CONTENT_HASH, entries=[entry])
        
        assert prov.has_role("author")
        assert not prov.has_role("auditor")

    def test_get_by_role(self):
        """Test getting entries by role."""
        entries = [
            ProvenanceEntry(
                role="author",
                identity=SAMPLE_IDENTITY,
                timestamp="2026-02-08T00:00:00Z",
                signature=SAMPLE_SIGNATURE,
            ),
            ProvenanceEntry(
                role="auditor",
                identity=SAMPLE_IDENTITY_2,
                timestamp="2026-02-08T01:00:00Z",
                signature=SAMPLE_SIGNATURE,
            ),
            ProvenanceEntry(
                role="auditor",
                identity=SAMPLE_IDENTITY_3,
                timestamp="2026-02-08T02:00:00Z",
                signature=SAMPLE_SIGNATURE,
            ),
        ]
        prov = Provenance(content_hash=SAMPLE_CONTENT_HASH, entries=entries)
        
        authors = prov.get_by_role("author")
        assert len(authors) == 1
        
        auditors = prov.get_auditors()
        assert len(auditors) == 2

    def test_verify_chain_integrity_empty(self):
        """Test chain integrity on empty chain."""
        prov = Provenance(content_hash=SAMPLE_CONTENT_HASH)
        valid, err = prov.verify_chain_integrity()
        assert valid
        assert err is None

    def test_verify_chain_integrity_valid(self):
        """Test chain integrity with valid parent hashes."""
        entry1 = ProvenanceEntry(
            role="author",
            identity=SAMPLE_IDENTITY,
            timestamp="2026-02-08T00:00:00Z",
            signature=SAMPLE_SIGNATURE,
            parent_hash=SAMPLE_CONTENT_HASH,  # First entry links to content
        )
        entry2 = ProvenanceEntry(
            role="auditor",
            identity=SAMPLE_IDENTITY_2,
            timestamp="2026-02-08T01:00:00Z",
            signature=SAMPLE_SIGNATURE,
            parent_hash=entry1.compute_hash(),  # Links to previous entry
        )
        prov = Provenance(
            content_hash=SAMPLE_CONTENT_HASH,
            entries=[entry1, entry2],
        )
        
        valid, err = prov.verify_chain_integrity()
        assert valid

    def test_verify_chain_integrity_invalid(self):
        """Test chain integrity with invalid parent hashes."""
        entry1 = ProvenanceEntry(
            role="author",
            identity=SAMPLE_IDENTITY,
            timestamp="2026-02-08T00:00:00Z",
            signature=SAMPLE_SIGNATURE,
            parent_hash=SAMPLE_CONTENT_HASH,
        )
        entry2 = ProvenanceEntry(
            role="auditor",
            identity=SAMPLE_IDENTITY_2,
            timestamp="2026-02-08T01:00:00Z",
            signature=SAMPLE_SIGNATURE,
            parent_hash="wrong_hash" + "0" * 54,  # Wrong hash
        )
        prov = Provenance(
            content_hash=SAMPLE_CONTENT_HASH,
            entries=[entry1, entry2],
        )
        
        valid, err = prov.verify_chain_integrity()
        assert not valid
        assert "mismatch" in err


class TestCreateProvenanceEntry:
    """Tests for create_provenance_entry function."""

    def test_create_entry_with_sign_func(self):
        """Test creating entry with signing function."""
        def mock_sign(payload: bytes) -> str:
            return base64.b64encode(b"signed:" + payload[:10]).decode()
        
        entry = create_provenance_entry(
            role="author",
            identity=SAMPLE_IDENTITY,
            content_hash=SAMPLE_CONTENT_HASH,
            sign_func=mock_sign,
            statement="I wrote this",
        )
        
        assert entry.role == "author"
        assert entry.identity == SAMPLE_IDENTITY
        assert entry.statement == "I wrote this"
        assert entry.signature.startswith("c2lnbmVkOm")  # base64 of "signed:"


class TestAddAttestation:
    """Tests for add_attestation function."""

    def test_add_first_attestation(self):
        """Test adding first attestation to empty chain."""
        prov = Provenance(content_hash=SAMPLE_CONTENT_HASH)
        
        def mock_sign(payload: bytes) -> str:
            return base64.b64encode(b"sig").decode()
        
        new_prov = add_attestation(
            prov,
            role="author",
            identity=SAMPLE_IDENTITY,
            sign_func=mock_sign,
            statement="I authored this",
        )
        
        assert new_prov.chain_depth() == 1
        assert new_prov.entries[0].role == "author"
        assert new_prov.entries[0].parent_hash == SAMPLE_CONTENT_HASH

    def test_add_subsequent_attestation(self):
        """Test adding attestation to existing chain."""
        def mock_sign(payload: bytes) -> str:
            return base64.b64encode(b"sig").decode()
        
        # Create chain with author
        prov = Provenance(content_hash=SAMPLE_CONTENT_HASH)
        prov = add_attestation(prov, "author", SAMPLE_IDENTITY, mock_sign)
        
        # Add auditor
        prov = add_attestation(prov, "auditor", SAMPLE_IDENTITY_2, mock_sign)
        
        assert prov.chain_depth() == 2
        assert prov.entries[1].role == "auditor"
        # Second entry should link to first
        assert prov.entries[1].parent_hash == prov.entries[0].compute_hash()


class TestVerifyProvenanceEntry:
    """Tests for verify_provenance_entry function."""

    def test_verify_valid_entry(self):
        """Test verifying a valid entry."""
        entry = ProvenanceEntry(
            role="author",
            identity=SAMPLE_IDENTITY,
            timestamp="2026-02-08T00:00:00Z",
            signature=SAMPLE_SIGNATURE,
        )
        
        def mock_verify(identity, payload, signature):
            return True
        
        assert verify_provenance_entry(entry, SAMPLE_CONTENT_HASH, mock_verify)

    def test_verify_invalid_entry(self):
        """Test verifying an invalid entry."""
        entry = ProvenanceEntry(
            role="author",
            identity=SAMPLE_IDENTITY,
            timestamp="2026-02-08T00:00:00Z",
            signature=SAMPLE_SIGNATURE,
        )
        
        def mock_verify(identity, payload, signature):
            return False
        
        assert not verify_provenance_entry(entry, SAMPLE_CONTENT_HASH, mock_verify)


class TestVerifyProvenanceChain:
    """Tests for verify_provenance_chain function."""

    def test_verify_valid_chain(self):
        """Test verifying a valid chain."""
        entry = ProvenanceEntry(
            role="author",
            identity=SAMPLE_IDENTITY,
            timestamp="2026-02-08T00:00:00Z",
            signature=SAMPLE_SIGNATURE,
            parent_hash=SAMPLE_CONTENT_HASH,
        )
        prov = Provenance(content_hash=SAMPLE_CONTENT_HASH, entries=[entry])
        
        def mock_verify(identity, payload, signature):
            return True
        
        valid, errors = verify_provenance_chain(prov, mock_verify)
        assert valid
        assert errors == []

    def test_verify_chain_with_invalid_signature(self):
        """Test verifying chain with invalid signature."""
        entry = ProvenanceEntry(
            role="author",
            identity=SAMPLE_IDENTITY,
            timestamp="2026-02-08T00:00:00Z",
            signature=SAMPLE_SIGNATURE,
            parent_hash=SAMPLE_CONTENT_HASH,
        )
        prov = Provenance(content_hash=SAMPLE_CONTENT_HASH, entries=[entry])
        
        def mock_verify(identity, payload, signature):
            return False  # All signatures invalid
        
        valid, errors = verify_provenance_chain(prov, mock_verify)
        assert not valid
        assert len(errors) == 1
        assert "Invalid signature" in errors[0]


class TestCheckProvenanceRequirements:
    """Tests for check_provenance_requirements function."""

    def test_empty_requirements_pass(self):
        """Test that empty requirements pass."""
        prov = Provenance(content_hash=SAMPLE_CONTENT_HASH)
        valid, unmet = check_provenance_requirements(prov)
        assert valid
        assert unmet == []

    def test_min_depth_requirement(self):
        """Test minimum depth requirement."""
        prov = Provenance(content_hash=SAMPLE_CONTENT_HASH)
        
        valid, unmet = check_provenance_requirements(prov, min_depth=1)
        assert not valid
        assert "Chain depth" in unmet[0]

    def test_required_roles(self):
        """Test required roles requirement."""
        entry = ProvenanceEntry(
            role="author",
            identity=SAMPLE_IDENTITY,
            timestamp="2026-02-08T00:00:00Z",
            signature=SAMPLE_SIGNATURE,
        )
        prov = Provenance(content_hash=SAMPLE_CONTENT_HASH, entries=[entry])
        
        # Has author, requires auditor
        valid, unmet = check_provenance_requirements(
            prov, required_roles=["author", "auditor"]
        )
        assert not valid
        assert "Missing required role: auditor" in unmet

    def test_min_auditors(self):
        """Test minimum auditors requirement."""
        entries = [
            ProvenanceEntry(
                role="author",
                identity=SAMPLE_IDENTITY,
                timestamp="2026-02-08T00:00:00Z",
                signature=SAMPLE_SIGNATURE,
            ),
            ProvenanceEntry(
                role="auditor",
                identity=SAMPLE_IDENTITY_2,
                timestamp="2026-02-08T01:00:00Z",
                signature=SAMPLE_SIGNATURE,
            ),
        ]
        prov = Provenance(content_hash=SAMPLE_CONTENT_HASH, entries=entries)
        
        # Has 1 auditor, requires 2
        valid, unmet = check_provenance_requirements(prov, min_auditors=2)
        assert not valid
        assert "Auditors 1 < required 2" in unmet

    def test_all_requirements_met(self):
        """Test when all requirements are met."""
        entries = [
            ProvenanceEntry(
                role="author",
                identity=SAMPLE_IDENTITY,
                timestamp="2026-02-08T00:00:00Z",
                signature=SAMPLE_SIGNATURE,
            ),
            ProvenanceEntry(
                role="auditor",
                identity=SAMPLE_IDENTITY_2,
                timestamp="2026-02-08T01:00:00Z",
                signature=SAMPLE_SIGNATURE,
            ),
            ProvenanceEntry(
                role="voucher",
                identity=SAMPLE_IDENTITY_3,
                timestamp="2026-02-08T02:00:00Z",
                signature=SAMPLE_SIGNATURE,
            ),
        ]
        prov = Provenance(content_hash=SAMPLE_CONTENT_HASH, entries=entries)
        
        valid, unmet = check_provenance_requirements(
            prov,
            min_depth=3,
            required_roles=["author", "auditor", "voucher"],
            min_auditors=1,
            min_vouchers=1,
        )
        assert valid
        assert unmet == []


class TestProvenanceFromDict:
    """Tests for provenance_from_dict function."""

    def test_from_none(self):
        """Test creating from None."""
        assert provenance_from_dict(None) is None

    def test_from_dict(self):
        """Test creating from dict."""
        data = {
            "content_hash": SAMPLE_CONTENT_HASH,
            "entries": [
                {
                    "role": "author",
                    "identity": SAMPLE_IDENTITY,
                    "timestamp": "2026-02-08T00:00:00Z",
                    "signature": SAMPLE_SIGNATURE,
                }
            ],
        }
        prov = provenance_from_dict(data)
        assert prov is not None
        assert prov.chain_depth() == 1
        assert prov.has_role("author")
