"""Tests for the v1.1 attestations module."""

import base64

import pytest
from cryptography.exceptions import InvalidSignature

from epp.attestations import (
    AttestationEntry,
    Attestations,
    attestations_from_dict,
    compute_subject_hash,
    create_attestation_entry,
    verify_attestation_entry,
    verify_attestations,
)
from epp.crypto.keys import KeyPair, PublicKey

# Helpers ------------------------------------------------------------------- #


def _make_signer(kp: KeyPair):
    def sign(data: bytes) -> str:
        return base64.b64encode(kp.private_key.sign(data)).decode("ascii")

    return sign


def _verify(identity_hex: str, payload: bytes, sig_b64: str) -> bool:
    try:
        PublicKey.from_hex(identity_hex).public_key.verify(base64.b64decode(sig_b64), payload)
        return True
    except (InvalidSignature, Exception):
        return False


# AttestationEntry --------------------------------------------------------- #


class TestAttestationEntry:
    def test_role_lowercased_and_validated(self):
        kp = KeyPair.generate()
        entry = create_attestation_entry(
            role="AUDITOR",
            identity=kp.public_key_hex(),
            subject_hash="ab" * 32,
            sign_func=_make_signer(kp),
        )
        assert entry.role == "auditor"

    def test_identity_must_be_64_hex(self):
        with pytest.raises(ValueError):
            AttestationEntry(
                role="auditor",
                identity="too-short",
                timestamp="2026-01-01T00:00:00Z",
                signature="x",
                subject_hash="ab" * 32,
            )

    def test_subject_hash_must_be_hex(self):
        with pytest.raises(ValueError):
            AttestationEntry(
                role="auditor",
                identity="ab" * 32,
                timestamp="2026-01-01T00:00:00Z",
                signature="x",
                subject_hash="not-hex!",
            )

    def test_signing_payload_is_deterministic(self):
        kp = KeyPair.generate()
        sh = compute_subject_hash(b"hello")
        e = create_attestation_entry(
            role="auditor",
            identity=kp.public_key_hex(),
            subject_hash=sh,
            sign_func=_make_signer(kp),
            statement="ok",
        )
        # signing payload is reconstructible
        payload = e.get_signing_payload()
        assert payload.startswith(b"auditor\n")
        assert sh.encode() in payload

    def test_verify_entry_succeeds_for_valid_signature(self):
        kp = KeyPair.generate()
        sh = compute_subject_hash(b"content")
        entry = create_attestation_entry(
            role="auditor",
            identity=kp.public_key_hex(),
            subject_hash=sh,
            sign_func=_make_signer(kp),
        )
        assert verify_attestation_entry(entry, _verify) is True

    def test_verify_entry_fails_for_wrong_key(self):
        kp = KeyPair.generate()
        other = KeyPair.generate()
        sh = compute_subject_hash(b"content")
        entry = create_attestation_entry(
            role="auditor",
            identity=other.public_key_hex(),  # claims to be other
            subject_hash=sh,
            sign_func=_make_signer(kp),  # but signed by kp
        )
        assert verify_attestation_entry(entry, _verify) is False


# Attestations (set semantics) --------------------------------------------- #


class TestAttestations:
    def test_threshold_violation_rejected_at_construction(self):
        kp = KeyPair.generate()
        sh = compute_subject_hash(b"x")
        e = create_attestation_entry(
            role="auditor",
            identity=kp.public_key_hex(),
            subject_hash=sh,
            sign_func=_make_signer(kp),
        )
        with pytest.raises(ValueError, match="threshold"):
            Attestations(threshold=2, required_roles=[], entries=[e])

    def test_missing_required_role_rejected_at_construction(self):
        kp = KeyPair.generate()
        sh = compute_subject_hash(b"x")
        e = create_attestation_entry(
            role="auditor",
            identity=kp.public_key_hex(),
            subject_hash=sh,
            sign_func=_make_signer(kp),
        )
        with pytest.raises(ValueError, match="missing required roles"):
            Attestations(threshold=1, required_roles=["reviewer"], entries=[e])

    def test_required_roles_lowercased(self):
        kp = KeyPair.generate()
        sh = compute_subject_hash(b"x")
        e = create_attestation_entry(
            role="reviewer",
            identity=kp.public_key_hex(),
            subject_hash=sh,
            sign_func=_make_signer(kp),
        )
        a = Attestations(threshold=1, required_roles=["REVIEWER"], entries=[e])
        assert a.required_roles == ["reviewer"]

    def test_invalid_required_role_rejected(self):
        with pytest.raises(ValueError, match="Invalid required_role"):
            Attestations(threshold=1, required_roles=["bad role!"], entries=[])

    def test_get_by_role(self):
        kp1 = KeyPair.generate()
        kp2 = KeyPair.generate()
        sh = compute_subject_hash(b"x")
        e1 = create_attestation_entry(
            role="auditor",
            identity=kp1.public_key_hex(),
            subject_hash=sh,
            sign_func=_make_signer(kp1),
        )
        e2 = create_attestation_entry(
            role="reviewer",
            identity=kp2.public_key_hex(),
            subject_hash=sh,
            sign_func=_make_signer(kp2),
        )
        a = Attestations(threshold=2, required_roles=["auditor", "reviewer"], entries=[e1, e2])
        assert a.has_role("auditor")
        assert len(a.get_by_role("reviewer")) == 1


class TestVerifyAttestations:
    def test_all_valid(self):
        kp = KeyPair.generate()
        sh = compute_subject_hash(b"content")
        e = create_attestation_entry(
            role="auditor",
            identity=kp.public_key_hex(),
            subject_hash=sh,
            sign_func=_make_signer(kp),
        )
        a = Attestations(threshold=1, required_roles=["auditor"], entries=[e])
        ok, errors = verify_attestations(a, sh, _verify)
        assert ok and errors == []

    def test_subject_hash_mismatch(self):
        kp = KeyPair.generate()
        sh = compute_subject_hash(b"content")
        e = create_attestation_entry(
            role="auditor",
            identity=kp.public_key_hex(),
            subject_hash=sh,
            sign_func=_make_signer(kp),
        )
        a = Attestations(threshold=1, required_roles=["auditor"], entries=[e])
        ok, errors = verify_attestations(a, compute_subject_hash(b"other"), _verify)
        assert not ok
        assert any("subject_hash mismatch" in err for err in errors)

    def test_tampered_signature(self):
        kp = KeyPair.generate()
        sh = compute_subject_hash(b"content")
        e = create_attestation_entry(
            role="auditor",
            identity=kp.public_key_hex(),
            subject_hash=sh,
            sign_func=_make_signer(kp),
        )
        # tamper with signature by flipping a byte
        sig_bytes = base64.b64decode(e.signature)
        bad_sig = base64.b64encode(b"\x00" + sig_bytes[1:]).decode("ascii")
        tampered = AttestationEntry(
            role=e.role,
            identity=e.identity,
            timestamp=e.timestamp,
            signature=bad_sig,
            subject_hash=e.subject_hash,
            statement=e.statement,
        )
        a = Attestations(threshold=1, required_roles=["auditor"], entries=[tampered])
        ok, errors = verify_attestations(a, sh, _verify)
        assert not ok
        assert any("signature invalid" in err for err in errors)


class TestRoundTrip:
    def test_dict_round_trip(self):
        kp = KeyPair.generate()
        sh = compute_subject_hash(b"content")
        e = create_attestation_entry(
            role="auditor",
            identity=kp.public_key_hex(),
            subject_hash=sh,
            sign_func=_make_signer(kp),
        )
        original = Attestations(threshold=1, required_roles=["auditor"], entries=[e])
        as_dict = original.model_dump(exclude_none=True)
        rebuilt = attestations_from_dict(as_dict)
        assert rebuilt is not None
        assert rebuilt.threshold == 1
        assert rebuilt.entries[0].signature == e.signature

    def test_attestations_from_dict_none(self):
        assert attestations_from_dict(None) is None
