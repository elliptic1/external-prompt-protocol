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
    CaseNote,
    CaseRecord,
    CaseMemory,
    ProviderSession,
    ProviderMessage,
    create_service_listing,
    create_legal_consultation_listing,
    create_service_request,
    create_service_response,
    create_consultation_session,
    create_case_record,
    create_case_memory,
    create_provider_session,
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


class TestCaseNote:
    """Tests for CaseNote model."""

    def test_basic_note(self):
        note = CaseNote(
            content="Client mentioned overtime issues",
            note_type="memo",
            author="ai",
        )
        assert note.content == "Client mentioned overtime issues"
        assert note.note_type == "memo"
        assert note.author == "ai"
        assert note.note_id is not None

    def test_note_with_references(self):
        note = CaseNote(
            content="See related case",
            note_type="guidance",
            author="provider",
            references=["case-123", "doc-456"],
        )
        assert len(note.references) == 2


class TestCaseRecord:
    """Tests for CaseRecord model."""

    def test_create_case(self):
        case = create_case_record(
            client_id="client-anon-123",
            category="employment-law",
            title="Retaliation claim",
            client_public_key=TEST_CLIENT_KEY,
        )
        assert case.client_id == "client-anon-123"
        assert case.category == "employment-law"
        assert case.status == "active"
        assert case.priority == "normal"

    def test_add_note(self):
        case = create_case_record(
            client_id="c1",
            category="legal",
            title="Test",
        )
        note = case.add_note(
            content="Important finding",
            note_type="update",
        )
        assert len(case.notes) == 1
        assert case.notes[0].content == "Important finding"

    def test_add_fact(self):
        case = create_case_record(
            client_id="c1",
            category="legal",
            title="Test",
        )
        case.add_fact("Client was terminated on Jan 15")
        case.add_fact("Complaint filed on Jan 10")
        assert len(case.facts) == 2

    def test_ai_question_workflow(self):
        case = create_case_record(
            client_id="c1",
            category="legal",
            title="Test",
        )

        # AI asks a question
        case.add_ai_question("Should I recommend filing with DLSE?")
        assert len(case.ai_questions) == 1
        assert case.ai_questions[0]["answered"] is False

        # Provider answers
        case.answer_ai_question(0, "Yes, recommend DLSE first because...")
        assert case.ai_questions[0]["answered"] is True
        assert case.ai_questions[0]["answer"] == "Yes, recommend DLSE first because..."
        assert len(case.notes) == 1  # Answer also added as note

    def test_add_guidance(self):
        case = create_case_record(
            client_id="c1",
            category="legal",
            title="Test",
        )
        case.add_guidance("Strong case for retaliation")
        assert len(case.guidance) == 1
        assert len(case.notes) == 1  # Guidance also added as note

    def test_link_consultation(self):
        case = create_case_record(
            client_id="c1",
            category="legal",
            title="Test",
        )
        case.link_consultation("req-001")
        case.link_consultation("req-002")
        case.link_consultation("req-001")  # Duplicate
        assert len(case.consultations) == 2

    def test_get_context_for_consultation(self):
        case = create_case_record(
            client_id="c1",
            category="legal",
            title="Test",
        )
        case.add_fact("Fact 1")
        case.add_guidance("Do X")

        context = case.get_context_for_consultation()
        assert context["case_id"] == case.case_id
        assert context["category"] == "legal"
        assert "Fact 1" in context["facts"]
        assert "Do X" in context["guidance"]


class TestCaseMemory:
    """Tests for CaseMemory model."""

    def test_create_memory(self):
        memory = create_case_memory(provider=TEST_PROVIDER_KEY)
        assert memory.provider == TEST_PROVIDER_KEY
        assert len(memory.cases) == 0

    def test_add_and_find_case(self):
        memory = create_case_memory(provider=TEST_PROVIDER_KEY)

        case = create_case_record(
            client_id="c1",
            category="legal",
            title="Test",
            client_public_key=TEST_CLIENT_KEY,
        )
        memory.add_case(case)

        # Find by ID
        found = memory.get_case(case.case_id)
        assert found is not None
        assert found.case_id == case.case_id

        # Find by client ID
        by_client = memory.find_cases_by_client("c1")
        assert len(by_client) == 1

        # Find by public key
        by_pubkey = memory.find_cases_by_pubkey(TEST_CLIENT_KEY)
        assert len(by_pubkey) == 1

    def test_find_active_cases(self):
        memory = create_case_memory(provider=TEST_PROVIDER_KEY)

        case1 = create_case_record(client_id="c1", category="legal", title="Active")
        case2 = create_case_record(client_id="c2", category="legal", title="Closed")
        case2.status = "closed"

        memory.add_case(case1)
        memory.add_case(case2)

        active = memory.find_active_cases()
        assert len(active) == 1
        assert active[0].title == "Active"

    def test_find_cases_with_questions(self):
        memory = create_case_memory(provider=TEST_PROVIDER_KEY)

        case1 = create_case_record(client_id="c1", category="legal", title="Has Q")
        case1.add_ai_question("Question?")

        case2 = create_case_record(client_id="c2", category="legal", title="No Q")

        memory.add_case(case1)
        memory.add_case(case2)

        with_q = memory.find_cases_with_questions()
        assert len(with_q) == 1
        assert with_q[0].title == "Has Q"

    def test_get_context_for_request(self):
        memory = create_case_memory(provider=TEST_PROVIDER_KEY)

        case = create_case_record(
            client_id="c1",
            category="legal",
            title="Test",
            client_public_key=TEST_CLIENT_KEY,
        )
        case.add_guidance("Important guidance")
        memory.add_case(case)

        request = ServiceRequest(
            service_id="svc",
            client=TEST_CLIENT_KEY,
            query="Follow-up question",
        )

        context = memory.get_context_for_request(request)
        assert context is not None
        assert "Important guidance" in context["guidance"]

    def test_create_or_update_case(self):
        memory = create_case_memory(provider=TEST_PROVIDER_KEY)

        request = ServiceRequest(
            service_id="svc",
            client=TEST_CLIENT_KEY,
            query="Initial question",
            context={"category": "employment"},
        )
        response = ServiceResponse(
            request_id=request.request_id,
            service_id="svc",
            provider=TEST_PROVIDER_KEY,
            response="Response",
        )

        # Creates new case
        case = memory.create_or_update_case_from_request(request, response)
        assert len(memory.cases) == 1
        assert request.request_id in case.consultations

        # Updates existing case
        request2 = ServiceRequest(
            service_id="svc",
            client=TEST_CLIENT_KEY,
            query="Follow-up",
        )
        response2 = ServiceResponse(
            request_id=request2.request_id,
            service_id="svc",
            provider=TEST_PROVIDER_KEY,
            response="Follow-up response",
        )

        case2 = memory.create_or_update_case_from_request(request2, response2)
        assert len(memory.cases) == 1  # Still 1 case
        assert case2.case_id == case.case_id
        assert len(case2.consultations) == 2


class TestProviderSession:
    """Tests for ProviderSession model."""

    def test_create_session(self):
        session = create_provider_session(provider=TEST_PROVIDER_KEY)
        assert session.provider == TEST_PROVIDER_KEY
        assert session.is_active() is True
        assert len(session.messages) == 0

    def test_add_messages(self):
        session = create_provider_session(provider=TEST_PROVIDER_KEY)

        session.add_message(
            role="ai",
            content="I have a question about case X",
            case_refs=["case-123"],
        )
        session.add_message(
            role="provider",
            content="Here's my guidance",
            case_refs=["case-123"],
            action_taken="provided_guidance",
        )

        assert len(session.messages) == 2
        assert session.messages[0].role == "ai"
        assert session.messages[1].role == "provider"
        assert "case-123" in session.cases_discussed

    def test_record_decision(self):
        session = create_provider_session(provider=TEST_PROVIDER_KEY)

        session.record_decision(
            case_id="case-456",
            decision="Recommend filing with DLSE",
            rationale="Strong temporal evidence",
        )

        assert len(session.decisions_made) == 1
        assert session.decisions_made[0]["decision"] == "Recommend filing with DLSE"
        assert "case-456" in session.cases_discussed

    def test_end_session(self):
        session = create_provider_session(provider=TEST_PROVIDER_KEY)
        assert session.is_active() is True

        session.end_session()
        assert session.is_active() is False
        assert session.ended_at is not None
