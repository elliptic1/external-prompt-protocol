"""
EPP Protocol Fees - The business model layer.

Every transaction through EPP can include a protocol fee that goes to:
1. Protocol treasury (development, maintenance)
2. Registry operators (service discovery)
3. Relay operators (message routing)

This is how EPP makes money at scale.

Fee Structure:
- Base fee: Fixed fee per transaction (e.g., $0.01)
- Percentage fee: Percentage of transaction value (e.g., 1%)
- Registry fee: Fee for service discovery
- Relay fee: Fee for message routing

Fees are transparent and declared in the envelope.
"""

import re
from decimal import Decimal, ROUND_UP
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class FeeRate(BaseModel):
    """A fee rate configuration."""

    fee_type: Literal["fixed", "percentage", "tiered"] = Field(
        ...,
        description="Type of fee calculation",
    )
    amount: str = Field(
        ...,
        description="Fee amount (fixed) or percentage (as decimal, e.g., '0.01' for 1%)",
    )
    currency: str = Field(
        default="USDC",
        description="Currency for fixed fees",
    )
    min_fee: Optional[str] = Field(
        default=None,
        description="Minimum fee (for percentage-based)",
    )
    max_fee: Optional[str] = Field(
        default=None,
        description="Maximum fee cap (for percentage-based)",
    )

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str) -> str:
        try:
            Decimal(v)
        except Exception:
            raise ValueError(f"Invalid fee amount: {v}")
        return v

    def calculate(self, transaction_amount: str) -> Decimal:
        """Calculate fee for a given transaction amount."""
        amount = Decimal(transaction_amount)

        if self.fee_type == "fixed":
            fee = Decimal(self.amount)
        elif self.fee_type == "percentage":
            fee = amount * Decimal(self.amount)
        else:
            raise ValueError(f"Unsupported fee type: {self.fee_type}")

        # Apply min/max
        if self.min_fee:
            fee = max(fee, Decimal(self.min_fee))
        if self.max_fee:
            fee = min(fee, Decimal(self.max_fee))

        return fee.quantize(Decimal("0.000001"), rounding=ROUND_UP)


class FeeSchedule(BaseModel):
    """
    Fee schedule for EPP transactions.

    Defines all fees that apply to transactions.
    """

    schedule_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique schedule identifier",
    )
    name: str = Field(
        default="Default",
        description="Schedule name",
    )
    protocol_fee: FeeRate = Field(
        default_factory=lambda: FeeRate(
            fee_type="percentage",
            amount="0.01",  # 1% protocol fee
            min_fee="0.01",  # $0.01 minimum
            max_fee="10.00",  # $10 cap
        ),
        description="Fee to EPP protocol",
    )
    registry_fee: Optional[FeeRate] = Field(
        default=None,
        description="Fee to registry operator (for discovery)",
    )
    relay_fee: Optional[FeeRate] = Field(
        default=None,
        description="Fee to relay operator (for routing)",
    )
    active: bool = Field(
        default=True,
        description="Whether this schedule is active",
    )
    effective_from: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        description="When this schedule takes effect",
    )

    def calculate_total(self, transaction_amount: str) -> "FeeBreakdown":
        """Calculate all fees for a transaction."""
        amount = Decimal(transaction_amount)

        protocol = self.protocol_fee.calculate(transaction_amount)
        registry = (
            self.registry_fee.calculate(transaction_amount)
            if self.registry_fee
            else Decimal("0")
        )
        relay = (
            self.relay_fee.calculate(transaction_amount)
            if self.relay_fee
            else Decimal("0")
        )

        total = protocol + registry + relay

        return FeeBreakdown(
            transaction_amount=str(amount),
            protocol_fee=str(protocol),
            registry_fee=str(registry) if registry else None,
            relay_fee=str(relay) if relay else None,
            total_fees=str(total),
            net_to_provider=str(amount - total),
        )


class FeeBreakdown(BaseModel):
    """Breakdown of fees for a transaction."""

    transaction_amount: str = Field(..., description="Original transaction amount")
    protocol_fee: str = Field(..., description="Fee to EPP protocol")
    registry_fee: Optional[str] = Field(default=None, description="Fee to registry")
    relay_fee: Optional[str] = Field(default=None, description="Fee to relay")
    total_fees: str = Field(..., description="Total fees")
    net_to_provider: str = Field(..., description="Amount provider receives")

    def to_dict(self) -> Dict[str, str]:
        """Convert to dict for envelope inclusion."""
        d = {
            "transaction_amount": self.transaction_amount,
            "protocol_fee": self.protocol_fee,
            "total_fees": self.total_fees,
            "net_to_provider": self.net_to_provider,
        }
        if self.registry_fee:
            d["registry_fee"] = self.registry_fee
        if self.relay_fee:
            d["relay_fee"] = self.relay_fee
        return d


class FeeRecipient(BaseModel):
    """A recipient of protocol fees."""

    address: str = Field(..., description="Wallet address")
    chain: str = Field(default="base", description="Blockchain")
    share: str = Field(..., description="Share of fees (decimal, e.g., '0.5' for 50%)")
    name: Optional[str] = Field(default=None, description="Recipient name")
    recipient_type: Literal["protocol", "registry", "relay", "referrer"] = Field(
        ...,
        description="Type of recipient",
    )

    @field_validator("share")
    @classmethod
    def validate_share(cls, v: str) -> str:
        share = Decimal(v)
        if share < 0 or share > 1:
            raise ValueError(f"Share must be between 0 and 1: {v}")
        return v


class ProtocolTreasury(BaseModel):
    """
    EPP Protocol Treasury configuration.

    Defines where protocol fees go and how they're split.
    """

    treasury_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Treasury identifier",
    )
    primary_address: str = Field(
        ...,
        description="Primary treasury wallet address",
    )
    chain: str = Field(
        default="base",
        description="Primary chain",
    )
    recipients: List[FeeRecipient] = Field(
        default_factory=list,
        description="Fee split recipients",
    )
    total_collected: str = Field(
        default="0",
        description="Total fees collected (for tracking)",
    )
    transaction_count: int = Field(
        default=0,
        description="Number of transactions processed",
    )

    def add_recipient(
        self,
        address: str,
        share: str,
        recipient_type: str,
        name: str = None,
        chain: str = None,
    ) -> None:
        """Add a fee recipient."""
        self.recipients.append(
            FeeRecipient(
                address=address,
                chain=chain or self.chain,
                share=share,
                name=name,
                recipient_type=recipient_type,
            )
        )

    def calculate_splits(self, total_fee: str) -> Dict[str, str]:
        """Calculate how fees split among recipients."""
        fee = Decimal(total_fee)
        splits = {}

        for recipient in self.recipients:
            share = fee * Decimal(recipient.share)
            splits[recipient.address] = str(share.quantize(Decimal("0.000001")))

        return splits

    def record_transaction(self, fee_amount: str) -> None:
        """Record a transaction's fees."""
        self.total_collected = str(
            Decimal(self.total_collected) + Decimal(fee_amount)
        )
        self.transaction_count += 1


class TransactionRecord(BaseModel):
    """Record of a transaction with fees."""

    transaction_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique transaction ID",
    )
    envelope_id: str = Field(..., description="Associated EPP envelope ID")
    service_id: Optional[str] = Field(default=None, description="Service used")
    provider: str = Field(..., description="Provider public key")
    client: str = Field(..., description="Client public key")
    amount: str = Field(..., description="Transaction amount")
    currency: str = Field(default="USDC", description="Currency")
    chain: str = Field(default="base", description="Blockchain")
    fees: FeeBreakdown = Field(..., description="Fee breakdown")
    payment_tx: Optional[str] = Field(default=None, description="Payment transaction hash")
    status: Literal["pending", "completed", "failed", "refunded"] = Field(
        default="pending",
        description="Transaction status",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        description="Transaction timestamp",
    )


# Default fee schedules
DEFAULT_FEE_SCHEDULE = FeeSchedule(
    name="Standard",
    protocol_fee=FeeRate(
        fee_type="percentage",
        amount="0.01",  # 1%
        min_fee="0.01",  # $0.01 min
        max_fee="10.00",  # $10 cap
    ),
)

PREMIUM_FEE_SCHEDULE = FeeSchedule(
    name="Premium (Verified Providers)",
    protocol_fee=FeeRate(
        fee_type="percentage",
        amount="0.005",  # 0.5% for verified providers
        min_fee="0.01",
        max_fee="5.00",
    ),
)

ZERO_FEE_SCHEDULE = FeeSchedule(
    name="Zero Fee (Promotional)",
    protocol_fee=FeeRate(
        fee_type="fixed",
        amount="0",
    ),
)


def calculate_fees(
    transaction_amount: str,
    schedule: FeeSchedule = None,
) -> FeeBreakdown:
    """Calculate fees for a transaction amount."""
    schedule = schedule or DEFAULT_FEE_SCHEDULE
    return schedule.calculate_total(transaction_amount)


def create_treasury(
    primary_address: str,
    chain: str = "base",
    protocol_share: str = "1.0",
) -> ProtocolTreasury:
    """Create a protocol treasury with default split (100% to protocol)."""
    treasury = ProtocolTreasury(
        primary_address=primary_address,
        chain=chain,
    )
    treasury.add_recipient(
        address=primary_address,
        share=protocol_share,
        recipient_type="protocol",
        name="EPP Protocol Treasury",
    )
    return treasury
