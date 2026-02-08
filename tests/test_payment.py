"""Tests for payment integration."""

import pytest
from datetime import datetime, timedelta, timezone

from epp.payment import (
    PaymentProof,
    PaymentRequest,
    StakeReference,
    create_payment_request,
    payment_proof_from_dict,
    payment_request_from_dict,
    stake_reference_from_dict,
    verify_payment_proof,
)

# Test fixtures
SAMPLE_EVM_ADDRESS = "0x1234567890123456789012345678901234567890"
SAMPLE_EVM_ADDRESS_2 = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
SAMPLE_EVM_TX_HASH = "0x" + "a" * 64
SAMPLE_SOLANA_ADDRESS = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
SAMPLE_IDENTITY = "a" * 64


class TestPaymentRequest:
    """Tests for PaymentRequest model."""

    def test_create_payment_request(self):
        """Test creating a payment request."""
        req = PaymentRequest(
            amount="0.01",
            currency="USDC",
            recipient=SAMPLE_EVM_ADDRESS,
            chain="base",
        )
        assert req.amount == "0.01"
        assert req.currency == "USDC"
        assert req.chain == "base"
        assert req.required is True  # Default

    def test_currency_normalized_to_uppercase(self):
        """Test currency is normalized to uppercase."""
        req = PaymentRequest(
            amount="1.0",
            currency="usdc",
            recipient=SAMPLE_EVM_ADDRESS,
            chain="base",
        )
        assert req.currency == "USDC"

    def test_chain_normalized_to_lowercase(self):
        """Test chain is normalized to lowercase."""
        req = PaymentRequest(
            amount="1.0",
            currency="USDC",
            recipient=SAMPLE_EVM_ADDRESS,
            chain="BASE",
        )
        assert req.chain == "base"

    def test_invalid_amount_rejected(self):
        """Test that invalid amounts are rejected."""
        with pytest.raises(ValueError, match="Invalid amount"):
            PaymentRequest(
                amount="not-a-number",
                currency="USDC",
                recipient=SAMPLE_EVM_ADDRESS,
                chain="base",
            )

    def test_negative_amount_rejected(self):
        """Test that negative amounts are rejected."""
        with pytest.raises(ValueError, match="must be positive"):
            PaymentRequest(
                amount="-1.0",
                currency="USDC",
                recipient=SAMPLE_EVM_ADDRESS,
                chain="base",
            )

    def test_with_expiration(self):
        """Test payment request with expiration."""
        expires = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
        req = PaymentRequest(
            amount="1.0",
            currency="USDC",
            recipient=SAMPLE_EVM_ADDRESS,
            chain="base",
            expires_at=expires,
        )
        assert not req.is_expired()

    def test_expired_request(self):
        """Test detecting expired request."""
        expires = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        req = PaymentRequest(
            amount="1.0",
            currency="USDC",
            recipient=SAMPLE_EVM_ADDRESS,
            chain="base",
            expires_at=expires,
        )
        assert req.is_expired()

    def test_to_402_response(self):
        """Test converting to 402 response format."""
        req = PaymentRequest(
            amount="0.01",
            currency="USDC",
            recipient=SAMPLE_EVM_ADDRESS,
            chain="base",
            memo="API call: weather",
        )
        response = req.to_402_response()

        assert response["payment_required"] is True
        assert response["amount"] == "0.01"
        assert response["currency"] == "USDC"
        assert response["memo"] == "API call: weather"


class TestPaymentProof:
    """Tests for PaymentProof model."""

    def test_create_payment_proof(self):
        """Test creating a payment proof."""
        proof = PaymentProof(
            tx_hash=SAMPLE_EVM_TX_HASH,
            chain="base",
            amount="0.01",
            currency="USDC",
            payer=SAMPLE_EVM_ADDRESS,
            recipient=SAMPLE_EVM_ADDRESS_2,
        )
        assert proof.tx_hash == SAMPLE_EVM_TX_HASH.lower()
        assert proof.chain == "base"

    def test_tx_hash_normalized_to_lowercase(self):
        """Test EVM tx hash is normalized to lowercase."""
        tx_hash = "0x" + "A" * 64
        proof = PaymentProof(
            tx_hash=tx_hash,
            chain="base",
            amount="0.01",
            currency="USDC",
            payer=SAMPLE_EVM_ADDRESS,
            recipient=SAMPLE_EVM_ADDRESS_2,
        )
        assert proof.tx_hash == tx_hash.lower()

    def test_invalid_tx_hash_rejected(self):
        """Test that invalid tx hashes are rejected."""
        with pytest.raises(ValueError, match="Invalid"):
            PaymentProof(
                tx_hash="invalid",
                chain="base",
                amount="0.01",
                currency="USDC",
                payer=SAMPLE_EVM_ADDRESS,
                recipient=SAMPLE_EVM_ADDRESS_2,
            )

    def test_get_explorer_url_base(self):
        """Test getting explorer URL for Base."""
        proof = PaymentProof(
            tx_hash=SAMPLE_EVM_TX_HASH,
            chain="base",
            amount="0.01",
            currency="USDC",
            payer=SAMPLE_EVM_ADDRESS,
            recipient=SAMPLE_EVM_ADDRESS_2,
        )
        url = proof.get_explorer_url()
        assert url is not None
        assert "basescan.org" in url
        assert proof.tx_hash in url

    def test_get_explorer_url_ethereum(self):
        """Test getting explorer URL for Ethereum."""
        proof = PaymentProof(
            tx_hash=SAMPLE_EVM_TX_HASH,
            chain="ethereum",
            amount="0.01",
            currency="ETH",
            payer=SAMPLE_EVM_ADDRESS,
            recipient=SAMPLE_EVM_ADDRESS_2,
        )
        url = proof.get_explorer_url()
        assert "etherscan.io" in url

    def test_get_explorer_url_unknown_chain(self):
        """Test getting explorer URL for unknown chain."""
        proof = PaymentProof(
            tx_hash=SAMPLE_EVM_TX_HASH,
            chain="unknown-chain",
            amount="0.01",
            currency="TOKEN",
            payer=SAMPLE_EVM_ADDRESS,
            recipient=SAMPLE_EVM_ADDRESS_2,
        )
        assert proof.get_explorer_url() is None


class TestStakeReference:
    """Tests for StakeReference model."""

    def test_create_stake_reference(self):
        """Test creating a stake reference."""
        stake = StakeReference(
            contract=SAMPLE_EVM_ADDRESS,
            chain="base",
            amount="100",
            currency="USDC",
            staker=SAMPLE_IDENTITY,
        )
        assert stake.contract == SAMPLE_EVM_ADDRESS.lower()
        assert stake.amount == "100"

    def test_staker_must_be_hex_pubkey(self):
        """Test that staker must be a 64-char hex pubkey."""
        with pytest.raises(ValueError, match="64 hex characters"):
            StakeReference(
                contract=SAMPLE_EVM_ADDRESS,
                chain="base",
                amount="100",
                currency="USDC",
                staker="invalid",
            )

    def test_invalid_stake_amount(self):
        """Test that invalid stake amounts are rejected."""
        with pytest.raises(ValueError, match="Invalid stake amount"):
            StakeReference(
                contract=SAMPLE_EVM_ADDRESS,
                chain="base",
                amount="not-a-number",
                currency="USDC",
                staker=SAMPLE_IDENTITY,
            )


class TestCreatePaymentRequest:
    """Tests for create_payment_request function."""

    def test_create_with_defaults(self):
        """Test creating payment request with defaults."""
        req = create_payment_request(
            amount="1.0",
            currency="USDC",
            recipient=SAMPLE_EVM_ADDRESS,
            chain="base",
        )
        assert req.amount == "1.0"
        assert req.required is True
        assert req.expires_at is not None
        assert not req.is_expired()

    def test_create_with_memo(self):
        """Test creating payment request with memo."""
        req = create_payment_request(
            amount="0.01",
            currency="USDC",
            recipient=SAMPLE_EVM_ADDRESS,
            chain="base",
            memo="weather-api-call",
        )
        assert req.memo == "weather-api-call"

    def test_create_optional_payment(self):
        """Test creating optional (tip) payment."""
        req = create_payment_request(
            amount="1.0",
            currency="USDC",
            recipient=SAMPLE_EVM_ADDRESS,
            chain="base",
            required=False,
        )
        assert req.required is False


class TestVerifyPaymentProof:
    """Tests for verify_payment_proof function."""

    def test_verify_matching_proof(self):
        """Test verifying a matching proof."""
        request = PaymentRequest(
            amount="1.0",
            currency="USDC",
            recipient=SAMPLE_EVM_ADDRESS,
            chain="base",
        )
        proof = PaymentProof(
            tx_hash=SAMPLE_EVM_TX_HASH,
            chain="base",
            amount="1.0",
            currency="USDC",
            payer=SAMPLE_EVM_ADDRESS_2,
            recipient=SAMPLE_EVM_ADDRESS,
        )

        valid, issues = verify_payment_proof(proof, request)
        assert valid
        assert issues == []

    def test_verify_chain_mismatch(self):
        """Test detecting chain mismatch."""
        request = PaymentRequest(
            amount="1.0",
            currency="USDC",
            recipient=SAMPLE_EVM_ADDRESS,
            chain="base",
        )
        proof = PaymentProof(
            tx_hash=SAMPLE_EVM_TX_HASH,
            chain="ethereum",  # Wrong chain
            amount="1.0",
            currency="USDC",
            payer=SAMPLE_EVM_ADDRESS_2,
            recipient=SAMPLE_EVM_ADDRESS,
        )

        valid, issues = verify_payment_proof(proof, request)
        assert not valid
        assert any("Chain mismatch" in i for i in issues)

    def test_verify_currency_mismatch(self):
        """Test detecting currency mismatch."""
        request = PaymentRequest(
            amount="1.0",
            currency="USDC",
            recipient=SAMPLE_EVM_ADDRESS,
            chain="base",
        )
        proof = PaymentProof(
            tx_hash=SAMPLE_EVM_TX_HASH,
            chain="base",
            amount="1.0",
            currency="ETH",  # Wrong currency
            payer=SAMPLE_EVM_ADDRESS_2,
            recipient=SAMPLE_EVM_ADDRESS,
        )

        valid, issues = verify_payment_proof(proof, request)
        assert not valid
        assert any("Currency mismatch" in i for i in issues)

    def test_verify_amount_too_low(self):
        """Test detecting insufficient amount."""
        request = PaymentRequest(
            amount="1.0",
            currency="USDC",
            recipient=SAMPLE_EVM_ADDRESS,
            chain="base",
        )
        proof = PaymentProof(
            tx_hash=SAMPLE_EVM_TX_HASH,
            chain="base",
            amount="0.5",  # Too low
            currency="USDC",
            payer=SAMPLE_EVM_ADDRESS_2,
            recipient=SAMPLE_EVM_ADDRESS,
        )

        valid, issues = verify_payment_proof(proof, request)
        assert not valid
        assert any("Amount too low" in i for i in issues)

    def test_verify_amount_with_tolerance(self):
        """Test amount verification with tolerance."""
        request = PaymentRequest(
            amount="1.0",
            currency="USDC",
            recipient=SAMPLE_EVM_ADDRESS,
            chain="base",
        )
        proof = PaymentProof(
            tx_hash=SAMPLE_EVM_TX_HASH,
            chain="base",
            amount="0.995",  # 0.5% less
            currency="USDC",
            payer=SAMPLE_EVM_ADDRESS_2,
            recipient=SAMPLE_EVM_ADDRESS,
        )

        # Should pass with default 1% tolerance
        valid, issues = verify_payment_proof(proof, request, tolerance_percent=1.0)
        assert valid

    def test_verify_recipient_mismatch(self):
        """Test detecting recipient mismatch."""
        request = PaymentRequest(
            amount="1.0",
            currency="USDC",
            recipient=SAMPLE_EVM_ADDRESS,
            chain="base",
        )
        proof = PaymentProof(
            tx_hash=SAMPLE_EVM_TX_HASH,
            chain="base",
            amount="1.0",
            currency="USDC",
            payer=SAMPLE_EVM_ADDRESS_2,
            recipient=SAMPLE_EVM_ADDRESS_2,  # Wrong recipient
        )

        valid, issues = verify_payment_proof(proof, request)
        assert not valid
        assert any("Recipient mismatch" in i for i in issues)


class TestFromDictFunctions:
    """Tests for from_dict helper functions."""

    def test_payment_request_from_none(self):
        """Test payment_request_from_dict with None."""
        assert payment_request_from_dict(None) is None

    def test_payment_request_from_dict(self):
        """Test payment_request_from_dict."""
        data = {
            "amount": "1.0",
            "currency": "USDC",
            "recipient": SAMPLE_EVM_ADDRESS,
            "chain": "base",
        }
        req = payment_request_from_dict(data)
        assert req is not None
        assert req.amount == "1.0"

    def test_payment_proof_from_none(self):
        """Test payment_proof_from_dict with None."""
        assert payment_proof_from_dict(None) is None

    def test_payment_proof_from_dict(self):
        """Test payment_proof_from_dict."""
        data = {
            "tx_hash": SAMPLE_EVM_TX_HASH,
            "chain": "base",
            "amount": "1.0",
            "currency": "USDC",
            "payer": SAMPLE_EVM_ADDRESS,
            "recipient": SAMPLE_EVM_ADDRESS_2,
        }
        proof = payment_proof_from_dict(data)
        assert proof is not None
        assert proof.chain == "base"

    def test_stake_reference_from_none(self):
        """Test stake_reference_from_dict with None."""
        assert stake_reference_from_dict(None) is None

    def test_stake_reference_from_dict(self):
        """Test stake_reference_from_dict."""
        data = {
            "contract": SAMPLE_EVM_ADDRESS,
            "chain": "base",
            "amount": "100",
            "currency": "USDC",
            "staker": SAMPLE_IDENTITY,
        }
        stake = stake_reference_from_dict(data)
        assert stake is not None
        assert stake.amount == "100"
