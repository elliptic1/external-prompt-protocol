"""
Payment integration for EPP envelopes.

Implements x402-style payment requests and proofs for agent-to-agent commerce.
EPP doesn't process payments - it carries payment instructions and proofs.
"""

import re
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# Supported chains
SupportedChain = Literal[
    "ethereum", "base", "optimism", "arbitrum", "polygon", 
    "solana", "avalanche", "bsc"
]

SUPPORTED_CHAINS = (
    "ethereum", "base", "optimism", "arbitrum", "polygon",
    "solana", "avalanche", "bsc"
)

# Common currencies
SupportedCurrency = Literal[
    "USDC", "USDT", "ETH", "SOL", "MATIC", "AVAX", "BNB", "DAI"
]

SUPPORTED_CURRENCIES = (
    "USDC", "USDT", "ETH", "SOL", "MATIC", "AVAX", "BNB", "DAI"
)


class PaymentRequest(BaseModel):
    """
    Payment request in an EPP envelope.
    
    Used when the sender requires payment to process the request.
    Follows the x402 (HTTP 402 Payment Required) pattern.
    """
    
    required: bool = Field(
        default=True,
        description="Whether payment is required (vs optional tip)",
    )
    amount: str = Field(
        ...,
        description="Payment amount as string (to preserve precision)",
    )
    currency: str = Field(
        ...,
        description="Currency code (USDC, ETH, SOL, etc.)",
    )
    recipient: str = Field(
        ...,
        description="Recipient wallet address",
    )
    chain: str = Field(
        ...,
        description="Blockchain network (base, ethereum, solana, etc.)",
    )
    memo: Optional[str] = Field(
        default=None,
        description="Optional memo/reference for the payment",
    )
    expires_at: Optional[str] = Field(
        default=None,
        description="Payment deadline (ISO-8601 UTC)",
    )
    min_confirmations: int = Field(
        default=1,
        description="Minimum block confirmations required",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional payment metadata",
    )

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str) -> str:
        """Validate amount is a valid decimal string."""
        try:
            amount = Decimal(v)
            if amount <= 0:
                raise ValueError("Amount must be positive")
        except Exception as e:
            raise ValueError(f"Invalid amount: {v} - {e}")
        return v

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """Validate currency code."""
        v = v.upper()
        # Allow any alphanumeric currency code (not just predefined ones)
        if not re.match(r"^[A-Z0-9]{2,10}$", v):
            raise ValueError(f"Invalid currency code: {v}")
        return v

    @field_validator("chain")
    @classmethod
    def validate_chain(cls, v: str) -> str:
        """Validate chain identifier."""
        v = v.lower()
        # Allow any alphanumeric chain ID (not just predefined ones)
        if not re.match(r"^[a-z0-9\-]+$", v):
            raise ValueError(f"Invalid chain: {v}")
        return v

    @field_validator("recipient")
    @classmethod
    def validate_recipient(cls, v: str) -> str:
        """Validate recipient address format."""
        # Basic validation - starts with 0x for EVM or is base58 for Solana
        if not (v.startswith("0x") and len(v) == 42) and not re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", v):
            # Allow other formats too (ENS, etc.)
            if not re.match(r"^[a-zA-Z0-9\.\-_]+$", v):
                raise ValueError(f"Invalid recipient address: {v}")
        return v

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, v: Optional[str]) -> Optional[str]:
        """Validate expiration timestamp."""
        if v is not None:
            try:
                datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                raise ValueError(f"Invalid ISO-8601 timestamp: {v}")
        return v

    def is_expired(self) -> bool:
        """Check if payment request has expired."""
        if self.expires_at is None:
            return False
        expires_dt = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) > expires_dt

    def to_402_response(self) -> Dict[str, Any]:
        """
        Convert to HTTP 402 response format.
        
        Returns dict suitable for JSON response body.
        """
        return {
            "payment_required": True,
            "amount": self.amount,
            "currency": self.currency,
            "recipient": self.recipient,
            "chain": self.chain,
            "memo": self.memo,
            "expires_at": self.expires_at,
        }


class PaymentProof(BaseModel):
    """
    Proof of payment in an EPP envelope.
    
    Used to prove payment was made for a previous request.
    """
    
    tx_hash: str = Field(
        ...,
        description="Transaction hash on the blockchain",
    )
    chain: str = Field(
        ...,
        description="Blockchain network where payment was made",
    )
    amount: str = Field(
        ...,
        description="Amount paid",
    )
    currency: str = Field(
        ...,
        description="Currency paid",
    )
    payer: str = Field(
        ...,
        description="Payer wallet address",
    )
    recipient: str = Field(
        ...,
        description="Recipient wallet address",
    )
    block: Optional[int] = Field(
        default=None,
        description="Block number (if confirmed)",
    )
    confirmations: Optional[int] = Field(
        default=None,
        description="Number of confirmations",
    )
    timestamp: Optional[str] = Field(
        default=None,
        description="Transaction timestamp (ISO-8601 UTC)",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional transaction metadata",
    )

    @field_validator("tx_hash")
    @classmethod
    def validate_tx_hash(cls, v: str) -> str:
        """Validate transaction hash format."""
        # EVM: 0x + 64 hex chars, Solana: base58
        if v.startswith("0x"):
            if not re.match(r"^0x[0-9a-fA-F]{64}$", v):
                raise ValueError(f"Invalid EVM tx hash: {v}")
            return v.lower()
        elif re.match(r"^[1-9A-HJ-NP-Za-km-z]{64,88}$", v):
            return v  # Solana signature
        else:
            raise ValueError(f"Invalid tx hash format: {v}")

    @field_validator("chain")
    @classmethod
    def validate_chain(cls, v: str) -> str:
        """Validate chain identifier."""
        return v.lower()

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str) -> str:
        """Validate amount is a valid decimal string."""
        try:
            Decimal(v)
        except Exception:
            raise ValueError(f"Invalid amount: {v}")
        return v

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """Validate currency code."""
        return v.upper()

    def get_explorer_url(self) -> Optional[str]:
        """
        Get block explorer URL for this transaction.
        
        Returns URL or None if chain not recognized.
        """
        explorers = {
            "ethereum": "https://etherscan.io/tx/",
            "base": "https://basescan.org/tx/",
            "optimism": "https://optimistic.etherscan.io/tx/",
            "arbitrum": "https://arbiscan.io/tx/",
            "polygon": "https://polygonscan.com/tx/",
            "solana": "https://solscan.io/tx/",
            "avalanche": "https://snowtrace.io/tx/",
            "bsc": "https://bscscan.com/tx/",
        }
        base_url = explorers.get(self.chain)
        if base_url:
            return base_url + self.tx_hash
        return None


class StakeReference(BaseModel):
    """
    Reference to an on-chain stake for reputation.
    
    Used when an attestor has staked tokens as collateral for their attestation.
    The stake can be slashed if the attested content is found to be malicious.
    """
    
    contract: str = Field(
        ...,
        description="Staking contract address",
    )
    chain: str = Field(
        ...,
        description="Blockchain network",
    )
    amount: str = Field(
        ...,
        description="Amount staked",
    )
    currency: str = Field(
        ...,
        description="Staked currency",
    )
    staker: str = Field(
        ...,
        description="Staker's public key (EPP identity)",
    )
    stake_id: Optional[str] = Field(
        default=None,
        description="Stake identifier in the contract",
    )
    staked_at: Optional[str] = Field(
        default=None,
        description="When the stake was created (ISO-8601 UTC)",
    )
    unlock_at: Optional[str] = Field(
        default=None,
        description="When the stake can be withdrawn (ISO-8601 UTC)",
    )
    slash_conditions: Optional[str] = Field(
        default=None,
        description="Description of conditions that trigger slashing",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional stake metadata",
    )

    @field_validator("contract")
    @classmethod
    def validate_contract(cls, v: str) -> str:
        """Validate contract address."""
        if v.startswith("0x"):
            if len(v) != 42:
                raise ValueError(f"Invalid EVM contract address: {v}")
            return v.lower()
        return v

    @field_validator("chain")
    @classmethod
    def validate_chain(cls, v: str) -> str:
        """Validate chain identifier."""
        return v.lower()

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str) -> str:
        """Validate amount."""
        try:
            amount = Decimal(v)
            if amount <= 0:
                raise ValueError("Stake amount must be positive")
        except Exception as e:
            raise ValueError(f"Invalid stake amount: {v} - {e}")
        return v

    @field_validator("staker")
    @classmethod
    def validate_staker(cls, v: str) -> str:
        """Validate staker is a hex public key."""
        if not re.match(r"^[0-9a-fA-F]{64}$", v):
            raise ValueError(f"Staker must be 64 hex characters: {v}")
        return v.lower()


def payment_request_from_dict(data: Optional[Dict[str, Any]]) -> Optional[PaymentRequest]:
    """Create PaymentRequest from dict."""
    if data is None:
        return None
    return PaymentRequest(**data)


def payment_proof_from_dict(data: Optional[Dict[str, Any]]) -> Optional[PaymentProof]:
    """Create PaymentProof from dict."""
    if data is None:
        return None
    return PaymentProof(**data)


def stake_reference_from_dict(data: Optional[Dict[str, Any]]) -> Optional[StakeReference]:
    """Create StakeReference from dict."""
    if data is None:
        return None
    return StakeReference(**data)


def create_payment_request(
    amount: str,
    currency: str,
    recipient: str,
    chain: str,
    memo: Optional[str] = None,
    expires_in_minutes: int = 15,
    required: bool = True,
) -> PaymentRequest:
    """
    Create a payment request with sensible defaults.
    
    Args:
        amount: Payment amount
        currency: Currency code (USDC, ETH, etc.)
        recipient: Recipient wallet address
        chain: Blockchain network
        memo: Optional memo/reference
        expires_in_minutes: Minutes until expiration (default 15)
        required: Whether payment is required vs optional
        
    Returns:
        PaymentRequest object
    """
    from datetime import timedelta
    
    expires_at = (
        datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)
    ).isoformat().replace("+00:00", "Z")
    
    return PaymentRequest(
        required=required,
        amount=amount,
        currency=currency,
        recipient=recipient,
        chain=chain,
        memo=memo,
        expires_at=expires_at,
    )


def verify_payment_proof(
    proof: PaymentProof,
    request: PaymentRequest,
    tolerance_percent: float = 1.0,
) -> tuple[bool, List[str]]:
    """
    Verify that a payment proof matches a payment request.
    
    Note: This does NOT verify on-chain - only checks the proof matches the request.
    On-chain verification requires chain-specific RPC calls.
    
    Args:
        proof: The payment proof to verify
        request: The original payment request
        tolerance_percent: Allowed difference in amount (for gas/fees)
        
    Returns:
        Tuple of (is_valid, list of issues)
    """
    issues = []
    
    # Check chain matches
    if proof.chain != request.chain:
        issues.append(f"Chain mismatch: proof={proof.chain}, request={request.chain}")
    
    # Check currency matches
    if proof.currency != request.currency:
        issues.append(f"Currency mismatch: proof={proof.currency}, request={request.currency}")
    
    # Check recipient matches
    if proof.recipient.lower() != request.recipient.lower():
        issues.append(f"Recipient mismatch: proof={proof.recipient}, request={request.recipient}")
    
    # Check amount (with tolerance)
    try:
        proof_amount = Decimal(proof.amount)
        request_amount = Decimal(request.amount)
        min_amount = request_amount * Decimal(1 - tolerance_percent / 100)
        
        if proof_amount < min_amount:
            issues.append(
                f"Amount too low: proof={proof.amount}, request={request.amount} "
                f"(min={min_amount})"
            )
    except Exception as e:
        issues.append(f"Amount comparison failed: {e}")
    
    return (len(issues) == 0, issues)
