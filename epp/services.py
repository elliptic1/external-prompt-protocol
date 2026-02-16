"""
AI-to-AI Services for EPP.

Enables professional AIs (lawyers, doctors, accountants) to offer paid consultation
services that client AIs can discover and consume on behalf of their users.

Use Case:
- Person wants legal advice but doesn't want to leave home or talk to a human
- They talk to their own AI, which pays a fee to use the lawyer's AI
- The two AIs communicate data between each other for a fee
- The lawyer doesn't have to do any extra work
- The person only has to talk to their own AI

This module provides:
- ServiceListing: How a professional AI advertises its services
- ServiceRequest: How a client AI requests a consultation
- ServiceResponse: How a professional AI responds
- ConsultationSession: Multi-turn consultation management
"""

import re
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from epp.payment import PaymentRequest, PaymentProof, create_payment_request


# Service categories
ServiceCategory = Literal[
    "legal",
    "medical",
    "financial",
    "tax",
    "insurance",
    "real-estate",
    "technical",
    "translation",
    "research",
    "creative",
    "custom",
]

SERVICE_CATEGORIES = (
    "legal",
    "medical",
    "financial",
    "tax",
    "insurance",
    "real-estate",
    "technical",
    "translation",
    "research",
    "creative",
    "custom",
)


# Billing models
BillingModel = Literal[
    "per-query",      # Fixed fee per question/query
    "per-session",    # Fixed fee for a consultation session (multi-turn)
    "per-minute",     # Metered by time (tracked by conversation timestamps)
    "per-token",      # Metered by tokens used (input + output)
    "subscription",   # Pre-paid access
    "escrow",         # Funds held until service complete
]


class ServiceTier(BaseModel):
    """A pricing tier within a service listing."""

    name: str = Field(
        ...,
        description="Tier name (e.g., 'basic', 'priority', 'expert')",
    )
    description: Optional[str] = Field(
        default=None,
        description="What this tier provides",
    )
    price: str = Field(
        ...,
        description="Price as decimal string",
    )
    currency: str = Field(
        default="USDC",
        description="Currency code",
    )
    billing: BillingModel = Field(
        default="per-query",
        description="Billing model",
    )
    response_time: Optional[str] = Field(
        default=None,
        description="Expected response time (e.g., '5m', '1h', '24h')",
    )
    max_turns: Optional[int] = Field(
        default=None,
        description="Max conversation turns (for per-session billing)",
    )
    features: List[str] = Field(
        default_factory=list,
        description="Features included in this tier",
    )

    @field_validator("price")
    @classmethod
    def validate_price(cls, v: str) -> str:
        """Validate price is a valid decimal string."""
        try:
            amount = Decimal(v)
            if amount < 0:
                raise ValueError("Price cannot be negative")
        except Exception as e:
            raise ValueError(f"Invalid price: {v} - {e}")
        return v

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """Validate currency code."""
        return v.upper()


class JurisdictionInfo(BaseModel):
    """Jurisdiction and licensing information for regulated services."""

    jurisdictions: List[str] = Field(
        default_factory=list,
        description="Jurisdictions where service is valid (e.g., 'US-CA', 'EU', 'UK')",
    )
    license_type: Optional[str] = Field(
        default=None,
        description="Type of professional license (e.g., 'bar-license', 'medical-license')",
    )
    license_id: Optional[str] = Field(
        default=None,
        description="License identifier (may be hashed for privacy)",
    )
    license_verification_url: Optional[str] = Field(
        default=None,
        description="URL to verify license (state bar lookup, etc.)",
    )
    disclaimers: List[str] = Field(
        default_factory=list,
        description="Required legal disclaimers",
    )


class ServiceListing(BaseModel):
    """
    A service offering from a professional AI.

    This is what a lawyer's AI (or doctor's, accountant's, etc.) publishes
    to advertise their paid consultation services.
    """

    service_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique service identifier",
    )
    provider: str = Field(
        ...,
        description="Provider's EPP public key (hex)",
    )
    provider_name: Optional[str] = Field(
        default=None,
        description="Human-readable provider name",
    )
    category: str = Field(
        ...,
        description="Service category",
    )
    subcategories: List[str] = Field(
        default_factory=list,
        description="Specific areas (e.g., ['contract-law', 'employment-law'])",
    )
    title: str = Field(
        ...,
        description="Service title (e.g., 'California Employment Law Consultation')",
    )
    description: str = Field(
        ...,
        description="Detailed service description",
    )
    tiers: List[ServiceTier] = Field(
        default_factory=list,
        description="Available pricing tiers",
    )
    payment_address: str = Field(
        ...,
        description="Wallet address for payments",
    )
    payment_chain: str = Field(
        default="base",
        description="Preferred blockchain for payments",
    )
    inbox_url: str = Field(
        ...,
        description="EPP inbox URL to submit requests",
    )
    scope: str = Field(
        ...,
        description="EPP scope for this service",
    )
    jurisdiction: Optional[JurisdictionInfo] = Field(
        default=None,
        description="Jurisdiction/licensing info",
    )
    capabilities_required: List[str] = Field(
        default_factory=list,
        description="EPP capabilities required from client",
    )
    data_retention: Optional[str] = Field(
        default=None,
        description="Data retention policy",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        description="Listing creation time",
    )
    expires_at: Optional[str] = Field(
        default=None,
        description="Listing expiration (optional)",
    )
    active: bool = Field(
        default=True,
        description="Whether service is currently accepting requests",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional metadata",
    )

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        """Validate provider is a hex public key."""
        if not re.match(r"^[0-9a-fA-F]{64}$", v):
            raise ValueError(f"Provider must be 64 hex characters: {v}")
        return v.lower()

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        """Validate category."""
        v = v.lower()
        if not re.match(r"^[a-z0-9\-]+$", v):
            raise ValueError(f"Invalid category: {v}")
        return v

    def get_tier(self, name: str) -> Optional[ServiceTier]:
        """Get a tier by name."""
        for tier in self.tiers:
            if tier.name == name:
                return tier
        return None

    def get_default_tier(self) -> Optional[ServiceTier]:
        """Get the first/default tier."""
        return self.tiers[0] if self.tiers else None

    def create_payment_request(
        self,
        tier_name: Optional[str] = None,
        memo: Optional[str] = None,
        expires_in_minutes: int = 15,
    ) -> PaymentRequest:
        """Create a payment request for this service."""
        tier = self.get_tier(tier_name) if tier_name else self.get_default_tier()
        if not tier:
            raise ValueError(f"Tier not found: {tier_name}")

        return create_payment_request(
            amount=tier.price,
            currency=tier.currency,
            recipient=self.payment_address,
            chain=self.payment_chain,
            memo=memo or f"Service: {self.service_id}",
            expires_in_minutes=expires_in_minutes,
        )


class ServiceRequest(BaseModel):
    """
    A request from a client AI to a professional AI.

    The client AI sends this on behalf of its user. It includes:
    - The query/question
    - Payment proof or prepayment
    - Client context (what the client AI knows is relevant)
    - Consent and authorization info
    """

    request_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique request identifier",
    )
    service_id: str = Field(
        ...,
        description="Service being requested",
    )
    tier: str = Field(
        default="basic",
        description="Service tier requested",
    )
    client: str = Field(
        ...,
        description="Client AI's EPP public key",
    )
    principal: Optional[str] = Field(
        default=None,
        description="End user's identity (if different from client AI owner)",
    )
    query: str = Field(
        ...,
        description="The actual question/request",
    )
    context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Relevant context the client AI provides",
    )
    attachments: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Attached documents/data (references or inline)",
    )
    preferences: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Client preferences (response format, detail level, etc.)",
    )
    payment_proof: Optional[PaymentProof] = Field(
        default=None,
        description="Proof of payment (for prepaid requests)",
    )
    payment_intent: Optional[str] = Field(
        default=None,
        description="Payment intent ID (for pay-after scenarios)",
    )
    consent: Dict[str, Any] = Field(
        default_factory=dict,
        description="Consent declarations from the user",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        description="Request timestamp",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID for multi-turn consultations",
    )
    in_reply_to: Optional[str] = Field(
        default=None,
        description="Previous response ID (for follow-ups)",
    )

    @field_validator("client")
    @classmethod
    def validate_client(cls, v: str) -> str:
        """Validate client is a hex public key."""
        if not re.match(r"^[0-9a-fA-F]{64}$", v):
            raise ValueError(f"Client must be 64 hex characters: {v}")
        return v.lower()

    @field_validator("principal")
    @classmethod
    def validate_principal(cls, v: Optional[str]) -> Optional[str]:
        """Validate principal if present."""
        if v is not None and not re.match(r"^[0-9a-fA-F]{64}$", v):
            raise ValueError(f"Principal must be 64 hex characters: {v}")
        return v.lower() if v else None


class ServiceResponse(BaseModel):
    """
    A response from a professional AI to a client AI.

    Contains the actual advice/answer plus metadata about the consultation.
    """

    response_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique response identifier",
    )
    request_id: str = Field(
        ...,
        description="Request this responds to",
    )
    service_id: str = Field(
        ...,
        description="Service that provided this response",
    )
    provider: str = Field(
        ...,
        description="Provider's EPP public key",
    )
    response: str = Field(
        ...,
        description="The actual response/advice",
    )
    structured_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Structured response data (for programmatic use)",
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence level (0-1)",
    )
    citations: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Citations/references",
    )
    disclaimers: List[str] = Field(
        default_factory=list,
        description="Legal/professional disclaimers",
    )
    follow_up_suggested: bool = Field(
        default=False,
        description="Whether follow-up is recommended",
    )
    follow_up_questions: List[str] = Field(
        default_factory=list,
        description="Suggested follow-up questions",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID for multi-turn consultations",
    )
    turns_remaining: Optional[int] = Field(
        default=None,
        description="Turns remaining in session (for per-session billing)",
    )
    billing: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Billing details for this response",
    )
    payment_required: Optional[PaymentRequest] = Field(
        default=None,
        description="Payment required for follow-up",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        description="Response timestamp",
    )
    processing_time_ms: Optional[int] = Field(
        default=None,
        description="Processing time in milliseconds",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional metadata",
    )

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        """Validate provider is a hex public key."""
        if not re.match(r"^[0-9a-fA-F]{64}$", v):
            raise ValueError(f"Provider must be 64 hex characters: {v}")
        return v.lower()


class ConsultationSession(BaseModel):
    """
    Manages a multi-turn consultation session between AIs.

    Used when billing is per-session and multiple exchanges are allowed.
    """

    session_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique session identifier",
    )
    service_id: str = Field(
        ...,
        description="Service this session is for",
    )
    tier: str = Field(
        ...,
        description="Service tier",
    )
    client: str = Field(
        ...,
        description="Client AI's public key",
    )
    provider: str = Field(
        ...,
        description="Provider AI's public key",
    )
    payment_proof: PaymentProof = Field(
        ...,
        description="Initial payment proof",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        description="Session creation time",
    )
    expires_at: str = Field(
        ...,
        description="Session expiration time",
    )
    max_turns: int = Field(
        ...,
        description="Maximum conversation turns",
    )
    turns_used: int = Field(
        default=0,
        description="Turns used so far",
    )
    status: Literal["active", "completed", "expired", "cancelled"] = Field(
        default="active",
        description="Session status",
    )
    exchanges: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Request/response pairs in this session",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Session metadata",
    )

    def is_expired(self) -> bool:
        """Check if session has expired."""
        expires_dt = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) > expires_dt

    def has_turns_remaining(self) -> bool:
        """Check if session has turns remaining."""
        return self.turns_used < self.max_turns

    def is_active(self) -> bool:
        """Check if session is active and usable."""
        return (
            self.status == "active"
            and not self.is_expired()
            and self.has_turns_remaining()
        )

    def record_exchange(self, request_id: str, response_id: str) -> None:
        """Record an exchange in the session."""
        self.exchanges.append({
            "request_id": request_id,
            "response_id": response_id,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        })
        self.turns_used += 1

        if self.turns_used >= self.max_turns:
            self.status = "completed"


# Helper functions

def create_service_listing(
    provider: str,
    category: str,
    title: str,
    description: str,
    price: str,
    payment_address: str,
    inbox_url: str,
    scope: str,
    **kwargs,
) -> ServiceListing:
    """
    Create a service listing with sensible defaults.

    Args:
        provider: Provider's EPP public key
        category: Service category (legal, medical, etc.)
        title: Service title
        description: Service description
        price: Default price
        payment_address: Wallet address
        inbox_url: EPP inbox URL
        scope: EPP scope for the service
        **kwargs: Additional fields

    Returns:
        ServiceListing object
    """
    default_tier = ServiceTier(
        name="basic",
        price=price,
        billing="per-query",
    )

    return ServiceListing(
        provider=provider,
        category=category,
        title=title,
        description=description,
        tiers=[default_tier],
        payment_address=payment_address,
        inbox_url=inbox_url,
        scope=scope,
        **kwargs,
    )


def create_legal_consultation_listing(
    provider: str,
    title: str,
    description: str,
    jurisdictions: List[str],
    specialties: List[str],
    payment_address: str,
    inbox_url: str,
    basic_price: str = "5.00",
    priority_price: str = "25.00",
    expert_price: str = "100.00",
    **kwargs,
) -> ServiceListing:
    """
    Create a legal consultation service listing.

    This is a convenience function for lawyers setting up AI consultation services.

    Args:
        provider: Lawyer's AI public key
        title: Service title
        description: Service description
        jurisdictions: List of jurisdictions (e.g., ['US-CA', 'US-NY'])
        specialties: Legal specialties (e.g., ['employment', 'contract'])
        payment_address: Payment wallet
        inbox_url: EPP inbox
        basic_price: Basic tier price (default $5)
        priority_price: Priority tier price (default $25)
        expert_price: Expert tier price (default $100)

    Returns:
        ServiceListing for legal consultation
    """
    tiers = [
        ServiceTier(
            name="basic",
            description="General legal information and guidance",
            price=basic_price,
            currency="USDC",
            billing="per-query",
            response_time="15m",
            features=[
                "General legal information",
                "Guidance on legal concepts",
                "Standard response time",
            ],
        ),
        ServiceTier(
            name="priority",
            description="Detailed analysis with faster response",
            price=priority_price,
            currency="USDC",
            billing="per-query",
            response_time="5m",
            features=[
                "Detailed legal analysis",
                "Priority response time",
                "Document review (up to 5 pages)",
                "Follow-up question included",
            ],
        ),
        ServiceTier(
            name="expert",
            description="Comprehensive consultation session",
            price=expert_price,
            currency="USDC",
            billing="per-session",
            response_time="2m",
            max_turns=10,
            features=[
                "Comprehensive legal analysis",
                "Multi-turn consultation (up to 10 exchanges)",
                "Document review (up to 25 pages)",
                "Written summary provided",
                "Fastest response time",
            ],
        ),
    ]

    jurisdiction = JurisdictionInfo(
        jurisdictions=jurisdictions,
        disclaimers=[
            "This is AI-assisted legal information, not legal advice.",
            "For formal legal representation, consult a licensed attorney directly.",
            "Information provided is based on general legal principles and may not apply to your specific situation.",
        ],
    )

    return ServiceListing(
        provider=provider,
        category="legal",
        subcategories=specialties,
        title=title,
        description=description,
        tiers=tiers,
        payment_address=payment_address,
        payment_chain="base",
        inbox_url=inbox_url,
        scope="legal-consultation",
        jurisdiction=jurisdiction,
        capabilities_required=["data_access:documents:read"],
        data_retention="30 days, then deleted",
        **kwargs,
    )


def create_service_request(
    service_listing: ServiceListing,
    client: str,
    query: str,
    tier: str = "basic",
    context: Optional[Dict[str, Any]] = None,
    payment_proof: Optional[PaymentProof] = None,
    session_id: Optional[str] = None,
    **kwargs,
) -> ServiceRequest:
    """
    Create a service request for a listing.

    Args:
        service_listing: The service being requested
        client: Client AI's public key
        query: The question/request
        tier: Service tier
        context: Relevant context
        payment_proof: Proof of payment
        session_id: Session ID for multi-turn
        **kwargs: Additional fields

    Returns:
        ServiceRequest object
    """
    return ServiceRequest(
        service_id=service_listing.service_id,
        tier=tier,
        client=client,
        query=query,
        context=context,
        payment_proof=payment_proof,
        session_id=session_id,
        consent={
            "data_processing": True,
            "ai_assistance": True,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
        **kwargs,
    )


def create_service_response(
    request: ServiceRequest,
    provider: str,
    response: str,
    **kwargs,
) -> ServiceResponse:
    """
    Create a response to a service request.

    Args:
        request: The request being responded to
        provider: Provider's public key
        response: The response text
        **kwargs: Additional fields

    Returns:
        ServiceResponse object
    """
    return ServiceResponse(
        request_id=request.request_id,
        service_id=request.service_id,
        provider=provider,
        response=response,
        session_id=request.session_id,
        **kwargs,
    )


def create_consultation_session(
    service_listing: ServiceListing,
    tier_name: str,
    client: str,
    payment_proof: PaymentProof,
    session_duration_hours: int = 24,
) -> ConsultationSession:
    """
    Create a new consultation session.

    Args:
        service_listing: The service
        tier_name: Tier being used
        client: Client AI's public key
        payment_proof: Proof of session payment
        session_duration_hours: How long the session is valid

    Returns:
        ConsultationSession object
    """
    tier = service_listing.get_tier(tier_name)
    if not tier:
        raise ValueError(f"Tier not found: {tier_name}")

    if tier.billing != "per-session":
        raise ValueError(f"Tier {tier_name} is not per-session billing")

    max_turns = tier.max_turns or 5

    expires_at = (
        (datetime.now(timezone.utc) + timedelta(hours=session_duration_hours))
        .isoformat()
        .replace("+00:00", "Z")
    )

    return ConsultationSession(
        service_id=service_listing.service_id,
        tier=tier_name,
        client=client,
        provider=service_listing.provider,
        payment_proof=payment_proof,
        expires_at=expires_at,
        max_turns=max_turns,
    )


# Envelope integration

def service_request_to_payload(request: ServiceRequest) -> Dict[str, Any]:
    """
    Convert a ServiceRequest to an EPP payload.

    Returns dict suitable for Payload.context field.
    """
    return {
        "type": "service-request",
        "version": "1",
        "request": request.model_dump(exclude_none=True),
    }


def service_response_to_payload(response: ServiceResponse) -> Dict[str, Any]:
    """
    Convert a ServiceResponse to an EPP payload.

    Returns dict suitable for Payload.context field.
    """
    return {
        "type": "service-response",
        "version": "1",
        "response": response.model_dump(exclude_none=True),
    }


def service_listing_to_payload(listing: ServiceListing) -> Dict[str, Any]:
    """
    Convert a ServiceListing to an EPP payload.

    For publishing service listings.
    """
    return {
        "type": "service-listing",
        "version": "1",
        "listing": listing.model_dump(exclude_none=True),
    }


# =============================================================================
# Provider-Side Workflow
# =============================================================================
#
# The professional (lawyer, doctor, etc.) can talk to their AI concurrently:
# - Discuss current cases and provide guidance
# - Answer questions the AI has
# - Make decisions that update case memory
#
# This updated knowledge is then available when responding to client AIs.
#
# Flow:
#   Lawyer ←→ Lawyer's AI (internal conversations, case updates)
#                ↓
#          Case Memory (updated with decisions, guidance)
#                ↓
#   Client's AI → Lawyer's AI (consultation uses case memory)
# =============================================================================


class CaseNote(BaseModel):
    """A note or update on a case from the professional."""

    note_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique note identifier",
    )
    content: str = Field(
        ...,
        description="Note content",
    )
    note_type: Literal["guidance", "decision", "question", "answer", "update", "memo"] = Field(
        default="memo",
        description="Type of note",
    )
    author: Literal["provider", "ai"] = Field(
        default="provider",
        description="Who created this note",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        description="When the note was created",
    )
    references: List[str] = Field(
        default_factory=list,
        description="References to other notes, documents, or cases",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional metadata",
    )


class CaseRecord(BaseModel):
    """
    A case record in the provider's AI memory.

    Tracks all information about a specific case/client, including:
    - Client information (anonymized or pseudonymized)
    - Consultation history
    - Provider guidance and decisions
    - AI questions and provider answers
    """

    case_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique case identifier",
    )
    client_id: str = Field(
        ...,
        description="Client identifier (can be anonymized)",
    )
    client_public_key: Optional[str] = Field(
        default=None,
        description="Client AI's public key (for matching consultations)",
    )
    category: str = Field(
        ...,
        description="Case category (e.g., 'employment-law', 'contract-dispute')",
    )
    title: str = Field(
        ...,
        description="Case title/summary",
    )
    status: Literal["active", "pending", "resolved", "closed", "archived"] = Field(
        default="active",
        description="Case status",
    )
    priority: Literal["low", "normal", "high", "urgent"] = Field(
        default="normal",
        description="Case priority",
    )
    summary: Optional[str] = Field(
        default=None,
        description="AI-generated or provider-written case summary",
    )
    facts: List[str] = Field(
        default_factory=list,
        description="Key facts established for this case",
    )
    notes: List[CaseNote] = Field(
        default_factory=list,
        description="Notes and updates on the case",
    )
    consultations: List[str] = Field(
        default_factory=list,
        description="IDs of ServiceRequests for this case",
    )
    ai_questions: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Questions the AI has for the provider (with answers)",
    )
    guidance: List[str] = Field(
        default_factory=list,
        description="Specific guidance from the provider for this case",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        description="When the case was created",
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        description="Last update time",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional case metadata",
    )

    @field_validator("client_public_key")
    @classmethod
    def validate_client_public_key(cls, v: Optional[str]) -> Optional[str]:
        """Validate client public key if present."""
        if v is not None and not re.match(r"^[0-9a-fA-F]{64}$", v):
            raise ValueError(f"Client public key must be 64 hex characters: {v}")
        return v.lower() if v else None

    def add_note(
        self,
        content: str,
        note_type: str = "memo",
        author: str = "provider",
        references: List[str] = None,
    ) -> CaseNote:
        """Add a note to the case."""
        note = CaseNote(
            content=content,
            note_type=note_type,
            author=author,
            references=references or [],
        )
        self.notes.append(note)
        self.updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return note

    def add_ai_question(self, question: str) -> None:
        """Record a question the AI has for the provider."""
        self.ai_questions.append({
            "question": question,
            "asked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "answered": False,
            "answer": None,
        })
        self.updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def answer_ai_question(self, question_index: int, answer: str) -> None:
        """Provider answers an AI question."""
        if 0 <= question_index < len(self.ai_questions):
            self.ai_questions[question_index]["answered"] = True
            self.ai_questions[question_index]["answer"] = answer
            self.ai_questions[question_index]["answered_at"] = (
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            )
            # Also add as a guidance note
            self.add_note(
                content=f"Q: {self.ai_questions[question_index]['question']}\nA: {answer}",
                note_type="answer",
                author="provider",
            )

    def add_guidance(self, guidance: str) -> None:
        """Add provider guidance for this case."""
        self.guidance.append(guidance)
        self.add_note(content=guidance, note_type="guidance", author="provider")

    def add_fact(self, fact: str) -> None:
        """Add an established fact to the case."""
        self.facts.append(fact)
        self.updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def link_consultation(self, request_id: str) -> None:
        """Link a consultation to this case."""
        if request_id not in self.consultations:
            self.consultations.append(request_id)
            self.updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def get_context_for_consultation(self) -> Dict[str, Any]:
        """
        Get relevant context for responding to a consultation.

        Returns a dict with case info, facts, and guidance that the AI
        should consider when responding.
        """
        return {
            "case_id": self.case_id,
            "category": self.category,
            "status": self.status,
            "priority": self.priority,
            "summary": self.summary,
            "facts": self.facts,
            "guidance": self.guidance,
            "recent_notes": [
                note.model_dump() for note in self.notes[-5:]
            ],  # Last 5 notes
            "unanswered_questions": [
                q for q in self.ai_questions if not q.get("answered", False)
            ],
        }


class ProviderMessage(BaseModel):
    """A message in a provider-AI conversation."""

    message_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique message identifier",
    )
    role: Literal["provider", "ai"] = Field(
        ...,
        description="Who sent this message",
    )
    content: str = Field(
        ...,
        description="Message content",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        description="When the message was sent",
    )
    case_refs: List[str] = Field(
        default_factory=list,
        description="Case IDs referenced in this message",
    )
    action_taken: Optional[str] = Field(
        default=None,
        description="Action taken as a result of this message",
    )


class ProviderSession(BaseModel):
    """
    A conversation session between the professional and their AI.

    The provider can:
    - Review pending questions from their AI
    - Provide guidance on specific cases
    - Make decisions that update case memory
    - Ask their AI to summarize case status
    """

    session_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique session identifier",
    )
    provider: str = Field(
        ...,
        description="Provider's EPP public key",
    )
    started_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        description="Session start time",
    )
    ended_at: Optional[str] = Field(
        default=None,
        description="Session end time (null if active)",
    )
    messages: List[ProviderMessage] = Field(
        default_factory=list,
        description="Conversation messages",
    )
    cases_discussed: List[str] = Field(
        default_factory=list,
        description="Case IDs discussed in this session",
    )
    decisions_made: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Decisions made during this session",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Session metadata",
    )

    def add_message(
        self,
        role: str,
        content: str,
        case_refs: List[str] = None,
        action_taken: str = None,
    ) -> ProviderMessage:
        """Add a message to the session."""
        msg = ProviderMessage(
            role=role,
            content=content,
            case_refs=case_refs or [],
            action_taken=action_taken,
        )
        self.messages.append(msg)

        # Track which cases were discussed
        for case_id in (case_refs or []):
            if case_id not in self.cases_discussed:
                self.cases_discussed.append(case_id)

        return msg

    def record_decision(
        self,
        case_id: str,
        decision: str,
        rationale: Optional[str] = None,
    ) -> None:
        """Record a decision made during this session."""
        self.decisions_made.append({
            "case_id": case_id,
            "decision": decision,
            "rationale": rationale,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        })
        if case_id not in self.cases_discussed:
            self.cases_discussed.append(case_id)

    def end_session(self) -> None:
        """End the provider session."""
        self.ended_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def is_active(self) -> bool:
        """Check if session is still active."""
        return self.ended_at is None


class CaseMemory(BaseModel):
    """
    The provider AI's case memory.

    Manages all cases and provides methods for:
    - Finding cases by client or category
    - Updating cases with new information
    - Getting context for consultations
    """

    provider: str = Field(
        ...,
        description="Provider's EPP public key",
    )
    cases: Dict[str, CaseRecord] = Field(
        default_factory=dict,
        description="All cases indexed by case_id",
    )
    client_index: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Index: client_id -> [case_ids]",
    )
    pubkey_index: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Index: client_public_key -> [case_ids]",
    )

    def add_case(self, case: CaseRecord) -> None:
        """Add a case to memory."""
        self.cases[case.case_id] = case

        # Update client index
        if case.client_id not in self.client_index:
            self.client_index[case.client_id] = []
        if case.case_id not in self.client_index[case.client_id]:
            self.client_index[case.client_id].append(case.case_id)

        # Update pubkey index
        if case.client_public_key:
            if case.client_public_key not in self.pubkey_index:
                self.pubkey_index[case.client_public_key] = []
            if case.case_id not in self.pubkey_index[case.client_public_key]:
                self.pubkey_index[case.client_public_key].append(case.case_id)

    def get_case(self, case_id: str) -> Optional[CaseRecord]:
        """Get a case by ID."""
        return self.cases.get(case_id)

    def find_cases_by_client(self, client_id: str) -> List[CaseRecord]:
        """Find all cases for a client."""
        case_ids = self.client_index.get(client_id, [])
        return [self.cases[cid] for cid in case_ids if cid in self.cases]

    def find_cases_by_pubkey(self, client_public_key: str) -> List[CaseRecord]:
        """Find all cases by client's public key."""
        pubkey = client_public_key.lower()
        case_ids = self.pubkey_index.get(pubkey, [])
        return [self.cases[cid] for cid in case_ids if cid in self.cases]

    def find_active_cases(self) -> List[CaseRecord]:
        """Find all active cases."""
        return [c for c in self.cases.values() if c.status == "active"]

    def find_cases_with_questions(self) -> List[CaseRecord]:
        """Find cases that have unanswered AI questions."""
        return [
            c for c in self.cases.values()
            if any(not q.get("answered", False) for q in c.ai_questions)
        ]

    def get_context_for_request(self, request: ServiceRequest) -> Optional[Dict[str, Any]]:
        """
        Get case context for a service request.

        Tries to match the request to an existing case by client public key.
        Returns the case context if found.
        """
        cases = self.find_cases_by_pubkey(request.client)
        if cases:
            # Return the most recently updated active case
            active_cases = [c for c in cases if c.status == "active"]
            if active_cases:
                # Sort by updated_at descending
                active_cases.sort(key=lambda c: c.updated_at, reverse=True)
                return active_cases[0].get_context_for_consultation()
        return None

    def create_or_update_case_from_request(
        self,
        request: ServiceRequest,
        response: ServiceResponse,
    ) -> CaseRecord:
        """
        Create or update a case based on a consultation.

        If a case exists for this client, updates it.
        Otherwise, creates a new case.
        """
        existing_cases = self.find_cases_by_pubkey(request.client)
        active_cases = [c for c in existing_cases if c.status == "active"]

        if active_cases:
            # Update existing case
            case = active_cases[0]
            case.link_consultation(request.request_id)
            case.add_note(
                content=f"Consultation: {request.query[:100]}...",
                note_type="update",
                author="ai",
            )
            return case
        else:
            # Create new case
            case = CaseRecord(
                client_id=request.client[:16] + "...",  # Anonymized
                client_public_key=request.client,
                category=request.context.get("category", "general") if request.context else "general",
                title=f"Consultation: {request.query[:50]}...",
            )
            case.link_consultation(request.request_id)
            case.add_note(
                content=f"Initial consultation: {request.query}",
                note_type="update",
                author="ai",
            )
            self.add_case(case)
            return case


# Helper functions for provider workflow

def create_case_record(
    client_id: str,
    category: str,
    title: str,
    client_public_key: Optional[str] = None,
    **kwargs,
) -> CaseRecord:
    """Create a new case record."""
    return CaseRecord(
        client_id=client_id,
        category=category,
        title=title,
        client_public_key=client_public_key,
        **kwargs,
    )


def create_provider_session(provider: str) -> ProviderSession:
    """Create a new provider session."""
    return ProviderSession(provider=provider)


def create_case_memory(provider: str) -> CaseMemory:
    """Create a new case memory store."""
    return CaseMemory(provider=provider)
