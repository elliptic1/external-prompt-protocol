"""
Tests for AI-to-AI services module.
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from epp.payment import PaymentProof
from epp.services import (
    ServiceTier,
    ServiceListing,
    ServiceRequest,
    ServiceResponse,
    ConsultationSession,
    JurisdictionInfo,
    create_service_listing,
    create_legal_consultation_listing,
    create_service_request,
    create_service_response,
    create_consultation_session,
    service_request_to_payload,
    service_response_to_payload,
    service_listing_to_payload,
)


# Test public key (valid 64-char hex)
TEST_PROVIDER_KEY = "a" * 64
TEST_CLIENT_KEY = "b" * 64


class TestServiceTier:
    """Tests for ServiceTier model."""

    def test_basic_tier(self):
        tier = ServiceTier(
            name="basic",
            price="5.00",
            billing="per-query",
        )
        assert tier.name == "basic"
        assert tier.price == "5.00"
        assert tier.currency == "USDC"  # default
        assert tier.billing == "per-query"

    def test_tier_with_all_fields(self):
        tier = ServiceTier(
            name="expert",
            description="Full consultation session",
            price="100.00",
            currency="ETH",
            billing="per-session",
            response_time="2m",
            max_turns=10,
            features=["Multi-turn", "Document review"],
        )
        assert tier.max_turns == 10
        assert len(tier.features) == 2

    def test_invalid_price(self):
        with pytest.raises(ValueError, match="Invalid price"):
            ServiceTier(name="bad", price="not-a-number", billing="per-query")

    def test_negative_price(self):
        with pytest.raises(ValueError, match="cannot be negative"):
            ServiceTier(name="bad", price="-5.00", billing="per-query")

    def test_zero_price_allowed(self):
        tier = ServiceTier(name="free", price="0", billing="per-query")
        assert tier.price == "0"


class TestServiceListing:
    """Tests for ServiceListing model."""

    def test_basic_listing(self):
        listing = create_service_listing(
            provider=TEST_PROVIDER_KEY,
            category="legal",
            title="Test Legal Service",
            description="A test service",
            price="10.00",
            payment_address="0x742d35Cc6634C0532925a3b844Bc9e7595f8abcd",
            inbox_url="https://inbox.example.com/epp",
            scope="legal-test",
        )
        assert listing.provider == TEST_PROVIDER_KEY
        assert listing.category == "legal"
        assert listing.active is True
        assert len(listing.tiers) == 1

    def test_legal_consultation_listing(self):
        listing = create_legal_consultation_listing(
            provider=TEST_PROVIDER_KEY,
            title="California Employment Law",
            description="Employment law consultation",
            jurisdictions=["US-CA"],
            specialties=["employment-law"],
            payment_address="0x742d35Cc6634C0532925a3b844Bc9e7595f8abcd",
            inbox_url="https://inbox.example.com/epp",
        )

        assert listing.category == "legal"
        assert len(listing.tiers) == 3
        assert listing.tiers[0].name == "basic"
        assert listing.tiers[0].price == "5.00"
        assert listing.tiers[1].name == "priority"
        assert listing.tiers[2].name == "expert"
        assert listing.jurisdiction is not None
        assert "US-CA" in listing.jurisdiction.jurisdictions
        assert len(listing.jurisdiction.disclaimers) > 0

    def test_get_tier(self):
        listing = create_legal_consultation_listing(
            provider=TEST_PROVIDER_KEY,
            title="Test",
            description="Test",
            jurisdictions=["US"],
            specialties=[],
            payment_address="0x" + "0" * 40,
            inbox_url="https://inbox.example.com",
        )

        basic = listing.get_tier("basic")
        assert basic is not None
        assert basic.price == "5.00"

        expert = listing.get_tier("expert")
        assert expert is not None
        assert expert.billing == "per-session"

        nonexistent = listing.get_tier("nonexistent")
        assert nonexistent is None

    def test_create_payment_request(self):
        listing = create_legal_consultation_listing(
            provider=TEST_PROVIDER_KEY,
            title="Test",
            description="Test",
            jurisdictions=["US"],
            specialties=[],
            payment_address="0x742d35Cc6634C0532925a3b844Bc9e7595f8abcd",
            inbox_url="https://inbox.example.com",
        )

        payment = listing.create_payment_request(tier_name="priority")
        assert payment.amount == "25.00"
        assert payment.currency == "USDC"
        assert payment.recipient == "0x742d35Cc6634C0532925a3b844Bc9e7595f8abcd"
        assert payment.chain == "base"
        assert payment.expires_at is not None

    def test_invalid_provider_key(self):
        with pytest.raises(ValueError, match="64 hex"):
            create_service_listing(
                provider="invalid",
                category="legal",
                title="Test",
                description="Test",
                price="10",
                payment_address="0x" + "0" * 40,
                inbox_url="https://test.com",
                scope="test",
            )


class TestServiceRequest:
    """Tests for ServiceRequest model."""

    def test_basic_request(self):
        request = ServiceRequest(
            service_id="test-service-123",
            tier="basic",
            client=TEST_CLIENT_KEY,
            query="What are my legal rights?",
        )
        assert request.service_id == "test-service-123"
        assert request.client == TEST_CLIENT_KEY
        assert request.query == "What are my legal rights?"
        assert request.request_id is not None
        assert request.timestamp is not None

    def test_request_with_context(self):
        request = ServiceRequest(
            service_id="test-service",
            client=TEST_CLIENT_KEY,
            query="Legal question",
            context={
                "location": "California",
                "situation": "employment",
            },
            preferences={
                "response_format": "detailed",
                "include_citations": True,
            },
        )
        assert request.context["location"] == "California"
        assert request.preferences["include_citations"] is True

    def test_request_with_payment_proof(self):
        proof = PaymentProof(
            tx_hash="0x" + "a" * 64,
            chain="base",
            amount="5.00",
            currency="USDC",
            payer="0x" + "1" * 40,
            recipient="0x" + "2" * 40,
        )
        request = ServiceRequest(
            service_id="test",
            client=TEST_CLIENT_KEY,
            query="Question",
            payment_proof=proof,
        )
        assert request.payment_proof.amount == "5.00"

    def test_request_with_session(self):
        request = ServiceRequest(
            service_id="test",
            client=TEST_CLIENT_KEY,
            query="Follow-up question",
            session_id="session-123",
            in_reply_to="previous-response-456",
        )
        assert request.session_id == "session-123"
        assert request.in_reply_to == "previous-response-456"


class TestServiceResponse:
    """Tests for ServiceResponse model."""

    def test_basic_response(self):
        response = ServiceResponse(
            request_id="req-123",
            service_id="svc-456",
            provider=TEST_PROVIDER_KEY,
            response="Here is the legal information...",
        )
        assert response.request_id == "req-123"
        assert response.provider == TEST_PROVIDER_KEY
        assert response.response_id is not None

    def test_response_with_metadata(self):
        response = ServiceResponse(
            request_id="req-123",
            service_id="svc-456",
            provider=TEST_PROVIDER_KEY,
            response="Legal analysis...",
            confidence=0.85,
            citations=[
                {"code": "Cal. Lab. Code § 98.6", "description": "Retaliation"},
            ],
            disclaimers=["This is not legal advice"],
            follow_up_suggested=True,
            follow_up_questions=["Do you have documentation?"],
            processing_time_ms=1500,
        )
        assert response.confidence == 0.85
        assert len(response.citations) == 1
        assert response.follow_up_suggested is True

    def test_response_with_session(self):
        response = ServiceResponse(
            request_id="req-123",
            service_id="svc-456",
            provider=TEST_PROVIDER_KEY,
            response="Response...",
            session_id="session-789",
            turns_remaining=8,
        )
        assert response.session_id == "session-789"
        assert response.turns_remaining == 8


class TestConsultationSession:
    """Tests for ConsultationSession model."""

    def test_session_creation(self):
        listing = create_legal_consultation_listing(
            provider=TEST_PROVIDER_KEY,
            title="Test",
            description="Test",
            jurisdictions=["US"],
            specialties=[],
            payment_address="0x" + "0" * 40,
            inbox_url="https://test.com",
        )

        proof = PaymentProof(
            tx_hash="0x" + "a" * 64,
            chain="base",
            amount="100.00",
            currency="USDC",
            payer="0x" + "1" * 40,
            recipient="0x" + "2" * 40,
        )

        session = create_consultation_session(
            service_listing=listing,
            tier_name="expert",
            client=TEST_CLIENT_KEY,
            payment_proof=proof,
        )

        assert session.service_id == listing.service_id
        assert session.tier == "expert"
        assert session.client == TEST_CLIENT_KEY
        assert session.provider == TEST_PROVIDER_KEY
        assert session.max_turns == 10
        assert session.turns_used == 0
        assert session.status == "active"

    def test_session_is_active(self):
        session = ConsultationSession(
            service_id="test",
            tier="expert",
            client=TEST_CLIENT_KEY,
            provider=TEST_PROVIDER_KEY,
            payment_proof=PaymentProof(
                tx_hash="0x" + "a" * 64,
                chain="base",
                amount="100",
                currency="USDC",
                payer="0x" + "1" * 40,
                recipient="0x" + "2" * 40,
            ),
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=24)).isoformat().replace("+00:00", "Z"),
            max_turns=10,
        )
        assert session.is_active() is True
        assert session.has_turns_remaining() is True

    def test_session_expired(self):
        session = ConsultationSession(
            service_id="test",
            tier="expert",
            client=TEST_CLIENT_KEY,
            provider=TEST_PROVIDER_KEY,
            payment_proof=PaymentProof(
                tx_hash="0x" + "a" * 64,
                chain="base",
                amount="100",
                currency="USDC",
                payer="0x" + "1" * 40,
                recipient="0x" + "2" * 40,
            ),
            expires_at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            max_turns=10,
        )
        assert session.is_expired() is True
        assert session.is_active() is False

    def test_session_record_exchange(self):
        session = ConsultationSession(
            service_id="test",
            tier="expert",
            client=TEST_CLIENT_KEY,
            provider=TEST_PROVIDER_KEY,
            payment_proof=PaymentProof(
                tx_hash="0x" + "a" * 64,
                chain="base",
                amount="100",
                currency="USDC",
                payer="0x" + "1" * 40,
                recipient="0x" + "2" * 40,
            ),
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=24)).isoformat().replace("+00:00", "Z"),
            max_turns=3,
        )

        session.record_exchange("req-1", "resp-1")
        assert session.turns_used == 1
        assert len(session.exchanges) == 1

        session.record_exchange("req-2", "resp-2")
        assert session.turns_used == 2

        session.record_exchange("req-3", "resp-3")
        assert session.turns_used == 3
        assert session.status == "completed"  # Auto-completed at max turns

    def test_session_wrong_billing_type(self):
        listing = create_legal_consultation_listing(
            provider=TEST_PROVIDER_KEY,
            title="Test",
            description="Test",
            jurisdictions=["US"],
            specialties=[],
            payment_address="0x" + "0" * 40,
            inbox_url="https://test.com",
        )

        proof = PaymentProof(
            tx_hash="0x" + "a" * 64,
            chain="base",
            amount="5.00",
            currency="USDC",
            payer="0x" + "1" * 40,
            recipient="0x" + "2" * 40,
        )

        with pytest.raises(ValueError, match="not per-session"):
            create_consultation_session(
                service_listing=listing,
                tier_name="basic",  # basic is per-query, not per-session
                client=TEST_CLIENT_KEY,
                payment_proof=proof,
            )


class TestPayloadConversions:
    """Tests for payload conversion functions."""

    def test_service_request_to_payload(self):
        request = ServiceRequest(
            service_id="test-service",
            client=TEST_CLIENT_KEY,
            query="Legal question",
        )
        payload = service_request_to_payload(request)

        assert payload["type"] == "service-request"
        assert payload["version"] == "1"
        assert "request" in payload
        assert payload["request"]["query"] == "Legal question"

    def test_service_response_to_payload(self):
        response = ServiceResponse(
            request_id="req-123",
            service_id="svc-456",
            provider=TEST_PROVIDER_KEY,
            response="Legal response...",
        )
        payload = service_response_to_payload(response)

        assert payload["type"] == "service-response"
        assert payload["version"] == "1"
        assert "response" in payload
        assert payload["response"]["response"] == "Legal response..."

    def test_service_listing_to_payload(self):
        listing = create_service_listing(
            provider=TEST_PROVIDER_KEY,
            category="legal",
            title="Test Service",
            description="A test",
            price="10.00",
            payment_address="0x" + "0" * 40,
            inbox_url="https://test.com",
            scope="test",
        )
        payload = service_listing_to_payload(listing)

        assert payload["type"] == "service-listing"
        assert payload["version"] == "1"
        assert "listing" in payload
        assert payload["listing"]["title"] == "Test Service"


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_create_service_request_helper(self):
        listing = create_service_listing(
            provider=TEST_PROVIDER_KEY,
            category="legal",
            title="Test",
            description="Test",
            price="10.00",
            payment_address="0x" + "0" * 40,
            inbox_url="https://test.com",
            scope="test",
        )

        request = create_service_request(
            service_listing=listing,
            client=TEST_CLIENT_KEY,
            query="What are my rights?",
            context={"location": "CA"},
        )

        assert request.service_id == listing.service_id
        assert request.client == TEST_CLIENT_KEY
        assert request.query == "What are my rights?"
        assert request.context["location"] == "CA"
        assert request.consent["data_processing"] is True

    def test_create_service_response_helper(self):
        request = ServiceRequest(
            service_id="svc-123",
            client=TEST_CLIENT_KEY,
            query="Question",
        )

        response = create_service_response(
            request=request,
            provider=TEST_PROVIDER_KEY,
            response="Here is the answer...",
            confidence=0.9,
        )

        assert response.request_id == request.request_id
        assert response.service_id == request.service_id
        assert response.provider == TEST_PROVIDER_KEY
        assert response.confidence == 0.9
