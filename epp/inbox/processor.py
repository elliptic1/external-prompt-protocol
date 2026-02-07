"""
Core inbox envelope processing logic.
"""

import logging
from datetime import datetime, timezone
from typing import Tuple
from uuid import uuid4

from pydantic import ValidationError

from ..crypto.keys import PublicKey
from ..crypto.signing import verify_envelope_signature
from ..executors.base import Executor
from ..models import (
    Envelope,
    ErrorDetail,
    ErrorReceipt,
    Receipt,
    SuccessReceipt,
)
from ..policy.nonce_registry import NonceRegistry
from ..policy.rate_limiter import RateLimiter
from ..policy.trust_registry import TrustRegistry

logger = logging.getLogger(__name__)


class InboxProcessor:
    """
    Processes EPP envelopes through the full verification and execution pipeline.
    """

    def __init__(
        self,
        recipient_public_key_hex: str,
        trust_registry: TrustRegistry,
        nonce_registry: NonceRegistry,
        rate_limiter: RateLimiter,
        executor: Executor,
    ):
        """
        Initialize inbox processor.

        Args:
            recipient_public_key_hex: This inbox's public key
            trust_registry: Trust registry for sender verification
            nonce_registry: Nonce registry for replay protection
            rate_limiter: Rate limiter for enforcement
            executor: Executor for processing accepted envelopes
        """
        self.recipient_key = recipient_public_key_hex.lower()
        self.trust_registry = trust_registry
        self.nonce_registry = nonce_registry
        self.rate_limiter = rate_limiter
        self.executor = executor

    def process_envelope(self, envelope_data: dict) -> Receipt:
        """
        Process an EPP envelope through the full verification pipeline.

        Args:
            envelope_data: Raw envelope dictionary

        Returns:
            Receipt (success or error)
        """
        received_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        envelope_id = envelope_data.get("envelope_id", "unknown")

        # Step 1: Parse and validate structure
        try:
            envelope = Envelope(**envelope_data)
            envelope_id = envelope.envelope_id
        except ValidationError as e:
            logger.warning(f"Invalid envelope format: {e}")
            return self._error_receipt(envelope_id, received_at, "INVALID_FORMAT", str(e))

        # Step 2: Check version
        if envelope.version != "1":
            logger.warning(f"Unsupported version: {envelope.version}")
            return self._error_receipt(
                envelope_id,
                received_at,
                "UNSUPPORTED_VERSION",
                f"Version '{envelope.version}' not supported",
            )

        # Step 3: Verify recipient
        if envelope.recipient.lower() != self.recipient_key:
            logger.warning(
                f"Wrong recipient: expected {self.recipient_key[:16]}..., "
                f"got {envelope.recipient[:16]}..."
            )
            return self._error_receipt(
                envelope_id,
                received_at,
                "WRONG_RECIPIENT",
                "Envelope not addressed to this inbox",
            )

        # Step 4: Check expiration
        if envelope.is_expired():
            logger.warning(f"Expired envelope: {envelope.expires_at}")
            return self._error_receipt(
                envelope_id, received_at, "EXPIRED", f"Envelope expired at {envelope.expires_at}"
            )

        # Step 5: Verify signature
        try:
            sender_public_key = PublicKey.from_hex(envelope.sender)
            signature_valid = verify_envelope_signature(
                sender_public_key,
                envelope.signature,
                envelope.version,
                envelope.envelope_id,
                envelope.sender,
                envelope.recipient,
                envelope.timestamp,
                envelope.expires_at,
                envelope.nonce,
                envelope.scope,
                envelope.payload.model_dump(exclude_none=True),
                conversation_id=envelope.conversation_id,
                in_reply_to=envelope.in_reply_to,
                delegation=(envelope.delegation.model_dump() if envelope.delegation else None),
            )

            if not signature_valid:
                logger.warning(f"Invalid signature for envelope {envelope_id}")
                return self._error_receipt(
                    envelope_id,
                    received_at,
                    "INVALID_SIGNATURE",
                    "Cryptographic signature verification failed",
                )

        except Exception as e:
            logger.error(f"Signature verification error: {e}")
            return self._error_receipt(
                envelope_id, received_at, "INVALID_SIGNATURE", f"Signature error: {e}"
            )

        # Step 6: Check for replay (nonce)
        if self.nonce_registry.has_seen(envelope.nonce):
            logger.warning(f"Replay detected: nonce {envelope.nonce[:16]}... already seen")
            return self._error_receipt(
                envelope_id,
                received_at,
                "REPLAY_DETECTED",
                "Nonce has been used before",
            )

        # Step 7: Check trust registry
        trust_entry = self.trust_registry.get_sender(envelope.sender)
        if not trust_entry:
            logger.warning(f"Untrusted sender: {envelope.sender[:16]}...")
            return self._error_receipt(
                envelope_id,
                received_at,
                "UNTRUSTED_SENDER",
                "Sender not in trust registry",
            )

        # Step 8: Apply policy - scope
        if not trust_entry.policy.allows_scope(envelope.scope):
            logger.warning(
                f"Scope '{envelope.scope}' not allowed for sender {envelope.sender[:16]}..."
            )
            return self._error_receipt(
                envelope_id,
                received_at,
                "POLICY_DENIED",
                f"Scope '{envelope.scope}' not allowed",
            )

        # Step 9: Apply policy - size
        envelope_size = envelope.size_bytes()
        if not trust_entry.policy.allows_size(envelope_size):
            logger.warning(
                f"Envelope size {envelope_size} exceeds limit "
                f"{trust_entry.policy.max_envelope_size}"
            )
            return self._error_receipt(
                envelope_id,
                received_at,
                "SIZE_EXCEEDED",
                f"Envelope size {envelope_size} exceeds limit",
            )

        # Step 10: Apply policy - rate limit
        rate_allowed, rate_reason = self.rate_limiter.check_and_record(
            envelope.sender,
            trust_entry.policy.rate_limit.max_per_hour,
            trust_entry.policy.rate_limit.max_per_day,
        )

        if not rate_allowed:
            logger.warning(f"Rate limited: {envelope.sender[:16]}... - {rate_reason}")
            return self._error_receipt(envelope_id, received_at, "RATE_LIMITED", rate_reason)

        # All checks passed - record nonce and execute
        try:
            self.nonce_registry.add(envelope.nonce, envelope.expires_at)
        except ValueError as e:
            # Race condition - nonce was added between check and here
            logger.warning(f"Race condition on nonce: {e}")
            return self._error_receipt(envelope_id, received_at, "REPLAY_DETECTED", str(e))

        # Execute the envelope
        logger.info(
            f"Accepted envelope {envelope_id} from {trust_entry.name} "
            f"({envelope.sender[:16]}...) with scope '{envelope.scope}'"
        )
        if envelope.delegation:
            logger.info(f"  Delegation: on behalf of {envelope.delegation.on_behalf_of[:16]}...")
        if envelope.conversation_id:
            logger.info(f"  Conversation: {envelope.conversation_id}")

        execution_result = self.executor.execute(envelope)

        receipt_id = str(uuid4())
        return SuccessReceipt(
            envelope_id=envelope_id,
            received_at=received_at,
            receipt_id=receipt_id,
            executor=execution_result.executor_name,
        )

    def _error_receipt(
        self, envelope_id: str, received_at: str, code: str, message: str
    ) -> ErrorReceipt:
        """Create an error receipt."""
        return ErrorReceipt(
            envelope_id=envelope_id,
            received_at=received_at,
            error=ErrorDetail(code=code, message=message),
        )
