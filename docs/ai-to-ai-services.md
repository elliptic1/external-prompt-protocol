# AI-to-AI Services

EPP enables **AI-to-AI paid consultations** where professional AIs (lawyers, doctors, accountants) can offer services that client AIs consume on behalf of their users.

## The Problem

A person wants legal advice but:
- Doesn't want to leave the house
- Doesn't want to talk to a human
- Just wants to talk to their own AI

Meanwhile, a lawyer:
- Has specialized knowledge
- Could monetize that knowledge
- Doesn't want to personally handle every query

## The Solution

1. **Lawyer's AI** publishes a service listing with pricing
2. **Client's AI** discovers the service and pays the fee
3. **Client's AI** sends the user's question to the Lawyer's AI
4. **Lawyer's AI** responds with professional advice
5. **Client's AI** presents the response to the user

The lawyer never has to do extra work — their AI handles it.
The user never has to leave home — they just talk to their own AI.

## Architecture

```
┌─────────────────┐         ┌─────────────────┐
│     User        │         │     Lawyer      │
│   (Person)      │         │   (No work!)    │
└────────┬────────┘         └─────────────────┘
         │                           ↑
         │ "I need legal advice"     │ Setup once (pricing, scope)
         ↓                           │
┌─────────────────┐         ┌────────┴────────┐
│   Client's AI   │ ◄─────► │   Lawyer's AI   │
│                 │   EPP   │                 │
│  - Finds service│ + $$$   │  - Processes    │
│  - Pays fee     │         │  - Responds     │
│  - Sends query  │         │  - Automated    │
│  - Presents     │         │                 │
└─────────────────┘         └─────────────────┘
```

## Core Components

### ServiceListing

What a professional AI publishes to advertise their services:

```python
from epp.services import create_legal_consultation_listing

listing = create_legal_consultation_listing(
    provider=lawyer_ai_public_key,
    title="California Employment Law Consultation",
    description="Employment law advice for CA workers and employers",
    jurisdictions=["US-CA"],
    specialties=["employment-law", "discrimination"],
    payment_address="0x742d35Cc6634C0532925a3b844Bc9e7595f8abcd",
    inbox_url="https://inbox.lawyer-ai.example.com/epp/v1/submit",
    basic_price="5.00",     # $5 per question
    priority_price="25.00", # $25 for detailed analysis
    expert_price="100.00",  # $100 for multi-turn session
)
```

### Service Tiers

Services can have multiple pricing tiers:

| Tier | Price | Billing | Features |
|------|-------|---------|----------|
| basic | $5 | per-query | Quick answer, 15min response time |
| priority | $25 | per-query | Detailed analysis, 5min response, follow-up included |
| expert | $100 | per-session | Up to 10 exchanges, document review, written summary |

Billing models:
- `per-query` — Fixed fee per question
- `per-session` — Fixed fee for multi-turn consultation
- `per-minute` — Metered by conversation time
- `per-token` — Metered by AI usage
- `subscription` — Pre-paid access
- `escrow` — Funds held until service complete

### ServiceRequest

How a client AI requests a consultation:

```python
from epp.services import create_service_request

request = create_service_request(
    service_listing=listing,
    client=client_ai_public_key,
    query="My employer laid me off after I filed an overtime complaint...",
    tier="basic",
    context={
        "location": "California",
        "employment_status": "terminated",
    },
    payment_proof=payment_proof,  # Proof of USDC payment
)
```

### ServiceResponse

How the professional AI responds:

```python
from epp.services import create_service_response

response = create_service_response(
    request=request,
    provider=lawyer_ai_public_key,
    response="Based on your description, you may have grounds for...",
    confidence=0.85,
    citations=[
        {"code": "Cal. Lab. Code § 98.6", "description": "Retaliation protection"},
    ],
    disclaimers=[
        "This is AI-assisted legal information, not legal advice.",
    ],
    follow_up_suggested=True,
    follow_up_questions=[
        "Do you have documentation of your complaint?",
    ],
)
```

### ConsultationSession

For multi-turn conversations (per-session billing):

```python
from epp.services import create_consultation_session

session = create_consultation_session(
    service_listing=listing,
    tier_name="expert",
    client=client_ai_public_key,
    payment_proof=payment_proof,
    session_duration_hours=24,
)

# Client can now have up to 10 exchanges within 24 hours
print(f"Session ID: {session.session_id}")
print(f"Turns remaining: {session.max_turns - session.turns_used}")
```

## Payment Flow

EPP uses the [x402 pattern](https://x402.org) for payments:

1. **Client AI** reads service listing → sees pricing
2. **Client AI** creates payment request from listing
3. **Client AI** makes on-chain payment (USDC on Base, etc.)
4. **Client AI** includes `PaymentProof` in service request
5. **Lawyer AI** verifies payment before processing
6. **Lawyer AI** responds with advice

```python
# Get payment details from listing
payment_request = listing.create_payment_request(
    tier_name="basic",
    memo=f"Legal consultation: {listing.service_id}",
)

# Make payment (this happens on-chain)
# payment_proof = make_payment(payment_request)

# Include proof in request
request = ServiceRequest(
    service_id=listing.service_id,
    client=client_key,
    query="My legal question...",
    payment_proof=payment_proof,
)
```

## EPP Envelope Integration

Service requests and responses are wrapped in EPP envelopes:

```python
from epp.models import Envelope, Payload
from epp.services import service_request_to_payload

# Convert request to EPP payload
payload = Payload(
    prompt=request.query,
    context=service_request_to_payload(request),
    payload_type="service-request",
)

# Create and sign envelope
envelope = Envelope(
    version="1",
    envelope_id=str(uuid4()),
    sender=client_public_key,
    recipient=lawyer_public_key,
    scope="legal-consultation",
    payload=payload,
    # ... other fields
)

signed_envelope = sign_envelope(envelope, client_private_key)
```

The `conversation_id` and `in_reply_to` fields enable multi-turn conversations:

```python
# Response envelope references the request
response_envelope = Envelope(
    # ...
    conversation_id=request_envelope.conversation_id,
    in_reply_to=request_envelope.envelope_id,
    # ...
)
```

## Jurisdiction & Compliance

For regulated professions, `JurisdictionInfo` tracks:

```python
jurisdiction = JurisdictionInfo(
    jurisdictions=["US-CA", "US-NY"],
    license_type="bar-license",
    license_id="CA-123456",  # Can be hashed for privacy
    license_verification_url="https://members.calbar.ca.gov/search",
    disclaimers=[
        "This is AI-assisted legal information, not legal advice.",
        "For formal representation, consult a licensed attorney.",
    ],
)
```

## Service Discovery

Services can be discovered through:

1. **Direct URL** — Client AI knows the service's inbox URL
2. **Registry** — Centralized or federated service marketplace
3. **EPP Broadcast** — Service publishes listing via EPP envelope
4. **DNS/ENS** — Service URL in domain records

A service registry might look like:

```json
{
  "services": [
    {
      "service_id": "...",
      "category": "legal",
      "subcategories": ["employment-law"],
      "jurisdictions": ["US-CA"],
      "inbox_url": "https://...",
      "min_price": "5.00",
      "provider_reputation": 4.8
    }
  ]
}
```

## Example Categories

| Category | Use Cases |
|----------|-----------|
| `legal` | Contract review, employment advice, legal research |
| `medical` | Symptom analysis, medication info, health guidance |
| `financial` | Investment analysis, tax questions, financial planning |
| `tax` | Tax preparation, deduction advice, compliance |
| `technical` | Code review, architecture advice, debugging |
| `translation` | Document translation, localization |
| `research` | Academic research, market analysis |
| `creative` | Writing assistance, design feedback |

## Security Considerations

1. **Trust Registry** — Client AI should verify lawyer AI's public key
2. **Payment Verification** — Lawyer AI should verify on-chain payment
3. **Data Minimization** — Only share necessary context
4. **Confidentiality** — Encryption at rest and in transit
5. **Audit Trail** — Both sides retain signed envelopes

## Running the Example

```bash
cd external-prompt-protocol
python examples/lawyer_consultation.py
```

This demonstrates the full flow:
1. Lawyer AI publishes a service listing
2. Client AI discovers service and pays
3. User asks a question (to their own AI)
4. Client AI sends request to Lawyer AI
5. Lawyer AI responds with legal information
6. Client AI presents response to user

## Future Extensions

- **Reputation System** — On-chain reputation based on outcomes
- **Escrow** — Hold funds until user confirms satisfaction
- **Arbitration** — Dispute resolution for service quality
- **Subscriptions** — Recurring access to professional AIs
- **Referrals** — Commission for service recommendations
