"""
Logger executor that writes envelope details to a log file.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from ..models import Envelope
from .base import ExecutionResult, Executor

logger = logging.getLogger(__name__)


class LoggerExecutor(Executor):
    """Executor that logs envelope details to a file."""

    def __init__(self, log_file: str):
        """
        Initialize logger executor.

        Args:
            log_file: Path to log file
        """
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def name(self) -> str:
        return "logger"

    def execute(self, envelope: Envelope) -> ExecutionResult:
        """Log envelope details to file."""
        try:
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "envelope_id": envelope.envelope_id,
                "sender": envelope.sender,
                "scope": envelope.scope,
                "prompt": envelope.payload.prompt,
                "context": envelope.payload.context,
                "metadata": envelope.payload.metadata,
            }

            # Append to log file
            with open(self.log_file, "a") as f:
                f.write(json.dumps(log_entry) + "\n")

            logger.info(f"Logged envelope {envelope.envelope_id} to {self.log_file}")

            return ExecutionResult(
                success=True,
                executor_name=self.name(),
                result_data={
                    "log_file": str(self.log_file),
                    "envelope_id": envelope.envelope_id,
                },
            )

        except Exception as e:
            logger.error(f"Failed to log envelope {envelope.envelope_id}: {e}")
            return ExecutionResult(
                success=False,
                executor_name=self.name(),
                error_message=str(e),
            )
