"""HTTP transport - direct POST to inbox endpoint."""

import httpx
from typing import AsyncIterator

from .base import Transport
from epp.models import Envelope


class HttpTransport(Transport):
    """HTTP/HTTPS transport for direct inbox delivery."""

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    async def send(self, envelope: Envelope, recipient_address: str) -> str:
        """
        Send envelope via HTTP POST to inbox endpoint.

        Args:
            envelope: The signed EPP envelope
            recipient_address: HTTP(S) URL of the inbox endpoint

        Returns:
            Receipt ID from the inbox
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                recipient_address,
                json=envelope.model_dump(mode="json")
            )
            response.raise_for_status()
            receipt = response.json()
            return receipt.get("receipt_id", response.headers.get("x-receipt-id", "unknown"))

    async def receive(self, recipient_pubkey: str, since: str | None = None) -> AsyncIterator[Envelope]:
        """
        HTTP transport is push-based, not pull-based.
        This method is not applicable for HTTP transport.
        """
        raise NotImplementedError(
            "HTTP transport is push-based. Use InboxServer to receive envelopes."
        )
        yield  # Make this a generator
