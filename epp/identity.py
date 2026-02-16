"""
EPP Agent Identity - The identity layer for AI agents.

Every AI agent needs to prove who it is. EPP Identity provides:
1. Cryptographic identity (Ed25519 keys)
2. Agent profiles with capabilities
3. Verification and attestation
4. Reputation tracking
5. Identity linking (to on-chain identities, professional licenses, etc.)

This is the "SSL of the AI era" - verified identity for every AI interaction.
"""

import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class AgentCapability(BaseModel):
    """A capability an agent has."""

    name: str = Field(..., description="Capability identifier")
    level: Literal["basic", "intermediate", "advanced", "expert"] = Field(
        default="basic",
        description="Proficiency level",
    )
    verified: bool = Field(
        default=False,
        description="Whether this capability is verified",
    )
    verified_by: Optional[str] = Field(
        default=None,
        description="Who verified this capability (public key)",
    )
    verified_at: Optional[str] = Field(
        default=None,
        description="When capability was verified",
    )


class AgentAttestation(BaseModel):
    """
    An attestation about an agent from another party.

    Attestations are how agents build trust:
    - A professional body attests to a lawyer's AI having legal knowledge
    - A platform attests to an agent's reliability
    - Users attest to quality of service
    """

    attestation_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique attestation ID",
    )
    subject: str = Field(
        ...,
        description="Agent being attested (public key)",
    )
    attestor: str = Field(
        ...,
        description="Who is making the attestation (public key)",
    )
    attestation_type: Literal[
        "identity",
        "capability",
        "professional-license",
        "platform-verified",
        "review",
        "endorsement",
        "revocation",
    ] = Field(
        ...,
        description="Type of attestation",
    )
    claim: str = Field(
        ...,
        description="The attestation claim",
    )
    evidence: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Supporting evidence",
    )
    signature: str = Field(
        ...,
        description="Attestor's signature over the claim",
    )
    issued_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        description="When attestation was issued",
    )
    expires_at: Optional[str] = Field(
        default=None,
        description="When attestation expires",
    )
    revoked: bool = Field(
        default=False,
        description="Whether attestation has been revoked",
    )

    @field_validator("subject", "attestor")
    @classmethod
    def validate_pubkey(cls, v: str) -> str:
        if not re.match(r"^[0-9a-fA-F]{64}$", v):
            raise ValueError(f"Must be 64 hex characters: {v}")
        return v.lower()

    def is_valid(self) -> bool:
        """Check if attestation is currently valid."""
        if self.revoked:
            return False
        if self.expires_at:
            expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > expires:
                return False
        return True


class LinkedIdentity(BaseModel):
    """A linked external identity (on-chain, professional license, etc.)."""

    identity_type: Literal[
        "ethereum",
        "solana",
        "ens",
        "lens",
        "professional-license",
        "domain",
        "social",
        "custom",
    ] = Field(
        ...,
        description="Type of linked identity",
    )
    identifier: str = Field(
        ...,
        description="The external identifier (address, handle, license number, etc.)",
    )
    chain: Optional[str] = Field(
        default=None,
        description="Blockchain (if applicable)",
    )
    verification_method: Optional[str] = Field(
        default=None,
        description="How verification was performed",
    )
    verified: bool = Field(
        default=False,
        description="Whether link is verified",
    )
    verified_at: Optional[str] = Field(
        default=None,
        description="When link was verified",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional identity metadata",
    )


class AgentProfile(BaseModel):
    """
    An AI agent's identity profile.

    This is the core identity document for an AI agent in the EPP ecosystem.
    """

    agent_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique agent identifier",
    )
    public_key: str = Field(
        ...,
        description="Agent's EPP public key (primary identity)",
    )
    name: str = Field(
        ...,
        description="Agent name",
    )
    description: Optional[str] = Field(
        default=None,
        description="Agent description",
    )
    agent_type: Literal["personal", "service", "enterprise", "platform"] = Field(
        default="service",
        description="Type of agent",
    )
    owner: Optional[str] = Field(
        default=None,
        description="Owner's public key (for service agents)",
    )
    owner_type: Optional[Literal["individual", "organization"]] = Field(
        default=None,
        description="Type of owner",
    )
    capabilities: List[AgentCapability] = Field(
        default_factory=list,
        description="Agent capabilities",
    )
    linked_identities: List[LinkedIdentity] = Field(
        default_factory=list,
        description="Linked external identities",
    )
    attestations: List[str] = Field(
        default_factory=list,
        description="Attestation IDs for this agent",
    )
    # Trust metrics
    trust_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Computed trust score (0-1)",
    )
    transaction_count: int = Field(
        default=0,
        description="Total transactions processed",
    )
    success_rate: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Transaction success rate",
    )
    average_rating: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=5.0,
        description="Average rating from reviews",
    )
    rating_count: int = Field(
        default=0,
        description="Number of ratings",
    )
    # Status
    active: bool = Field(
        default=True,
        description="Whether agent is active",
    )
    verified: bool = Field(
        default=False,
        description="Whether agent identity is verified",
    )
    verification_level: Literal["none", "basic", "standard", "enhanced"] = Field(
        default="none",
        description="Level of identity verification",
    )
    # Timestamps
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        description="Profile creation time",
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        description="Last update time",
    )
    # Metadata
    inbox_url: Optional[str] = Field(
        default=None,
        description="EPP inbox URL",
    )
    website: Optional[str] = Field(
        default=None,
        description="Website URL",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional metadata",
    )

    @field_validator("public_key")
    @classmethod
    def validate_public_key(cls, v: str) -> str:
        if not re.match(r"^[0-9a-fA-F]{64}$", v):
            raise ValueError(f"Public key must be 64 hex characters: {v}")
        return v.lower()

    @field_validator("owner")
    @classmethod
    def validate_owner(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not re.match(r"^[0-9a-fA-F]{64}$", v):
            raise ValueError(f"Owner must be 64 hex characters: {v}")
        return v.lower() if v else None

    def add_capability(
        self,
        name: str,
        level: str = "basic",
        verified: bool = False,
    ) -> None:
        """Add a capability to the agent."""
        self.capabilities.append(
            AgentCapability(name=name, level=level, verified=verified)
        )
        self.updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def link_identity(
        self,
        identity_type: str,
        identifier: str,
        chain: str = None,
        verified: bool = False,
    ) -> None:
        """Link an external identity."""
        self.linked_identities.append(
            LinkedIdentity(
                identity_type=identity_type,
                identifier=identifier,
                chain=chain,
                verified=verified,
            )
        )
        self.updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def add_rating(self, rating: float) -> None:
        """Add a rating and update average."""
        if self.average_rating is None:
            self.average_rating = rating
        else:
            total = self.average_rating * self.rating_count + rating
            self.rating_count += 1
            self.average_rating = total / self.rating_count
        self.rating_count += 1
        self.updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def compute_trust_score(self) -> float:
        """
        Compute trust score based on various factors.

        This is a simple implementation - production would use more sophisticated models.
        """
        score = 0.0
        factors = 0

        # Verification level
        verification_scores = {"none": 0.0, "basic": 0.3, "standard": 0.6, "enhanced": 0.9}
        score += verification_scores.get(self.verification_level, 0)
        factors += 1

        # Rating
        if self.average_rating is not None:
            score += self.average_rating / 5.0
            factors += 1

        # Transaction history
        if self.transaction_count > 0:
            # More transactions = more trust, with diminishing returns
            tx_score = min(1.0, self.transaction_count / 1000)
            score += tx_score
            factors += 1

        # Success rate
        if self.success_rate is not None:
            score += self.success_rate
            factors += 1

        # Linked identities (more links = more trust)
        verified_links = sum(1 for li in self.linked_identities if li.verified)
        if verified_links > 0:
            link_score = min(1.0, verified_links / 5)
            score += link_score
            factors += 1

        self.trust_score = score / factors if factors > 0 else 0.0
        return self.trust_score


class IdentityRegistry(BaseModel):
    """
    Registry of agent identities.

    In production, this would be a distributed system.
    This is the reference implementation.
    """

    registry_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Registry identifier",
    )
    name: str = Field(
        default="EPP Identity Registry",
        description="Registry name",
    )
    operator: str = Field(
        ...,
        description="Registry operator's public key",
    )
    agents: Dict[str, AgentProfile] = Field(
        default_factory=dict,
        description="Registered agents by public key",
    )
    attestations: Dict[str, AgentAttestation] = Field(
        default_factory=dict,
        description="All attestations by ID",
    )

    def register(self, profile: AgentProfile) -> None:
        """Register an agent profile."""
        self.agents[profile.public_key] = profile

    def get(self, public_key: str) -> Optional[AgentProfile]:
        """Get an agent profile by public key."""
        return self.agents.get(public_key.lower())

    def add_attestation(self, attestation: AgentAttestation) -> None:
        """Add an attestation."""
        self.attestations[attestation.attestation_id] = attestation

        # Link to agent profile
        agent = self.agents.get(attestation.subject)
        if agent and attestation.attestation_id not in agent.attestations:
            agent.attestations.append(attestation.attestation_id)

    def get_attestations_for(self, public_key: str) -> List[AgentAttestation]:
        """Get all attestations for an agent."""
        agent = self.agents.get(public_key.lower())
        if not agent:
            return []

        return [
            self.attestations[aid]
            for aid in agent.attestations
            if aid in self.attestations
        ]

    def search(
        self,
        capability: str = None,
        verified_only: bool = False,
        min_trust_score: float = None,
        agent_type: str = None,
    ) -> List[AgentProfile]:
        """Search for agents matching criteria."""
        results = []

        for agent in self.agents.values():
            if not agent.active:
                continue
            if verified_only and not agent.verified:
                continue
            if agent_type and agent.agent_type != agent_type:
                continue
            if min_trust_score and (
                agent.trust_score is None or agent.trust_score < min_trust_score
            ):
                continue
            if capability:
                has_cap = any(c.name == capability for c in agent.capabilities)
                if not has_cap:
                    continue

            results.append(agent)

        return results


def create_agent_profile(
    public_key: str,
    name: str,
    agent_type: str = "service",
    description: str = None,
    owner: str = None,
    **kwargs,
) -> AgentProfile:
    """Create an agent profile."""
    return AgentProfile(
        public_key=public_key,
        name=name,
        agent_type=agent_type,
        description=description,
        owner=owner,
        **kwargs,
    )


def create_identity_registry(operator: str, name: str = "EPP Identity Registry") -> IdentityRegistry:
    """Create an identity registry."""
    return IdentityRegistry(operator=operator, name=name)


def create_attestation(
    subject: str,
    attestor: str,
    attestation_type: str,
    claim: str,
    signature: str,
    evidence: Dict[str, Any] = None,
    expires_in_days: int = None,
) -> AgentAttestation:
    """Create an attestation."""
    expires_at = None
    if expires_in_days:
        expires_at = (
            (datetime.now(timezone.utc) + timedelta(days=expires_in_days))
            .isoformat()
            .replace("+00:00", "Z")
        )

    return AgentAttestation(
        subject=subject,
        attestor=attestor,
        attestation_type=attestation_type,
        claim=claim,
        signature=signature,
        evidence=evidence,
        expires_at=expires_at,
    )
