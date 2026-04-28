"""
Chain identity declaration for EPP envelopes (v1.1).

Allows a sender to declare an on-chain identity (NFT-bound, ENS, Lens, etc.)
that an executor or trust registry can choose to verify out-of-band.

EPP itself does not perform on-chain verification — verification is left to
the receiver's executor or a separate identity service. This module only
carries the claim and validates its shape.
"""

import re
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from epp.payment import SUPPORTED_CHAINS

SUPPORTED_STANDARDS = (
    "erc-8004",
    "ens",
    "lens",
    "did",
    "custom",
)
SupportedStandard = Literal[
    "erc-8004",
    "ens",
    "lens",
    "did",
    "custom",
]

SUPPORTED_VERIFICATION_METHODS = (
    "on-chain-lookup",
    "attestation",
    "oracle",
    "self",
)


class ChainIdentity(BaseModel):
    """
    A claim that the sender's identity is anchored on-chain.

    Typical use: a sender holds an ERC-8004 identity NFT on Base and wants
    receivers to be able to verify that the envelope sender pubkey matches
    the NFT's controller.
    """

    standard: str = Field(
        ...,
        description="Identity standard (erc-8004, ens, lens, did, custom)",
    )
    chain: str = Field(
        ...,
        description="Blockchain network (ethereum, base, optimism, ...)",
    )
    contract: Optional[str] = Field(
        default=None,
        description="Smart contract address (when applicable, e.g. ERC-8004 registry)",
    )
    token_id: Optional[str] = Field(
        default=None,
        description="NFT token ID (string to preserve precision)",
    )
    identifier: Optional[str] = Field(
        default=None,
        description="Off-chain identifier (e.g. 'alice.eth' for ENS, 'lens/alice' for Lens)",
    )
    verification_method: str = Field(
        default="on-chain-lookup",
        description="How a recipient should verify (on-chain-lookup, attestation, oracle, self)",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional standard-specific metadata",
    )

    @field_validator("standard")
    @classmethod
    def validate_standard(cls, v: str) -> str:
        v = v.lower()
        if v not in SUPPORTED_STANDARDS:
            raise ValueError(
                f"Unsupported chain_identity standard: {v}. Supported: {SUPPORTED_STANDARDS}"
            )
        return v

    @field_validator("chain")
    @classmethod
    def validate_chain(cls, v: str) -> str:
        v = v.lower()
        if v not in SUPPORTED_CHAINS:
            # Permit unknown chains for forward-compatibility but enforce shape.
            if not re.match(r"^[a-z0-9\-]+$", v):
                raise ValueError(f"Invalid chain identifier: {v}")
        return v

    @field_validator("contract")
    @classmethod
    def validate_contract(cls, v: Optional[str]) -> Optional[str]:
        """Validate contract address shape (best-effort, chain-agnostic)."""
        if v is None:
            return None
        if v.startswith("0x"):
            if len(v) != 42 or not re.match(r"^0x[0-9a-fA-F]{40}$", v):
                raise ValueError(f"Invalid EVM contract address: {v}")
            return v.lower()
        # Solana / non-EVM: base58, length 32-44
        if not re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", v):
            raise ValueError(f"Invalid contract address: {v}")
        return v

    @field_validator("token_id")
    @classmethod
    def validate_token_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        # Token IDs are typically decimal strings; allow hex for ERC-1155.
        if not re.match(r"^(0x)?[0-9a-fA-F]+$", v):
            raise ValueError(f"Invalid token_id: {v}")
        return v

    @field_validator("identifier")
    @classmethod
    def validate_identifier(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        # Allow ENS-style names, Lens handles, DIDs, and similar.
        if not re.match(r"^[a-zA-Z0-9_\-:./]+$", v):
            raise ValueError(f"Invalid identifier: {v}")
        return v

    @field_validator("verification_method")
    @classmethod
    def validate_verification_method(cls, v: str) -> str:
        v = v.lower()
        if v not in SUPPORTED_VERIFICATION_METHODS:
            raise ValueError(
                f"Unsupported verification_method: {v}. "
                f"Supported: {SUPPORTED_VERIFICATION_METHODS}"
            )
        return v


def chain_identity_from_dict(data: Optional[Dict[str, Any]]) -> Optional[ChainIdentity]:
    """Construct ChainIdentity from a dict, or return None."""
    if data is None:
        return None
    return ChainIdentity(**data)
