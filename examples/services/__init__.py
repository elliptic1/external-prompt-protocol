"""
AI-to-AI Services - Example Implementation

This is a reference implementation showing how to build paid consultation
services on top of EPP. It is NOT part of the core EPP protocol.

Use Case:
- Person wants legal advice but doesn't want to leave home
- They talk to their own AI, which pays a fee to use the lawyer's AI
- The lawyer's AI responds with advice
- The lawyer doesn't do extra work; the person only talks to their own AI
"""

from .services import (
    # Service categories
    ServiceCategory,
    SERVICE_CATEGORIES,
    BillingModel,
    # Models
    ServiceTier,
    JurisdictionInfo,
    ServiceListing,
    ServiceRequest,
    ServiceResponse,
    ConsultationSession,
    # Provider workflow
    CaseNote,
    CaseRecord,
    ProviderMessage,
    ProviderSession,
    CaseMemory,
    # Helper functions
    create_service_listing,
    create_legal_consultation_listing,
    create_service_request,
    create_service_response,
    create_consultation_session,
    create_case_record,
    create_provider_session,
    create_case_memory,
    # Payload conversion
    service_request_to_payload,
    service_response_to_payload,
    service_listing_to_payload,
)

__all__ = [
    "ServiceCategory",
    "SERVICE_CATEGORIES",
    "BillingModel",
    "ServiceTier",
    "JurisdictionInfo",
    "ServiceListing",
    "ServiceRequest",
    "ServiceResponse",
    "ConsultationSession",
    "CaseNote",
    "CaseRecord",
    "ProviderMessage",
    "ProviderSession",
    "CaseMemory",
    "create_service_listing",
    "create_legal_consultation_listing",
    "create_service_request",
    "create_service_response",
    "create_consultation_session",
    "create_case_record",
    "create_provider_session",
    "create_case_memory",
    "service_request_to_payload",
    "service_response_to_payload",
    "service_listing_to_payload",
]
