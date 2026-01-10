"""
File queue executor that writes envelopes to a directory for later processing.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from ..models import Envelope
from .base import ExecutionResult, Executor

logger = logging.getLogger(__name__)


class FileQueueExecutor(Executor):
    """Executor that writes envelopes to a file queue."""

    def __init__(self, queue_dir: str):
        """
        Initialize file queue executor.

        Args:
            queue_dir: Directory to write envelope files
        """
        self.queue_dir = Path(queue_dir)
        self.queue_dir.mkdir(parents=True, exist_ok=True)

    def name(self) -> str:
        return "file_queue"

    def execute(self, envelope: Envelope) -> ExecutionResult:
        """Write envelope to queue directory."""
        try:
            # Generate filename with timestamp and envelope ID
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_{envelope.envelope_id}.json"
            filepath = self.queue_dir / filename

            # Write envelope to file
            with open(filepath, "w") as f:
                json.dump(envelope.model_dump(), f, indent=2)

            # Restrict permissions
            os.chmod(filepath, 0o600)

            logger.info(f"Wrote envelope {envelope.envelope_id} to {filepath}")

            return ExecutionResult(
                success=True,
                executor_name=self.name(),
                result_data={
                    "file_path": str(filepath),
                    "envelope_id": envelope.envelope_id,
                },
            )

        except Exception as e:
            logger.error(f"Failed to write envelope {envelope.envelope_id}: {e}")
            return ExecutionResult(
                success=False,
                executor_name=self.name(),
                error_message=str(e),
            )
