"""Base transport interface for EPP envelope delivery."""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

from epp.models import Envelope


class Transport(ABC):
    """Abstract base class for EPP transport mechanisms."""

    @abstractmethod
    async def send(self, envelope: Envelope, recipient_address: str) -> str:
        """
        Send an envelope to a recipient.

        Args:
            envelope: The signed EPP envelope to send
            recipient_address: Transport-specific recipient address

        Returns:
            Transaction/delivery ID for tracking
        """
        pass

    @abstractmethod
    async def receive(
        self, recipient_pubkey: str, since: Optional[str] = None
    ) -> AsyncIterator[Envelope]:
        """
        Receive envelopes addressed to a recipient.

        Args:
            recipient_pubkey: The recipient's EPP public key (hex)
            since: Optional cursor/timestamp to fetch only new envelopes

        Yields:
            EPP envelopes addressed to the recipient
        """
        pass
