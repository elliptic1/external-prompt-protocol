"""
EPP Service Registry - Discovery layer for AI services.

The registry is how AI agents find services they need. Think "DNS for AI capabilities."

Business Model:
- Service providers register their capabilities
- Client AIs query the registry to find services
- Registry operators can charge listing fees or take discovery fees
- Federated: anyone can run a registry, registries can peer with each other
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class ServiceCapability(BaseModel):
    """A capability that a service provides."""

    name: str = Field(
        ...,
        description="Capability identifier (e.g., 'legal-consultation', 'image-generation')",
    )
    version: str = Field(
        default="1.0",
        description="Capability version",
    )
    description: Optional[str] = Field(
        default=None,
        description="Human-readable description",
    )
    input_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        description="JSON schema for expected input",
    )
    output_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        description="JSON schema for expected output",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9\-]+$", v):
            raise ValueError(f"Capability name must be lowercase alphanumeric with hyphens: {v}")
        return v


class ServiceRegistration(BaseModel):
    """
    A service registration in the EPP registry.

    This is how services advertise themselves for discovery.
    """

    service_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique service identifier",
    )
    provider: str = Field(
        ...,
        description="Provider's EPP public key (64 hex chars)",
    )
    name: str = Field(
        ...,
        description="Human-readable service name",
    )
    description: str = Field(
        ...,
        description="Service description",
    )
    capabilities: List[ServiceCapability] = Field(
        default_factory=list,
        description="Capabilities this service provides",
    )
    categories: List[str] = Field(
        default_factory=list,
        description="Category tags (e.g., ['legal', 'employment'])",
    )
    inbox_url: str = Field(
        ...,
        description="EPP inbox URL for this service",
    )
    pricing: Dict[str, Any] = Field(
        default_factory=dict,
        description="Pricing information",
    )
    min_price: Optional[str] = Field(
        default=None,
        description="Minimum price (for search filtering)",
    )
    max_price: Optional[str] = Field(
        default=None,
        description="Maximum price (for search filtering)",
    )
    currency: str = Field(
        default="USDC",
        description="Primary currency",
    )
    chain: str = Field(
        default="base",
        description="Primary payment chain",
    )
    rating: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=5.0,
        description="Average rating (0-5)",
    )
    review_count: int = Field(
        default=0,
        description="Number of reviews",
    )
    transaction_count: int = Field(
        default=0,
        description="Total transactions processed",
    )
    verified: bool = Field(
        default=False,
        description="Whether the provider is verified",
    )
    verification_type: Optional[str] = Field(
        default=None,
        description="Type of verification (e.g., 'kyc', 'professional-license')",
    )
    active: bool = Field(
        default=True,
        description="Whether service is currently active",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        description="Registration timestamp",
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        description="Last update timestamp",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional metadata",
    )

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if not re.match(r"^[0-9a-fA-F]{64}$", v):
            raise ValueError(f"Provider must be 64 hex characters: {v}")
        return v.lower()

    @field_validator("categories")
    @classmethod
    def validate_categories(cls, v: List[str]) -> List[str]:
        return [c.lower() for c in v]


class RegistryQuery(BaseModel):
    """Query parameters for searching the registry."""

    capability: Optional[str] = Field(
        default=None,
        description="Required capability",
    )
    categories: List[str] = Field(
        default_factory=list,
        description="Filter by categories (OR logic)",
    )
    max_price: Optional[str] = Field(
        default=None,
        description="Maximum price filter",
    )
    currency: Optional[str] = Field(
        default=None,
        description="Required currency",
    )
    chain: Optional[str] = Field(
        default=None,
        description="Required chain",
    )
    min_rating: Optional[float] = Field(
        default=None,
        description="Minimum rating",
    )
    verified_only: bool = Field(
        default=False,
        description="Only return verified providers",
    )
    active_only: bool = Field(
        default=True,
        description="Only return active services",
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Max results to return",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Pagination offset",
    )
    sort_by: Literal["rating", "price", "transactions", "created"] = Field(
        default="rating",
        description="Sort order",
    )


class Registry(BaseModel):
    """
    EPP Service Registry.

    In production, this would be backed by a database and exposed via API.
    This is the in-memory reference implementation.
    """

    registry_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique registry identifier",
    )
    name: str = Field(
        default="EPP Registry",
        description="Registry name",
    )
    operator: str = Field(
        ...,
        description="Registry operator's EPP public key",
    )
    services: Dict[str, ServiceRegistration] = Field(
        default_factory=dict,
        description="Registered services by service_id",
    )
    provider_index: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Index: provider pubkey -> [service_ids]",
    )
    capability_index: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Index: capability -> [service_ids]",
    )
    category_index: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Index: category -> [service_ids]",
    )
    listing_fee: Optional[str] = Field(
        default=None,
        description="Fee to list a service (optional)",
    )
    discovery_fee: Optional[str] = Field(
        default=None,
        description="Fee per discovery query (optional)",
    )

    def register(self, service: ServiceRegistration) -> None:
        """Register a service in the registry."""
        self.services[service.service_id] = service

        # Update provider index
        if service.provider not in self.provider_index:
            self.provider_index[service.provider] = []
        if service.service_id not in self.provider_index[service.provider]:
            self.provider_index[service.provider].append(service.service_id)

        # Update capability index
        for cap in service.capabilities:
            if cap.name not in self.capability_index:
                self.capability_index[cap.name] = []
            if service.service_id not in self.capability_index[cap.name]:
                self.capability_index[cap.name].append(service.service_id)

        # Update category index
        for cat in service.categories:
            if cat not in self.category_index:
                self.category_index[cat] = []
            if service.service_id not in self.category_index[cat]:
                self.category_index[cat].append(service.service_id)

    def unregister(self, service_id: str) -> bool:
        """Remove a service from the registry."""
        if service_id not in self.services:
            return False

        service = self.services[service_id]

        # Remove from provider index
        if service.provider in self.provider_index:
            self.provider_index[service.provider] = [
                sid for sid in self.provider_index[service.provider]
                if sid != service_id
            ]

        # Remove from capability index
        for cap in service.capabilities:
            if cap.name in self.capability_index:
                self.capability_index[cap.name] = [
                    sid for sid in self.capability_index[cap.name]
                    if sid != service_id
                ]

        # Remove from category index
        for cat in service.categories:
            if cat in self.category_index:
                self.category_index[cat] = [
                    sid for sid in self.category_index[cat]
                    if sid != service_id
                ]

        del self.services[service_id]
        return True

    def get(self, service_id: str) -> Optional[ServiceRegistration]:
        """Get a service by ID."""
        return self.services.get(service_id)

    def search(self, query: RegistryQuery) -> List[ServiceRegistration]:
        """Search for services matching the query."""
        # Start with all services or filtered by capability/category
        candidate_ids: Optional[set] = None

        if query.capability:
            cap_ids = set(self.capability_index.get(query.capability, []))
            candidate_ids = cap_ids if candidate_ids is None else candidate_ids & cap_ids

        if query.categories:
            cat_ids: set = set()
            for cat in query.categories:
                cat_ids.update(self.category_index.get(cat.lower(), []))
            candidate_ids = cat_ids if candidate_ids is None else candidate_ids & cat_ids

        if candidate_ids is None:
            candidate_ids = set(self.services.keys())

        # Filter candidates
        results = []
        for sid in candidate_ids:
            service = self.services.get(sid)
            if not service:
                continue

            # Apply filters
            if query.active_only and not service.active:
                continue
            if query.verified_only and not service.verified:
                continue
            if query.currency and service.currency != query.currency.upper():
                continue
            if query.chain and service.chain != query.chain.lower():
                continue
            if query.min_rating and (service.rating is None or service.rating < query.min_rating):
                continue
            # Note: max_price filter would need decimal comparison in production

            results.append(service)

        # Sort
        if query.sort_by == "rating":
            results.sort(key=lambda s: s.rating or 0, reverse=True)
        elif query.sort_by == "transactions":
            results.sort(key=lambda s: s.transaction_count, reverse=True)
        elif query.sort_by == "created":
            results.sort(key=lambda s: s.created_at, reverse=True)
        # price sorting would need decimal parsing

        # Paginate
        return results[query.offset : query.offset + query.limit]

    def find_by_capability(self, capability: str) -> List[ServiceRegistration]:
        """Find all services with a specific capability."""
        service_ids = self.capability_index.get(capability, [])
        return [self.services[sid] for sid in service_ids if sid in self.services]

    def find_by_provider(self, provider: str) -> List[ServiceRegistration]:
        """Find all services by a provider."""
        provider = provider.lower()
        service_ids = self.provider_index.get(provider, [])
        return [self.services[sid] for sid in service_ids if sid in self.services]

    def update_rating(self, service_id: str, new_rating: float) -> bool:
        """Update a service's rating (called after reviews)."""
        service = self.services.get(service_id)
        if not service:
            return False

        # Simple average (production would use weighted/time-decayed)
        if service.rating is None:
            service.rating = new_rating
        else:
            total = service.rating * service.review_count + new_rating
            service.review_count += 1
            service.rating = total / service.review_count

        service.updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return True

    def increment_transactions(self, service_id: str) -> bool:
        """Increment transaction count for a service."""
        service = self.services.get(service_id)
        if not service:
            return False
        service.transaction_count += 1
        return True


# Standard capability definitions
STANDARD_CAPABILITIES = {
    "legal-consultation": "Legal information and consultation services",
    "medical-consultation": "Medical information and health consultation",
    "financial-advice": "Financial planning and advice services",
    "tax-preparation": "Tax preparation and filing assistance",
    "translation": "Language translation services",
    "code-review": "Source code review and analysis",
    "image-generation": "AI image generation",
    "text-generation": "AI text generation and writing",
    "data-analysis": "Data analysis and insights",
    "research": "Research and information gathering",
    "scheduling": "Calendar and scheduling services",
    "customer-support": "Customer service and support",
}


def create_registry(operator: str, name: str = "EPP Registry") -> Registry:
    """Create a new registry instance."""
    return Registry(operator=operator, name=name)


def create_service_registration(
    provider: str,
    name: str,
    description: str,
    inbox_url: str,
    capabilities: List[str] = None,
    categories: List[str] = None,
    min_price: str = None,
    currency: str = "USDC",
    chain: str = "base",
    **kwargs,
) -> ServiceRegistration:
    """Create a service registration with common defaults."""
    caps = [
        ServiceCapability(name=c, description=STANDARD_CAPABILITIES.get(c))
        for c in (capabilities or [])
    ]

    return ServiceRegistration(
        provider=provider,
        name=name,
        description=description,
        inbox_url=inbox_url,
        capabilities=caps,
        categories=categories or [],
        min_price=min_price,
        currency=currency,
        chain=chain,
        **kwargs,
    )
