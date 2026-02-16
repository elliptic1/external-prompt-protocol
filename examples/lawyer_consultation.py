#!/usr/bin/env python3
"""
Lawyer Consultation Example

Demonstrates the full flow of AI-to-AI paid consultation:

1. Lawyer's AI publishes a service listing
2. Client's AI discovers the service and pays for a consultation
3. Client's AI sends a legal question (user just talks to their own AI)
4. Lawyer's AI responds with advice
5. Client's AI translates the response for their user

The lawyer never has to do extra work - their AI handles it.
The user never has to leave home or talk to a human.
"""

import json
import base64
import os
from datetime import datetime, timezone, timedelta
from uuid import uuid4

# EPP core imports
from epp.crypto.keys import KeyPair, PublicKey
from epp.crypto.signing import sign_envelope, verify_envelope_signature
from epp.models import Envelope, Payload
from epp.payment import PaymentProof, create_payment_request

# Services layer (example implementation, not part of EPP core)
from services.services import (
    ServiceListing,
    ServiceRequest,
    ServiceResponse,
    ConsultationSession,
    create_legal_consultation_listing,
    create_service_request,
    create_service_response,
    create_consultation_session,
    service_request_to_payload,
    service_response_to_payload,
)


def main():
    print("=" * 70)
    print("EPP Lawyer Consultation Example")
    print("=" * 70)
    print()

    # ==========================================================================
    # SETUP: Generate keys for all parties
    # ==========================================================================
    print("Step 0: Setting up identities...")
    print("-" * 40)

    # The lawyer has their own AI with its own EPP identity
    lawyer_keypair = KeyPair.generate()
    lawyer_public = lawyer_keypair.public_key_hex()
    print(f"Lawyer's AI public key: {lawyer_public[:16]}...")

    # The client (person wanting legal advice) has their own AI
    client_keypair = KeyPair.generate()
    client_public = client_keypair.public_key_hex()
    print(f"Client's AI public key: {client_public[:16]}...")

    print()

    # ==========================================================================
    # STEP 1: Lawyer's AI publishes a service listing
    # ==========================================================================
    print("Step 1: Lawyer's AI publishes service listing")
    print("-" * 40)

    # The lawyer (or their setup assistant) configures this once.
    # After that, the lawyer's AI handles everything automatically.
    service_listing = create_legal_consultation_listing(
        provider=lawyer_public,
        title="California Employment Law Consultation",
        description="""
        AI-powered employment law consultation for California workers and employers.
        Covers workplace rights, discrimination, wrongful termination, wage disputes,
        and employment contracts. Powered by a licensed California attorney's 
        knowledge base and supervised by legal professionals.
        """.strip(),
        jurisdictions=["US-CA"],
        specialties=["employment-law", "workplace-rights", "discrimination"],
        payment_address="0x742d35Cc6634C0532925a3b844Bc9e7595f8abcd",
        inbox_url="https://inbox.lawyer-ai.example.com/epp/v1/submit",
        basic_price="5.00",       # $5 for a quick question
        priority_price="25.00",   # $25 for detailed analysis
        expert_price="100.00",    # $100 for multi-turn session
    )

    print(f"Service ID: {service_listing.service_id}")
    print(f"Category: {service_listing.category}")
    print(f"Title: {service_listing.title}")
    print(f"Tiers available:")
    for tier in service_listing.tiers:
        print(f"  - {tier.name}: ${tier.price} USDC ({tier.billing})")
    print()

    # ==========================================================================
    # STEP 2: Client's AI discovers the service and prepares payment
    # ==========================================================================
    print("Step 2: Client's AI finds service and prepares payment")
    print("-" * 40)

    # In practice, service discovery would use a registry/marketplace.
    # Here we simulate the client's AI finding the lawyer's service.

    # Client's AI creates a payment request based on the listing
    payment_request = service_listing.create_payment_request(
        tier_name="basic",
        memo=f"Legal consultation: {service_listing.service_id}",
    )

    print(f"Payment required: ${payment_request.amount} {payment_request.currency}")
    print(f"Pay to: {payment_request.recipient}")
    print(f"Chain: {payment_request.chain}")
    print()

    # Simulate the client's AI making the payment
    # (In reality, this would be an on-chain transaction)
    payment_proof = PaymentProof(
        tx_hash="0x" + "a" * 64,  # Valid EVM tx hash (0x + 64 hex chars)
        chain="base",
        amount="5.00",
        currency="USDC",
        payer="0x" + "1" * 40,  # Valid EVM address
        recipient=payment_request.recipient,
        block=12345678,
        confirmations=3,
    )

    print(f"Payment made!")
    print(f"TX Hash: {payment_proof.tx_hash[:20]}...")
    print(f"Block: {payment_proof.block}")
    print()

    # ==========================================================================
    # STEP 3: User talks to their own AI (no direct interaction with lawyer)
    # ==========================================================================
    print("Step 3: User asks their AI a legal question")
    print("-" * 40)

    # The user just talks naturally to their own AI:
    user_question = """
    My employer just laid me off after I filed a complaint about unpaid overtime.
    They said it was due to 'restructuring' but I was the only one let go, and 
    they hired someone new for my position two weeks later. I'm in California.
    Do I have any legal options?
    """

    print("User's question (to their own AI):")
    print(user_question.strip())
    print()

    # ==========================================================================
    # STEP 4: Client's AI creates service request and sends to lawyer's AI
    # ==========================================================================
    print("Step 4: Client's AI sends request to Lawyer's AI")
    print("-" * 40)

    # Client's AI packages the question with payment proof
    service_request = create_service_request(
        service_listing=service_listing,
        client=client_public,
        query=user_question.strip(),
        tier="basic",
        context={
            "user_location": "California",
            "employment_status": "terminated",
            "time_since_termination": "2 weeks",
        },
        payment_proof=payment_proof,
    )

    print(f"Request ID: {service_request.request_id}")
    print(f"Service: {service_request.service_id}")
    print(f"Tier: {service_request.tier}")
    print(f"Payment included: Yes")
    print()

    # Create the EPP envelope for the request
    conversation_id = str(uuid4())
    request_envelope = create_envelope(
        sender_keypair=client_keypair,
        sender_public=client_public,
        recipient_public=lawyer_public,
        scope=service_listing.scope,
        prompt=service_request.query,
        context=service_request_to_payload(service_request),
        payload_type="service-request",
        conversation_id=conversation_id,
    )

    print(f"EPP Envelope created and signed")
    print(f"Envelope ID: {request_envelope.envelope_id}")
    print()

    # ==========================================================================
    # STEP 5: Lawyer's AI processes and responds (no human involvement)
    # ==========================================================================
    print("Step 5: Lawyer's AI processes and responds")
    print("-" * 40)

    # Lawyer's AI verifies the envelope
    is_valid = verify_envelope(request_envelope, client_public)
    print(f"Signature valid: {is_valid}")

    # Lawyer's AI generates a response (this would be their specialized legal AI)
    legal_response = """
    Based on what you've described, you may have grounds for a **wrongful termination** 
    and/or **retaliation** claim under California law.

    **Key factors that support your case:**

    1. **Timing**: You were terminated shortly after filing a complaint about unpaid 
       overtime. California Labor Code Section 98.6 protects employees from retaliation 
       for making wage complaints.

    2. **Pretext**: The "restructuring" explanation appears pretextual since they hired 
       a replacement within two weeks. Courts look at whether the stated reason is 
       believable.

    3. **Overtime violation**: If you were owed unpaid overtime, that's a separate 
       violation under California Labor Code Sections 510-511.

    **Recommended next steps:**

    1. **Document everything**: Save any emails, messages, or documents about your 
       termination and the overtime complaint.

    2. **File a complaint**: You can file with the California Labor Commissioner 
       (DLSE) for both the unpaid overtime and retaliation.

    3. **Statute of limitations**: For retaliation claims, you typically have 1 year. 
       For unpaid wages, you have 3-4 years depending on the circumstances.

    4. **Consult an attorney**: Given the complexity, consider a free consultation 
       with an employment attorney. Many work on contingency for these cases.

    **Important disclaimer**: This is general legal information based on the facts 
    you've provided. Your specific situation may have additional factors. For formal 
    legal advice and representation, please consult with a licensed California 
    employment attorney.
    """

    service_response = create_service_response(
        request=service_request,
        provider=lawyer_public,
        response=legal_response.strip(),
        confidence=0.85,
        citations=[
            {"code": "Cal. Lab. Code § 98.6", "description": "Retaliation protection"},
            {"code": "Cal. Lab. Code § 510-511", "description": "Overtime requirements"},
        ],
        disclaimers=[
            "This is AI-assisted legal information, not legal advice.",
            "Consult a licensed attorney for your specific situation.",
        ],
        follow_up_suggested=True,
        follow_up_questions=[
            "Do you have documentation of your overtime complaint?",
            "What was your job title and how long were you employed?",
            "Did you receive a written termination notice?",
        ],
    )

    print(f"Response ID: {service_response.response_id}")
    print(f"Confidence: {service_response.confidence}")
    print(f"Follow-up suggested: {service_response.follow_up_suggested}")
    print()

    # Create response envelope
    response_envelope = create_envelope(
        sender_keypair=lawyer_keypair,
        sender_public=lawyer_public,
        recipient_public=client_public,
        scope=service_listing.scope,
        prompt=service_response.response,
        context=service_response_to_payload(service_response),
        payload_type="service-response",
        conversation_id=conversation_id,
        in_reply_to=request_envelope.envelope_id,
        expires_hours=24,
    )

    print(f"Response envelope created")
    print(f"Envelope ID: {response_envelope.envelope_id}")
    print()

    # ==========================================================================
    # STEP 6: Client's AI receives and presents response to user
    # ==========================================================================
    print("Step 6: Client's AI presents response to user")
    print("-" * 40)

    # Client's AI verifies the response envelope
    is_valid = verify_envelope(response_envelope, lawyer_public)
    print(f"Response signature valid: {is_valid}")
    print()

    # Client's AI can now present this to the user in a friendly way
    print("=" * 70)
    print("RESPONSE FROM LEGAL CONSULTATION")
    print("=" * 70)
    print()
    print(service_response.response)
    print()
    print("-" * 40)
    print("Citations:")
    for cite in service_response.citations:
        print(f"  • {cite['code']}: {cite['description']}")
    print()
    print("Suggested follow-up questions:")
    for q in service_response.follow_up_questions:
        print(f"  • {q}")
    print()
    print("-" * 40)
    print(f"Cost: ${payment_proof.amount} {payment_proof.currency}")
    print(f"Service: {service_listing.title}")
    print("=" * 70)


def create_envelope(
    sender_keypair: KeyPair,
    sender_public: str,
    recipient_public: str,
    scope: str,
    prompt: str,
    context: dict,
    payload_type: str,
    conversation_id: str = None,
    in_reply_to: str = None,
    expires_hours: float = 0.25,  # 15 minutes default
) -> Envelope:
    """Create a signed EPP envelope."""
    now = datetime.now(timezone.utc)
    nonce = base64.b64encode(os.urandom(16)).decode()
    envelope_id = str(uuid4())

    payload_dict = {
        "prompt": prompt,
        "context": context,
        "payload_type": payload_type,
    }

    # Sign the envelope
    signature = sign_envelope(
        key_pair=sender_keypair,
        version="1",
        envelope_id=envelope_id,
        sender=sender_public,
        recipient=recipient_public,
        timestamp=now.isoformat().replace("+00:00", "Z"),
        expires_at=(now + timedelta(hours=expires_hours)).isoformat().replace("+00:00", "Z"),
        nonce=nonce,
        scope=scope,
        payload=payload_dict,
        conversation_id=conversation_id,
        in_reply_to=in_reply_to,
    )

    envelope = Envelope(
        version="1",
        envelope_id=envelope_id,
        sender=sender_public,
        recipient=recipient_public,
        timestamp=now.isoformat().replace("+00:00", "Z"),
        expires_at=(now + timedelta(hours=expires_hours)).isoformat().replace("+00:00", "Z"),
        nonce=nonce,
        scope=scope,
        payload=Payload(**payload_dict),
        signature=signature,
        conversation_id=conversation_id,
        in_reply_to=in_reply_to,
    )

    return envelope


def verify_envelope(envelope: Envelope, sender_public: str) -> bool:
    """Verify an EPP envelope signature."""
    public_key = PublicKey.from_hex(sender_public)

    payload_dict = {
        "prompt": envelope.payload.prompt,
        "context": envelope.payload.context,
        "payload_type": envelope.payload.payload_type,
    }
    if envelope.payload.metadata:
        payload_dict["metadata"] = envelope.payload.metadata

    return verify_envelope_signature(
        public_key=public_key,
        signature_b64=envelope.signature,
        version=envelope.version,
        envelope_id=envelope.envelope_id,
        sender=envelope.sender,
        recipient=envelope.recipient,
        timestamp=envelope.timestamp,
        expires_at=envelope.expires_at,
        nonce=envelope.nonce,
        scope=envelope.scope,
        payload=payload_dict,
        conversation_id=envelope.conversation_id,
        in_reply_to=envelope.in_reply_to,
        delegation=envelope.delegation.model_dump() if envelope.delegation else None,
    )


if __name__ == "__main__":
    main()
