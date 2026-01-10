"""
Command executor that runs a shell command with the prompt as input.
"""

import logging
import subprocess
import shlex
from typing import Optional

from ..models import Envelope
from .base import ExecutionResult, Executor

logger = logging.getLogger(__name__)


class CommandExecutor(Executor):
    """Executor that runs a shell command with prompt as input."""

    def __init__(
        self,
        command_template: str,
        timeout: int = 30,
        shell: bool = False,
    ):
        """
        Initialize command executor.

        Args:
            command_template: Command template (use {prompt}, {sender}, {scope} placeholders)
            timeout: Maximum execution time in seconds
            shell: Whether to execute through shell (less safe)
        """
        self.command_template = command_template
        self.timeout = timeout
        self.shell = shell

    def name(self) -> str:
        return "command"

    def execute(self, envelope: Envelope) -> ExecutionResult:
        """Execute command with envelope data."""
        try:
            # Format command with envelope data
            command = self.command_template.format(
                prompt=envelope.payload.prompt,
                sender=envelope.sender,
                scope=envelope.scope,
                envelope_id=envelope.envelope_id,
            )

            if self.shell:
                cmd = command
            else:
                cmd = shlex.split(command)

            logger.info(f"Executing command for envelope {envelope.envelope_id}")

            # Run command
            result = subprocess.run(
                cmd,
                shell=self.shell,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            return ExecutionResult(
                success=result.returncode == 0,
                executor_name=self.name(),
                result_data={
                    "return_code": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
                error_message=result.stderr if result.returncode != 0 else None,
            )

        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out for envelope {envelope.envelope_id}")
            return ExecutionResult(
                success=False,
                executor_name=self.name(),
                error_message=f"Command timed out after {self.timeout}s",
            )

        except Exception as e:
            logger.error(f"Failed to execute command for envelope {envelope.envelope_id}: {e}")
            return ExecutionResult(
                success=False,
                executor_name=self.name(),
                error_message=str(e),
            )
