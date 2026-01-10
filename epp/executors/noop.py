"""
No-op executor that accepts and logs envelopes without taking action.
"""

import logging

from ..models import Envelope
from .base import ExecutionResult, Executor

logger = logging.getLogger(__name__)


class NoOpExecutor(Executor):
    """Executor that accepts envelopes but performs no action."""

    def name(self) -> str:
        return "noop"

    def execute(self, envelope: Envelope) -> ExecutionResult:
        """Log the envelope and return success."""
        logger.info(
            f"NoOp executor received envelope {envelope.envelope_id} "
            f"from {envelope.sender[:16]}... with scope '{envelope.scope}'"
        )

        return ExecutionResult(
            success=True,
            executor_name=self.name(),
            result_data={
                "envelope_id": envelope.envelope_id,
                "sender": envelope.sender,
                "scope": envelope.scope,
                "prompt_length": len(envelope.payload.prompt),
            },
        )
